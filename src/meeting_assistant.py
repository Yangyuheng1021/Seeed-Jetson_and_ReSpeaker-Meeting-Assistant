# meeting_assistant.py —— 主程序：一键开会 → 一键出纪要（含说话人方向时间线）
import datetime
import os
import select
import sys
import threading
import time

import doa
import recorder
import summarize
import transcribe

RECORDING_DIR = os.path.expanduser("~/meeting-assistant/recordings")
OUTPUT_DIR = os.path.expanduser("~/meeting-assistant/meetings")

DOA_INTERVAL = 1.0   # DoA 采样间隔（秒）
SILENCE_TIMEOUT = 60  # 连续无人说话多少秒自动结束录音


def ensure_dirs():
    os.makedirs(RECORDING_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def available_mem_gb():
    with open("/proc/meminfo") as f:
        info = {k: int(v.split()[0]) for k, v in
                (line.split(":") for line in f)}
    return (info["MemFree"] + info["Cached"] + info["Buffers"]) / 1024**2


def check_memory():
    """8GB 板子内存紧张，跑大模型前先看一眼。"""
    free = available_mem_gb()
    print(f"💾 当前可用内存约 {free:.1f} GB")
    if free < 2.5:
        print("⚠️  可用内存偏少！建议先关掉 Firefox 等大程序，否则可能卡死或触发 swap。")


def format_doa_timeline(samples):
    """把 [(秒, 角度, 语音标志)] 整理成人类可读的方向时间线。"""
    if not samples:
        return "（无数据）"
    speaking = [s for s in samples if s[2] == 1]
    if not speaking:
        return "会议期间未检测到语音。"
    total_speech = len(speaking) * DOA_INTERVAL
    mean_angle = sum(s[1] for s in speaking) / len(speaking)
    lines = [
        f"检测到语音总时长约 {total_speech:.0f} 秒，平均声源方向约 {mean_angle:.0f}°。",
        "声源方向变化（说话人移动/切换）：",
    ]
    prev = None
    for sec, angle, flag in samples:
        if flag != 1:
            continue
        minute = f"{int(sec // 60):02d}:{int(sec % 60):02d}"
        bucket = f"{angle // 45 * 45}°"
        if bucket != prev:
            lines.append(f"  {minute} → 声源在 {angle:3.0f}° 方向（{_dir_name(angle)}）")
            prev = bucket
    return "\n".join(lines)


def _dir_name(angle):
    names = {0: "正前方", 45: "右前方", 90: "右侧", 135: "右后方",
             180: "正后方", 225: "左后方", 270: "左侧", 315: "左前方"}
    key = min(names, key=lambda k: abs(((angle - k + 180) % 360) - 180))
    return names[key]


class DoaLogger(threading.Thread):
    """录音期间后台采样 DoA 方向角。"""

    def __init__(self):
        super().__init__(daemon=True)
        self.samples = []
        self._stop = threading.Event()

    def run(self):
        t0 = time.time()
        try:
            dev = doa.RespeakerDoA()
        except Exception as e:
            print(f"⚠️  DoA 采样不可用（{e}），本次会议将无方向信息。")
            return
        try:
            while not self._stop.is_set():
                try:
                    angle, speech = dev.read()
                    self.samples.append((time.time() - t0, angle, speech))
                except Exception:
                    pass  # 单次读取失败不致命，跳过
                time.sleep(DOA_INTERVAL)
        finally:
            dev.close()

    def stop(self):
        self._stop.set()


def wait_for_stop(logger):
    """回车手动停止；或连续 SILENCE_TIMEOUT 秒无人说话自动停止。"""
    print(f"\n👉 会议结束按【回车】停止录音")
    print(f"   （连续 {SILENCE_TIMEOUT} 秒无人说话将自动结束）...")
    last_speech = time.time()
    while True:
        # 非阻塞等待回车
        if select.select([sys.stdin], [], [], 0.2)[0]:
            sys.stdin.readline()
            return "manual"
        recent = logger.samples[-10:]
        if any(s[2] == 1 for s in recent):
            last_speech = time.time()
        if time.time() - last_speech >= SILENCE_TIMEOUT:
            print("\n🤫 连续 60 秒无人说话，自动结束录音。")
            return "auto"


def main():
    ensure_dirs()
    check_memory()

    print("=" * 52)
    print("        智能会议纪要助手")
    print("  定向拾音 · Whisper 转写 · LLM 摘要")
    print("=" * 52)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    wav_path = os.path.join(RECORDING_DIR, f"meeting_{stamp}.wav")

    # ---- 1. 录音（带 DoA 时间线采样） ----
    input("\n👉 按【回车】开始录音...")
    print("🎙️  录音中...（DoA 方向角同步采样中）")
    proc = recorder.start_recording(wav_path)
    logger = DoaLogger()
    logger.start()
    try:
        how = wait_for_stop(logger)
    except KeyboardInterrupt:
        how = "manual"
        print("\n检测到 Ctrl+C，停止录音。")
    recorder.stop_recording(proc)
    logger.stop()
    logger.join(timeout=3)
    print("✅ 录音已保存：", wav_path)

    # ---- 2. 转写 ----
    check_memory()
    print("\n📝 正在转写（Whisper large-v3-turbo CUDA 处理中，请稍候）...")
    t0 = time.time()
    try:
        full_text = transcribe.transcribe(wav_path, language="auto")
    except Exception as e:
        print("❌ 转写出错：", e)
        return
    print(f"✅ 转写完成（用时 {time.time() - t0:.1f} 秒）\n")
    print("---- 转写全文 ----")
    print(full_text)
    print("------------------\n")

    # ---- 3. 摘要 ----
    check_memory()
    print("🤖 正在生成会议摘要与待办清单（qwen2.5:3b 处理中）...")
    try:
        summary_text = summarize.summarize(full_text)
    except Exception as e:
        print("❌ 摘要生成出错：", e)
        return
    print("✅ 摘要生成完成\n")

    # ---- 4. 保存纪要 ----
    md_content = f"""# 会议纪要 {stamp}

## 会议摘要与待办

{summary_text}

---

## 🎯 说话人方向时间线（DoA 定向拾音）

{format_doa_timeline(logger.samples)}

---

## 转写全文

{full_text}

> 生成时间：{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 音频文件：{os.path.basename(wav_path)}
"""
    md_path = os.path.join(OUTPUT_DIR, f"meeting_{stamp}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print("=" * 52)
    print("📄 会议纪要已生成：")
    print("  ", md_path)
    print("=" * 52)
    print("\n--- 摘要与待办 ---\n")
    print(summary_text)


if __name__ == "__main__":
    main()
