# app.py —— 会议纪要助手 Web 服务（Flask）
# 浏览器打开 http://<Jetson IP>:5000 使用；手机/电脑同局域网均可访问
import datetime
import os
import threading
import time

from flask import Flask, jsonify, request, send_from_directory

import doa
import recorder
import summarize
import transcribe

BASE_DIR = os.path.expanduser("~/meeting-assistant")
RECORDING_DIR = os.path.join(BASE_DIR, "recordings")
OUTPUT_DIR = os.path.join(BASE_DIR, "meetings")
SILENCE_TIMEOUT = 60   # 连续无人说话多少秒自动结束录音（可调）
DOA_INTERVAL = 1.0

app = Flask(__name__, static_folder="static", static_url_path="/static")

_lock = threading.Lock()
_state = {
    "status": "idle",          # idle | recording | processing
    "started_at": None,
    "elapsed": 0,
    "doa_angle": None,         # 最新声源方向角（0-359）
    "speaking": False,         # 当前是否有人在说话
    "speech_secs": 0,          # 本场会议累计检测到语音的秒数
    "silence_secs": 0,         # 连续静音秒数
    "doa_samples": [],         # [(elapsed_sec, angle, speech)] DoA 采样时间线
    "progress": "",            # 处理阶段描述（转写中/摘要中...）
    "result": None,            # 生成的纪要文件名
    "error": None,
}
_rec_proc = None


# ---------- 方向角 → 中文方位 ----------
def dir_name(angle):
    names = {0: "正前方", 45: "右前方", 90: "右侧", 135: "右后方",
             180: "正后方", 225: "左后方", 270: "左侧", 315: "左前方"}
    key = min(names, key=lambda k: abs(((angle - k + 180) % 360) - 180))
    return names[key]


def _set(**kw):
    with _lock:
        _state.update(kw)


def _get(key):
    with _lock:
        return _state[key]


# ---------- 录音 + DoA 采样线程 ----------
class MeetingRecorder(threading.Thread):
    """录音线程：跑 arecord，同时每 1s 采样 DoA，静音超时自动停止。"""

    def __init__(self, wav_path):
        super().__init__(daemon=True)
        self.wav_path = wav_path
        self.proc = None
        self.auto_stopped = False

    def run(self):
        global _rec_proc
        self.proc = recorder.start_recording(self.wav_path)
        _rec_proc = self.proc
        t0 = time.time()
        try:
            dev = doa.RespeakerDoA()
        except Exception as e:
            _set(error=f"DoA 不可用：{e}")
            dev = None

        silence = 0
        try:
            while self.proc.poll() is None:
                if dev is not None:
                    try:
                        angle, speech = dev.read()
                        elapsed = int(time.time() - t0)
                        samples = _get("doa_samples") + [(elapsed, angle, speech)]
                        _set(doa_angle=angle,
                             speaking=bool(speech),
                             speech_secs=_get("speech_secs") + (1 if speech else 0),
                             silence_secs=silence,
                             doa_samples=samples,
                             elapsed=elapsed)
                        silence = 0 if speech else silence + 1
                    except Exception:
                        silence += 1
                else:
                    silence += 1
                _set(elapsed=int(time.time() - t0))
                # 静音超时 → 自动结束
                if silence >= SILENCE_TIMEOUT and _get("status") == "recording":
                    self.auto_stopped = True
                    break
                time.sleep(DOA_INTERVAL)
        finally:
            if dev is not None:
                dev.close()
            recorder.stop_recording(self.proc)
            _set(elapsed=int(time.time() - t0))
            # 静音自动结束 → 自动进入处理流程
            if self.auto_stopped:
                _set(status="processing", progress="静音超时自动结束，开始转写...")
                MeetingProcessor(self.wav_path).start()


