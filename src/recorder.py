# recorder.py —— 录音模块（封装 arecord，自动寻找 reSpeaker 声卡）
import re
import subprocess

# 固件 v2.1.0（2 通道版）实际采样率为 16kHz，正好是 Whisper 的原生采样率
RATE = 16000
CHANNELS = 2


def find_card():
    """从 /proc/asound/cards 自动找 reSpeaker 声卡号，返回如 2。

    避免硬编码 hw:2,0（重启或换 USB 口后卡号可能变化）。
    """
    try:
        with open("/proc/asound/cards", "r") as f:
            content = f.read()
    except FileNotFoundError:
        return None
    for m in re.finditer(r"^\s*(\d+)\s*\[.*?(?:XVF3800|Flex|Array).*?\]", content, re.M):
        return int(m.group(1))
    return None


def get_device():
    card = find_card()
    if card is None:
        raise RuntimeError(
            "未找到 reSpeaker 声卡。请检查 USB 连接（lsusb 应看到 2886:001a）"
        )
    return f"hw:{card},0"


def start_recording(wav_path, device=None, rate=RATE, channels=CHANNELS):
    """启动后台录音，返回进程对象。"""
    cmd = [
        "arecord",
        "-D", device or get_device(),
        "-f", "S16_LE",
        "-r", str(rate),
        "-c", str(channels),
        wav_path,
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_recording(proc):
    """停止录音并等待进程结束。"""
    if proc.poll() is None:
        proc.terminate()
    proc.wait()


if __name__ == "__main__":
    print("找到声卡：", get_device())
