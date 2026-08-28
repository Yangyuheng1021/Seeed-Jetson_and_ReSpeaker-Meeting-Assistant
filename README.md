# 智能会议纪要助手（Meeting Assistant）

一键开会 → 一键出纪要：**定向拾音 · Whisper 转写 · LLM 摘要**，附带说话人方向（DoA）时间线。

基于 [reSpeaker Flex](https://wiki.seeedstudio.com/respeaker_flex/) 麦克风阵列与 Jetson/Linux 板卡，支持命令行与 Web 两种使用方式。浏览器（或局域网内手机）打开 Web 界面即可开始/停止会议，自动完成转写、摘要并生成 Markdown 会议纪要。

## 功能特性

- **录音**：`arecord` 录制 16kHz 双声道 WAV，自动发现 reSpeaker 声卡（无需硬编码卡号）
- **DoA 时间线**：通过 USB 厂商协议读取 reSpeaker Flex 的声源方向角（0–359°）与语音检测标志，生成说话人方向时间线
- **转写**：提取 ASR 优化声道，调用 [whisper.cpp](https://github.com/ggml-org/whisper.cpp)（large-v3-turbo）完成语音转文字
- **摘要**：调用本地 Ollama `qwen2.5:3b` 生成会议摘要、待办清单与关键结论（自动推算相对日期）
- **静音自动结束**：连续 60 秒无人说话自动停止录音并进入处理流程
- **Web 界面**：Flask 服务，实时显示录音时长、当前声源方向、语音检测状态与处理进度

## 硬件依赖

| 硬件 | 说明 |
| ---- | ---- |
| reSpeaker Flex | USB 麦克风阵列（USB ID `2886:001a`，2 通道固件 v2.1.0） |
| Jetson 或其他 Linux 板卡 | 建议可用内存 ≥ 8GB（Whisper 与 LLM 分时复用） |

## 软件依赖

### 系统工具

```bash
sudo apt install alsa-utils sox
```

### Python 包

```bash
pip install flask pyusb
```

### whisper.cpp

编译并下载 `ggml-large-v3-turbo` 模型：

```bash
git clone https://github.com/ggml-org/whisper.cpp ~/whisper.cpp
cd ~/whisper.cpp && make -j
bash ./models/download-ggml-model.sh large-v3-turbo
```

### Ollama + qwen2.5:3b

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b
```

> 仓库内的 `Modelfile` 指向本地 `qwen2.5-3b-instruct-q4_k_m.gguf`（约 2GB，未随仓库分发）。
> 如需使用该文件，可从 [HuggingFace](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/blob/main/qwen2.5-3b-instruct-q4_k_m.gguf) 下载后执行 `ollama create qwen2.5:3b -f Modelfile`。

### udev 规则（免 sudo 访问 USB 设备）

创建 `/etc/udev/rules.d/99-respeaker.rules`：

```
SUBSYSTEM=="usb", ATTR{idVendor}=="2886", ATTR{idProduct}=="001a", MODE="0666"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## 使用方法

### 方式一：Web 界面（推荐）

```bash
cd src
python app.py
```

浏览器打开 `http://<板卡IP>:5000`，局域网内手机/电脑均可访问。

### 方式二：命令行

```bash
cd src
python meeting_assistant.py
```

按提示回车开始/停止录音，纪要自动保存至 `~/meeting-assistant/meetings/`。

## 目录结构

```
meeting-assistant/
├── src/
│   ├── app.py                # Flask Web 服务
│   ├── meeting_assistant.py  # 命令行主程序
│   ├── recorder.py           # arecord 封装 + reSpeaker 声卡自动发现
│   ├── doa.py                # reSpeaker Flex DoA 读取（USB 厂商协议）
│   ├── transcribe.py         # 声道提取（sox）+ whisper-cli 转写
│   ├── summarize.py          # Ollama API 摘要生成
│   └── static/index.html     # Web 前端
└── Modelfile                 # Ollama 模型定义
```

> 录音与纪要保存在 `~/meeting-assistant/recordings/` 与 `~/meeting-assistant/meetings/`（程序运行时自动创建），不入库。

## 常见问题

- **找不到声卡**：检查 `lsusb` 应看到 `2886:001a`；确认固件为 2 通道版（v2.1.0）
- **DoA 不可用**：确认 udev 规则已生效，普通用户可访问 USB 设备
- **转写失败**：确认 `~/whisper.cpp/build/bin/whisper-cli` 与模型文件存在
- **内存不足**：8GB 板子建议关闭浏览器等大程序；Whisper 与 LLM 分时运行，摘要完成后模型自动卸载

## 许可证

[MIT](LICENSE)