# ---------- 转写 + 摘要线程 ----------
class MeetingProcessor(threading.Thread):
    def __init__(self, wav_path):
        super().__init__(daemon=True)
        self.wav_path = wav_path

    def run(self):
        stamp = os.path.basename(self.wav_path).replace("meeting_", "").replace(".wav", "")
        try:
            _set(progress="Whisper 转写中（约需录音时长的 1/3 ~ 1 倍时间）...")
            full_text = transcribe.transcribe(self.wav_path, language="auto")

            _set(progress="LLM 生成摘要中（qwen2.5:3b）...")
            summary_text = summarize.summarize(full_text)

            timeline = format_timeline()
            md_content = f"""# 会议纪要 {stamp}

## 会议摘要与待办

{summary_text}

---

## 🎯 说话人方向时间线（DoA 定向拾音）

{timeline}

---

## 转写全文

{full_text}

> 生成时间：{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 音频文件：{os.path.basename(self.wav_path)}
"""
            md_name = f"meeting_{stamp}.md"
            with open(os.path.join(OUTPUT_DIR, md_name), "w", encoding="utf-8") as f:
                f.write(md_content)
            _set(progress="完成", result=md_name, status="idle", error=None)
        except Exception as e:
            _set(progress="", status="idle", error=str(e))


def format_timeline():
    samples = _get("doa_samples")
    speaking = [s for s in samples if s[2] == 1]
    if not speaking:
        return "会议期间未检测到语音。"
    total = len(speaking)
    lines = [f"检测到语音总时长约 {total} 秒。", "声源方向变化（说话人移动/切换）："]
    prev = None
    for sec, angle, flag in samples:
        if flag != 1:
            continue
        minute = f"{int(sec // 60):02d}:{int(sec % 60):02d}"
        bucket = angle // 45 * 45
        if bucket != prev:
            lines.append(f"  {minute} → 声源在 {angle:3.0f}° 方向（{dir_name(angle)}）")
            prev = bucket
    return "\n".join(lines)


# ---------- 路由 ----------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/start", methods=["POST"])
def start():
    with _lock:
        if _state["status"] != "idle":
            return jsonify({"ok": False, "msg": f"当前状态：{_state['status']}"}), 409
        _state.update(status="recording", started_at=time.time(), elapsed=0,
                      doa_angle=None, speaking=False, speech_secs=0, silence_secs=0,
                      doa_samples=[], progress="", result=None, error=None)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    wav_path = os.path.join(RECORDING_DIR, f"meeting_{stamp}.wav")
    MeetingRecorder(wav_path).start()
    return jsonify({"ok": True, "wav": os.path.basename(wav_path)})


@app.route("/api/stop", methods=["POST"])
def stop():
    with _lock:
        if _state["status"] != "recording":
            return jsonify({"ok": False, "msg": "当前没有进行中的会议"}), 409
        _state["status"] = "processing"
        # 找到录音进程并停止
        wav_path = None
        rec_threads = [t for t in threading.enumerate() if isinstance(t, MeetingRecorder)]
        if rec_threads:
            t = rec_threads[0]
            wav_path = t.wav_path
            recorder.stop_recording(t.proc)
    if wav_path:
        MeetingProcessor(wav_path).start()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "未找到录音进程"}), 500


@app.route("/api/status")
def status():
    with _lock:
        snap = dict(_state)
    snap["dir"] = dir_name(snap["doa_angle"]) if snap["doa_angle"] is not None else None
    snap["silence_timeout"] = SILENCE_TIMEOUT
    return jsonify(snap)


@app.route("/api/meetings")
def meetings():
    files = sorted(
        (f for f in os.listdir(OUTPUT_DIR) if f.endswith(".md")),
        reverse=True,
    )
    return jsonify(files)


@app.route("/api/meetings/<name>")
def meeting(name):
    # 防目录穿越
    if "/" in name or ".." in name:
        return "bad", 400
    return send_from_directory(OUTPUT_DIR, name)


if __name__ == "__main__":
    os.makedirs(RECORDING_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, threaded=True)
