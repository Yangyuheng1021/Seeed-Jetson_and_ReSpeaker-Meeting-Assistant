# 智能会议纪要助手（Meeting Assistant）

一键开会 → 一键出纪要：**定向拾音 · Whisper 转写 · LLM 摘要**，附带说话人方向（DoA）时间线。

专为 [Jetson Orin Nano](https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/) 等 8GB 内存级 Linux 板卡设计，搭配 [reSpeaker Flex](https://wiki.seeedstudio.com/respeaker_flex/) USB 麦克风阵列。点击 Web 页面上的按钮开始会议，系统自动完成录音、转写、摘要全流程，生成结构化 Markdown 会议纪要。支持命令行与 Web 两种使用方式，局域网内手机、电脑均可通过浏览器操作。

## 项目背景

常规会议纪要依赖人工整理，耗时且容易遗漏。本项目的目标是利用边缘设备构建一个**离线可用的会议记录系统**：

- **定向拾音**：通过 reSpeaker Flex 的波束成形能力获取声源方向角（DoA），纪要中附带"谁在什么方向说话"的时间线，辅助还原讨论过程；
- **本地转写**：whisper.cpp（large-v3-turbo）完全本地运行，会议内容不出设备；
- **本地摘要**：Ollama 加载 qwen2.5:3b 生成摘要、待办清单与关键结论，并自动把"本周五""下周一"等相对日期推算为绝对日期；
- **内存友好**：转写与摘要分时复用 8GB 内存，摘要完成后模型立即卸载（`keep_alive=0`），避免 OOM。

## 功能特性

### 录音
- `arecord` 录制 **16kHz / 双声道 / S16_LE** WAV（与 Whisper 原生采样率一致）
- 自动扫描 `/proc/asound/cards` 发现 reSpeaker 声卡号，无需硬编码 `hw:2,0`，重启或换 USB 口后仍可用
- 连续 **60 秒**无人说话自动结束录音并进入处理流程（可配置）

### DoA 说话人方向
- 通过 USB 厂商协议（`ctrl_transfer`，resid=20 / cmdid=18）直读 reSpeaker Flex 的声源方向角（0–359°）与语音检测标志
- 每秒采样一次，实时绘制方向雷达图
- 纪要中生成"说话人方向时间线"：标注语音出现时刻与声源方位（8 方位中文描述）

### 转写
- 提取 **ch1（ASR 优化声道）**：2 通道固件中 ch1 为 AEC + AGC 处理后的语音识别专用输出，实测转写效果优于 ch0 波束输出
- 调用 whisper.cpp `large-v3-turbo` 模型本地转写，支持自动语言检测

### 摘要
- 调用本地 Ollama `qwen2.5:3b`，输出三部分：**会议摘要 / 待办清单 / 关键结论**
- 提示词自动附带当天日期，相对日期（"本周五""下周一"）推算为绝对日期，无法推算则标注"未明确"
- `temperature=0.3` 保证输出稳定；生成完毕模型立即从内存卸载

### Web 界面
- Flask 服务（`0.0.0.0:5000`），深色主题响应式页面，局域网内手机/电脑均可访问
- 实时显示：录音时长、语音累计秒数、连续静音倒计时、声源方向雷达图、说话/安静状态
- 历史纪要列表，点击即可查看全文；状态每秒自动刷新
- 状态机管理：`idle → recording → processing → idle`，处理中禁用按钮防止并发冲突

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    Web 界面 / CLI                     │
│   （Flask app.py 或命令行 meeting_assistant.py）      │
└───────┬──────────────┬───────────────┬──────────────┘
        │              │               │
        ▼              ▼               ▼
┌──────────────┐ ┌────────────┐ ┌──────────────┐
│ recorder.py  │ │   doa.py   │ │ transcribe.py│
│ arecord 录音  │ │ USB 方向角  │ │ sox 提声道    │
│ 自动发现声卡  │ │ 语音检测    │ │ whisper-cli  │
└──────┬───────┘ └─────┬──────┘ └──────┬───────┘
       │               │               │
       ▼               ▼               ▼
  recordings/     方向时间线      转写全文
       │               │               │
       └───────────────┴───────┬───────┘
                               ▼
                     ┌──────────────────┐
                     │   summarize.py   │
                     │ Ollama qwen2.5:3b│
                     └────────┬─────────┘
                              ▼
                        meetings/*.md
                    （摘要 + 时间线 + 全文）
```

## 硬件要求

| 硬件 | 规格要求 | 说明 |
| ---- | -------- | ---- |
| reSpeaker Flex | USB 麦克风阵列，2 通道固件 **v2.1.0**，USB ID `2886:001a` | DoA 方向角与 ASR 优化声道的来源 |
| 主控板卡 | Jetson Orin Nano 或其他 Linux 板卡，内存 ≥ 8GB | Whisper 与 LLM 分时复用内存 |
| 网络（可选） | 局域网 | 仅 Web 界面访问需要；转写与摘要全程离线 |

> 固件为 1 通道版的设备虽然也能录音，但无 ASR 优化声道且 DoA 行为不同，本项目按 2 通道 v2.1.0 固件实现，请先确认固件版本。

## 软件依赖

### 1. 系统工具

```bash
sudo apt update
sudo apt install -y alsa-utils sox python3-pip
```

- `alsa-utils`：提供 `arecord` 录音命令
- `sox`：声道提取（双声道 → ASR 单声道）

### 2. Python 包

```bash
pip install flask pyusb
```

| 包 | 用途 |
| -- | ---- |
| flask | Web 服务与 API |
| pyusb | 读取 reSpeaker Flex 的 DoA 数据 |

### 3. whisper.cpp（转写）

```bash
# 克隆并编译
git clone https://github.com/ggml-org/whisper.cpp ~/whisper.cpp
cd ~/whisper.cpp && make -j

# 下载 large-v3-turbo 模型（约 1.6GB）
bash ./models/download-ggml-model.sh large-v3-turbo
```

> 项目默认查找 `~/whisper.cpp/build/bin/whisper-cli` 与 `~/whisper.cpp/models/ggml-large-v3-turbo.bin`，如路径不同请修改 `src/transcribe.py` 顶部的常量。

### 4. Ollama + qwen2.5:3b（摘要）

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b
```

仓库内的 `Modelfile` 指向本地 `qwen2.5-3b-instruct-q4_k_m.gguf`（约 2GB，未随仓库分发）。如需使用该文件：

```bash
# 从 HuggingFace 下载（约 2GB）
wget https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf

# 导入 Ollama
ollama create qwen2.5:3b -f Modelfile
```

### 5. udev 规则（免 sudo 访问 USB 设备）

创建 `/etc/udev/rules.d/99-respeaker.rules`：

```
SUBSYSTEM=="usb", ATTR{idVendor}=="2886", ATTR{idProduct}=="001a", MODE="0666"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

然后**重新插拔一次 USB 设备**使规则生效。验证：

```bash
lsusb | grep 2886:001a
python3 -c "import usb.core; print(usb.core.find(idVendor=0x2886, idProduct=0x001a))"
```

## 配置说明

| 参数 | 默认值 | 位置 | 说明 |
| ---- | ------ | ---- | ---- |
| `SILENCE_TIMEOUT` | 60 秒 | `src/app.py` / `src/meeting_assistant.py` | 连续无人说话自动结束录音的时长 |
| `DOA_INTERVAL` | 1.0 秒 | 同上 | DoA 方向角采样间隔 |
| `RATE` / `CHANNELS` | 16000 / 2 | `src/recorder.py` | 录音采样率与声道数（勿改，与固件匹配） |
| `ASR_CHANNEL` | 2（即 ch1） | `src/transcribe.py` | 转写提取的声道，sox 编号从 1 开始 |
| `MODEL` | `qwen2.5:3b` | `src/summarize.py` | Ollama 模型名 |
| `temperature` | 0.3 | `src/summarize.py` | 摘要生成的随机性 |
| `WHISPER_BIN` / `MODEL_PATH` | `~/whisper.cpp/...` | `src/transcribe.py` | whisper-cli 与模型路径 |
| 服务端口 | 5000 | `src/app.py` | Web 服务监听端口 |

## 使用方法

### 方式一：Web 界面（推荐）

```bash
cd src
python app.py
```

1. 浏览器打开 `http://<板卡IP>:5000`（板卡上直接操作则用 `http://localhost:5000`）
2. 页面显示声源方向雷达图与空闲状态，点击 **▶ 开始会议**
3. 录音期间实时显示：会议时长、语音累计、连续静音秒数、当前声源方向与说话状态
4. 点击 **⏹ 结束会议**（或静音 60 秒自动结束），自动进入处理流程：
   - 显示"Whisper 转写中..."（耗时约为录音时长的 1/3 ~ 1 倍）
   - 显示"LLM 生成摘要中..."
5. 完成后在"历史会议纪要"列表点击查看全文

### 方式二：命令行

```bash
cd src
python meeting_assistant.py
```

按提示操作：回车开始录音 → 回车结束（或静音 60 秒自动结束）→ 自动转写并打印全文 → 自动生成摘要并打印 → 纪要保存至 `~/meeting-assistant/meetings/`。

### Web API 参考

| 端点 | 方法 | 说明 |
| ---- | ---- | ---- |
| `/api/start` | POST | 开始录音（录音中/处理中返回 409） |
| `/api/stop` | POST | 结束录音并启动转写+摘要 |
| `/api/status` | GET | 返回 JSON 状态：`status`、`elapsed`、`doa_angle`、`speaking`、`speech_secs`、`silence_secs`、`progress`、`error` 等 |
| `/api/meetings` | GET | 历史纪要文件名列表（按时间倒序） |
| `/api/meetings/<name>` | GET | 指定纪要的 Markdown 全文（已做路径穿越防护） |

## 输出文件格式

每场会议生成两个文件：

```
~/meeting-assistant/
├── recordings/
│   ├── meeting_20260821_091501.wav        # 原始双声道录音
│   ├── meeting_20260821_091501_mono.wav   # ASR 单声道（转写用）
│   └── meeting_20260821_091501_mono.wav.txt  # 转写全文
└── meetings/
    └── meeting_20260821_091501.md         # 会议纪要
```

纪要 Markdown 结构：

```markdown
# 会议纪要 20260821_091501

## 会议摘要与待办
（LLM 输出：会议摘要 / 待办清单 / 关键结论）

---

## 🎯 说话人方向时间线（DoA 定向拾音）
检测到语音总时长约 49 秒。
声源方向变化（说话人移动/切换）：
  00:00 → 声源在 159° 方向（正后方）
  ...

---

## 转写全文
（whisper.cpp 转写结果）

> 生成时间：2026-08-21 09:15:01
> 音频文件：meeting_20260821_091501.wav
```

## 目录结构

```
meeting-assistant/
├── src/
│   ├── app.py                # Flask Web 服务（状态机、录音/处理线程、REST API）
│   ├── meeting_assistant.py  # 命令行主程序（一键全流程）
│   ├── recorder.py           # arecord 封装 + reSpeaker 声卡自动发现
│   ├── doa.py                # reSpeaker Flex DoA 读取（USB 厂商协议）
│   ├── transcribe.py         # 声道提取（sox）+ whisper-cli 转写
│   ├── summarize.py          # Ollama API 摘要生成（提示词 + 日期推算）
│   └── static/index.html     # Web 前端（雷达图、状态轮询、纪要列表）
├── Modelfile                 # Ollama 模型定义（指向本地 gguf）
├── README.md
├── LICENSE
└── .gitignore
```

> 录音与纪要保存在 `~/meeting-assistant/recordings/` 与 `~/meeting-assistant/meetings/`（程序运行时自动创建），不入库。

## 常见问题

### 录音相关
- **找不到声卡**：`lsusb` 应看到 `2886:001a`；确认固件为 2 通道版（v2.1.0）。声卡号由程序自动发现，无需手动配置。
- **录音无声/单声道**：确认 `arecord -l` 中 reSpeaker 显示为 2 通道设备。

### DoA 相关
- **DoA 不可用**：确认 udev 规则已生效且设备重新插拔过；用 `python3 src/doa.py` 单独测试（应连续打印 `DOA=xxx° speech=x`）。
- **方向角乱跳**：方向角基于波束能量估算，多人同时说话或多径反射时会有波动，属正常现象；时间线按 45° 分桶展示以降低噪声。

### 转写相关
- **转写失败**：确认 `~/whisper.cpp/build/bin/whisper-cli` 与 `~/whisper.cpp/models/ggml-large-v3-turbo.bin` 存在；模型路径不一致时修改 `src/transcribe.py`。
- **转写慢**：large-v3-turbo 在 Orin Nano 上转写耗时约为录音时长的 1/3 ~ 1 倍，属预期；可换 smaller 模型提速（需同步修改 `MODEL_PATH`）。

### 摘要相关
- **摘要超时**：Ollama 首次加载模型较慢（2GB 读盘），超时时间已设为 600 秒；若仍超时请确认 `ollama serve` 正在运行、`ollama list` 中有 `qwen2.5:3b`。
- **内存不足**：8GB 板子上 Whisper 与 LLM 分时运行，摘要完成后模型自动卸载。启动时若可用内存 < 2.5GB 会有警告，建议关闭浏览器等大程序。

### Web 相关
- **手机打不开页面**：确认手机与板卡同一局域网，且防火墙放行 5000 端口（`sudo ufw allow 5000`）。
- **按钮变灰**：正在处理中（转写/摘要），处理完成自动恢复。

## 许可证

[MIT](LICENSE) © 2026 Yangyuheng1021
