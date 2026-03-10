import platform
import subprocess
import uuid
import hashlib
import re

def get_mac_address():
    """获取 MAC 地址"""
    mac = uuid.getnode()
    return ':'.join(("%012X" % mac)[i:i+2] for i in range(0, 12, 2))

def get_motherboard_uuid_windows():
    """Windows 下获取主板 UUID"""
    try:
        output = subprocess.check_output("wmic csproduct get uuid", shell=True)
        lines = output.decode().splitlines()
        for line in lines:
            if re.match(r"^[0-9A-Fa-f\-]{36}$", line.strip()):
                return line.strip()
    except Exception:
        return None

def get_cpu_serial_linux():
    """Linux 下获取 CPU 序列号"""
    try:
        output = subprocess.check_output("cat /proc/cpuinfo", shell=True)
        for line in output.decode().splitlines():
            if "Serial" in line or "serial" in line:
                return line.split(":")[1].strip()
    except Exception:
        return None

def get_fingerprint():
    """拼接所有信息并生成 SHA256 指纹"""
    parts = [get_mac_address()]

    system = platform.system()
    if system == "Windows":
        uuid_win = get_motherboard_uuid_windows()
        if uuid_win:
            parts.append(uuid_win)
    elif system == "Linux":
        cpu_serial = get_cpu_serial_linux()
        if cpu_serial:
            parts.append(cpu_serial)

    raw = "|".join(parts)
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()
    return fingerprint

if __name__ == "__main__":
    fp = get_fingerprint()
    print("📌 客户机器指纹如下，请复制发送给开发者：\n")
    print(fp)
