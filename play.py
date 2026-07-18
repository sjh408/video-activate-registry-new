from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import os
import hashlib
import uuid
import platform
import subprocess
import json
import urllib.request
import urllib.error
from datetime import datetime
import tempfile
import time
import sys
from tkinter import Tk, filedialog

# 密钥必须和管理员端完全一致，否则解密失败
GLOBAL_ENC_KEY = b"1234567890ABCDEF1234567890ABCDEF"
REGISTRY_URL = "https://video-activate-reg-1306943725.cos.ap-guangzhou.myqcloud.com/activation_registry.json"

# 获取本机机器码
def get_machine_code():
    raw_id = ""
    os_name = platform.system()
    try:
        if os_name == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            raw_id = winreg.QueryValueEx(key, "MachineGuid")[0]
        elif os_name == "Linux":
            with open("/etc/machine-id", "r", encoding="utf-8") as f:
                raw_id = f.read().strip()
        elif os_name == "Darwin":
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                stderr=subprocess.STDOUT
            ).decode("utf-8")
            import re
            match = re.search(r'"IOPlatformUUID"\s*=\s*"(.+?)"', out)
            if match:
                raw_id = match.group(1)
    except Exception as e:
        raw = str(uuid.getnode()) + platform.system() + platform.node()
        raw_id = raw
    return hashlib.md5(raw_id.encode("utf-8")).hexdigest()

# 拉取云端注册表
def fetch_registry():
    url = REGISTRY_URL + ("&" if "?" in REGISTRY_URL else "?") + "_=" + str(datetime.now().timestamp())
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, dict):
            print("⚠️ 激活注册表格式错误")
            return None
        return data
    except Exception:
        print("⚠️ 网络异常，无法验证激活权限")
        return None

# 校验激活码
def verify_activation(mid, entered_code):
    reg = fetch_registry()
    if reg is None:
        return False
    entry = reg.get(mid)
    if not isinstance(entry, dict):
        return False
    return entry.get("code") == entered_code

# 解密视频
def decrypt_video(enc_path: str, out_path: str):
    chunk_size = 64 * 1024 * AES.block_size
    cipher = AES.new(GLOBAL_ENC_KEY, AES.MODE_CBC, iv=b'0000000000000000')
    file_size = os.path.getsize(enc_path)
    processed = 0
    buffer = b''
    with open(enc_path, "rb") as fin, open(out_path, "wb") as fout:
        while True:
            data = fin.read(chunk_size)
            if not data:
                break
            buffer += data
            while len(buffer) >= chunk_size:
                block = buffer[:chunk_size]
                buffer = buffer[chunk_size:]
                decrypted = cipher.decrypt(block)
                fout.write(decrypted)
                processed += len(block)
                percent = min(99, int(processed * 100 / file_size))
                print(f"\r解密进度：{percent}% ({processed}/{file_size} bytes)", end="", flush=True)
        if buffer:
            decrypted_last = cipher.decrypt(buffer)
            unpadded = unpad(decrypted_last, AES.block_size)
            fout.write(unpadded)
            processed += len(buffer)
    print(f"\r解密进度：100% ({processed}/{file_size} bytes)", flush=True)

# 系统默认播放器（稳定不崩溃）
def open_video(path):
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])

# 弹窗选择加密文件
def select_enc_file():
    root = Tk()
    root.withdraw()
    # 弹窗筛选仅enc文件
    all_files_pattern = "*" if platform.system() == "Darwin" else "*.*"
    file_path = filedialog.askopenfilename(
        title="选择加密视频文件",
        filetypes=[("加密视频 *.enc", "*.enc"), ("所有文件", all_files_pattern)]
    )
    root.destroy()
    return file_path

# 安全删除文件，处理文件占用WinError32
def safe_remove_file(file_path, retry_times=5, delay=1):
    if not os.path.exists(file_path):
        return True
    for i in range(retry_times):
        try:
            os.remove(file_path)
            return True
        except PermissionError:
            print(f"⚠️ 文件被播放器占用，{delay}秒后重试删除({i+1}/{retry_times})")
            time.sleep(delay)
    print("❌ 多次删除失败，请关闭播放器后手动清理临时文件")
    return False

# 主程序
if __name__ == "__main__":
    print("=== 加密视频播放器（弹窗选择+连续播放）===")
    mid = get_machine_code()
    print(f"本机机器码：{mid}")
    print("请将机器码发送给管理员获取激活码\n")

    # 仅首次启动输入激活码
    act_code = input("输入管理员提供的激活码：").strip()
    if not verify_activation(mid, act_code):
        print("❌ 激活码无效、已吊销或网络失败，禁止播放")
        input("按回车退出")
        sys.exit(1)
    print("✅ 激活校验通过，弹窗选择视频即可连续播放\n")

    # 循环连续播放
    while True:
        # 每次生成独立随机临时mp4，避免文件占用冲突
        tmp_fd, temp_mp4 = tempfile.mkstemp(suffix=".mp4")
        os.close(tmp_fd)

        print("\n正在弹出文件选择窗口...")
        enc_file = select_enc_file()

        # 用户点弹窗取消，退出程序
        if not enc_file:
            print("未选择文件，是否退出程序？")
            opt = input("输入 q 退出，直接回车继续播放：").strip().lower()
            safe_remove_file(temp_mp4)
            if opt == "q":
                print("程序退出，清理全部临时文件")
                break
            continue

        print(f"选中加密文件：{enc_file}")
        print("开始解密视频...")
        decrypt_video(enc_file, temp_mp4)
        print("✅ 解密完成，自动打开播放器，请完整看完视频！")
        open_video(temp_mp4)

        input("\n看完视频后按回车，自动清理临时文件，重新弹出选择窗口")
        # 容错删除，解决文件占用报错
        safe_remove_file(temp_mp4)
        print("✅ 本轮文件清理完毕，即将重新弹窗选择下一个视频")