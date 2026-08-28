# summarize.py —— 摘要模块（调用本地 Ollama API，零第三方依赖）
# 模型按用户要求使用 qwen2.5:3b（约 2GB，8GB 内存板子上与 Whisper 分时复用更从容）
import datetime
import json
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:3b"


def build_prompt(text):
    """构造提示词，附带今天日期避免模型把相对日期推算错。"""
    today = datetime.date.today().strftime("%Y-%m-%d")
    return f"""你是一名专业的会议记录助手。今天是 {today}（请用这个日期推算"本周五""下周一"等相对时间的绝对日期，无法推算就写"未明确"）。请根据下面的会议内容，严格输出以下三个部分（用 Markdown 格式）：

## 会议摘要
（用 3~5 句话，客观概括会议讨论了什么、达成了什么结论）

## 待办清单
（用列表形式，每条格式为：- **任务**：负责人（未明确则写"未明确"），截止时间（未明确则写"未明确"））

## 关键结论
（用列表形式，列出会议中做出的重要决定或达成的共识）

会议内容如下：
{text}
"""


def summarize(text, model=MODEL):
    """把会议全文交给 LLM，返回摘要文本。

    keep_alive=0：模型回答完立即从内存卸载，把 8GB 内存让给下一次 Whisper 转写。
    """
    prompt = build_prompt(text)
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": 0,
        "options": {"temperature": 0.3},
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=600) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    return result.get("response", "")
