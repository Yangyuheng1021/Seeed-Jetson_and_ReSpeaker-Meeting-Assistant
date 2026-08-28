# transcribe.py —— 转写模块（声道提取 + whisper-cli）
import os
import subprocess

WHISPER_BIN = os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli")
MODEL_PATH = os.path.expanduser("~/whisper.cpp/models/ggml-large-v3-turbo.bin")

# 2 通道固件的声道定义：
#   ch0 (左) = 后处理波束输出；ch1 (右) = ASR 输出（AEC_ASROUTONOFF=1，带 AGC，专为语音识别设计）
# 实测 ch1 能量显著高于 ch0，转写取 ch1 效果更好。
ASR_CHANNEL = 2  # sox 的声道编号从 1 开始


def _find_bin():
    """whisper-cli 或旧版 main，谁存在用谁。"""
    for cand in (WHISPER_BIN, os.path.expanduser("~/whisper.cpp/build/bin/main")):
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError("找不到 whisper-cli，请先编译 whisper.cpp（第 4 章）")


def _extract_mono(wav_path):
    """用 sox 提取 ASR 声道为单声道 wav，返回路径。"""
    mono_path = wav_path.replace(".wav", "_mono.wav")
    subprocess.run(
        ["sox", wav_path, "-c", "1", mono_path, "remix", str(ASR_CHANNEL)],
        check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return mono_path


def transcribe(wav_path, language="auto"):
    """把音频文件转成文字，返回文本字符串。"""
    mono_path = _extract_mono(wav_path)
    cmd = [
        _find_bin(),
        "-m", MODEL_PATH,
        "-f", mono_path,
        "-l", language,
        "-otxt",
    ]
    subprocess.run(cmd, check=True)

    txt_path = mono_path + ".txt"
    with open(txt_path, "r", encoding="utf-8") as f:
        return f.read().strip()
