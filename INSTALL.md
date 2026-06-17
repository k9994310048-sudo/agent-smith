# Installation Guide — Agent Smith

## Table of Contents

- [System Requirements](#system-requirements)
- [Quick Start](#quick-start)
- [Step-by-Step Installation](#step-by-step-installation)
  - [1. Clone Repository](#1-clone-repository)
  - [2. System Dependencies](#2-system-dependencies)
  - [3. Python Virtual Environment](#3-python-virtual-environment)
  - [4. Install Python Dependencies](#4-install-python-dependencies)
  - [5. Download LLM Models](#5-download-llm-models)
  - [6. Configure Agent Smith](#6-configure-agent-smith)
  - [7. (Optional) OpenSERP for Web Search](#7-openserp-for-web-search)
  - [8. (Optional) systemd Autostart](#8-systemd-autostart)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 22.04 / Debian 12 | Ubuntu 24.04 |
| CPU | 2 cores (x86_64) | 4 cores |
| RAM | 4 GB | 8+ GB |
| Disk | 10 GB free | 20+ GB free |
| Python | 3.10 | 3.11+ |
| GPU | Not required (CPU inference works) | NVIDIA with CUDA for faster inference |

**Note:** Agent Smith is designed to run on low-end hardware. It works on a 2012 MacBook Pro with i5-2435M and 16GB RAM.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/agent-smith.git
cd agent-smith

# 2. Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Download model (DeepSeek-R1 1.5B recommended)
mkdir -p models/deepseek-r1-1.5b
wget -O models/deepseek-r1-1.5b/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf \
  https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf

# 4. Configure
cp config.yaml.example config.yaml
# Edit config.yaml with your API keys and settings

# 5. Run
./run-all.sh
```

---

## Step-by-Step Installation

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/agent-smith.git
cd agent-smith
```

### 2. System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential curl git
```

**Optional — for TTS (text-to-speech):**
```bash
sudo apt install -y espeak-ng
```

**Optional — for Whisper (speech recognition):**
```bash
sudo apt install -y ffmpeg
```

### 3. Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

**Important:** Always activate the virtual environment before running Agent Smith:
```bash
source venv/bin/activate
```

### 4. Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Core dependencies:**
- `llama-cpp-python` — Local LLM inference
- `fastapi` + `uvicorn` — IKKF Graph API and Web UI
- `psutil` — System monitoring
- `duckduckgo-search` — Web search fallback
- `beautifulsoup4` — HTML parsing
- `python-telegram-bot` — Telegram integration
- `structlog` — Structured logging
- `pyyaml` — Configuration parsing
- `python-dotenv` — Environment variables
- `httpx` — Async HTTP client
- `chromadb` — Vector database (optional, for advanced search)

### 5. Download LLM Models

Agent Smith requires at least one local LLM model for fallback inference.

**Recommended: DeepSeek-R1 1.5B (Q4_K_M)**
- Size: ~1.1 GB
- RAM usage: ~1.5 GB
- Speed: ~5 tokens/sec on 2-core CPU

```bash
mkdir -p models/deepseek-r1-1.5b
wget -O models/deepseek-r1-1.5b/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf \
  https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf
```

**Alternative: Qwen 2.5 0.5B (Q4_K_M)**
- Size: ~0.5 GB
- RAM usage: ~0.7 GB
- Speed: ~20 tokens/sec on 2-core CPU

```bash
mkdir -p models/qwen2.5-1.5b
wget -O models/qwen2.5-1.5b/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf \
  https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf
```

**Update `config.yaml`** to point to your model:
```yaml
models:
  fallback:
    model: deepseek-r1-1.5b
    path: models/deepseek-r1-1.5b/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf
```

### 6. Configure Agent Smith

Copy the example configuration:
```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` with your settings:

**Required:**
- `models.primary.api_key` — Your LLM API key (or use local-only mode)
- `telegram.token` — Your Telegram bot token from @BotFather
- `telegram.chat_id` — Your Telegram chat ID

**Optional:**
- `agent.owner` — Your name
- `agent.personality` — `helpful`, `concise`, `creative`, or `technical`

**For local-only mode** (no API key needed):
Set `models.routing.use_api: false` and ensure you have a local model downloaded.

**Environment variables** (`.env` file):
```env
TELEGRAM_TOKEN=your_t...6. Configure Agent Smith

Copy the example configuration:
```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` with your settings:

**Required:**
- `models.primary.api_key` — Your LLM API key (or use local-only mode)
- `telegram.token` — Your Telegram bot token from @BotFather
- `telegram.chat_id` — Your Telegram chat ID

**Optional:**
- `agent.owner` — Your name
- `agent.personality` — `helpful`, `concise`, `creative`, or `technical`

**For local-only mode** (no API key needed):
Set `models.routing.use_api: false` and ensure you have a local model downloaded.

**Environment variables** (`.env` file):
```env
TELEGRAM_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### 7. OpenSERP for Web Search (Optional)

For multi-engine web search (Bing, Yandex, Google, DuckDuckGo, Baidu), install OpenSERP via Docker:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in for group changes

# Run OpenSERP
docker run -d \
  --name openserp \
  --restart always \
  -p 7000:7000 \
  karust/openserp
```

Verify:
```bash
curl http://127.0.0.1:7000/health
```

### 8. systemd Autostart (Optional)

To start Agent Smith automatically on boot:

```bash
# Copy service file
sudo cp deepseek-r1.service /etc/systemd/system/agent-smith.service

# Edit the service file to match your paths
sudo nano /etc/systemd/system/agent-smith.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable agent-smith
sudo systemctl start agent-smith

# Check status
sudo systemctl status agent-smith
```

**Note:** Edit the service file to set correct `User`, `WorkingDirectory`, and `ExecStart` paths.

---

## Verification

After starting Agent Smith, verify all components:

```bash
# Check IKKF API
curl http://127.0.0.1:8766/health

# Check IKKF Web UI
curl http://127.0.0.1:8767

# Check Dashboard
curl http://127.0.0.1:8768

# Check Telegram bot
# Send /start to your bot in Telegram

# View logs
tail -f ~/.agent-smith/system.log
```

**Expected output:**
- IKKF API: `{"status": "ok"}`
- Web UI: HTML page with graph visualization
- Dashboard: HTML page with agent status
- Telegram: Bot responds to messages

---

## Troubleshooting

### Port already in use
```bash
fuser -k 8766/tcp 8767/tcp 8768/tcp
```

### Model not found
- Check `config.yaml` path matches downloaded model
- Ensure file extension is `.gguf`

### Out of memory
- Use a smaller model (Qwen 0.5B instead of DeepSeek 1.5B)
- Reduce `n_ctx` in config (2048 instead of 4096)
- Close other applications

### Telegram not working
- Verify bot token with @BotFather
- Ensure `TELEGRAM_TOKEN` is set in `.env` or `config.yaml`
- Check internet connectivity

### Web search not working
- OpenSERP may not be running: `docker ps | grep openserp`
- Fallback (Wikipedia + DDG) works without Docker
- Check `OPEN_SERP_URL` in `agents/tools/web_search.py`

### TTS not working
```bash
pip install edge-tts
edge-tts --version
```

### Whisper not working
```bash
pip install openai-whisper
whisper --help
```

---

## Next Steps

- Read [USAGE.md](USAGE.md) for operation guide
- Read [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
