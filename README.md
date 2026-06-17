# 🤖 Agent Smith

**Autonomous AI Agent with Graph Memory, Self-Healing, and Cognitive Loop**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Linux](https://img.shields.io/badge/platform-linux-lightgrey.svg)](https://www.kernel.org/)

Agent Smith is a fully autonomous AI agent designed to run on low-end hardware. It features a graph-based memory system (IKKF), self-healing capabilities, multimodal interaction (text-to-speech, speech recognition), and a cognitive loop that generates ideas while you sleep.

> **Philosophy:** "If it works on trash, it works everywhere." — Designed for a 2012 MacBook Pro with i5-2435M and 16GB RAM.

---

## ✨ Features

### Core
- **🧠 Graph Memory (IKKF)** — SQLite-based knowledge graph with FTS5 search, automatic fact extraction, and contradiction detection
- **🔄 Cognitive Loop** — Autonomous dream cycle, idea generation, and self-correction
- **🛠️ 7 Tools** — Web search, shell execution, file reading, project overview, system stats, TTS, Whisper
- **🤖 Multi-LLM** — Primary API + local fallback with automatic failover
- **💬 Telegram Bot** — Full Telegram integration with long message splitting and Markdown-to-HTML conversion

### Advanced
- **🏥 Self-Healing** — Automatic service recovery, disk cleanup, OOM protection
- **🎭 Personalities** — helpful, concise, creative, technical
- **📊 Dashboard** — Real-time web dashboard for monitoring
- **🌐 IKKF Web UI** — Graph visualization and exploration
- **🗣️ Multimodal** — Text-to-speech (edge-tts) and speech recognition (Whisper)
- **🌙 Dream Cycle** — Generates ideas while you sleep, delivers best idea in the morning
- **📈 Performance Monitor** — Tracks response times, tool usage, error rates

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│              Agent Smith                         │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Perceive │→ │  Reason  │→ │   Act    │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       │              │              │             │
│       └──────────────┼──────────────┘             │
│                      │                            │
│  ┌───────────────────▼────────────────────┐      │
│  │           LLM Provider                  │      │
│  │  Primary: Cloud API (streaming)         │      │
│  │  Fallback: Local LLM (llama.cpp)        │      │
│  └───────────────────┬────────────────────┘      │
│                      │                            │
│  ┌───────────────────▼────────────────────┐      │
│  │           IKKF Bridge                   │      │
│  └───────────────────┬────────────────────┘      │
│                      │                            │
├──────────────────────┼────────────────────────────┤
│  ┌───────────────────▼────────────────────┐      │
│  │        IKKF Graph API (8766)            │      │
│  │  SQLite + FTS5 + Vector Search          │      │
│  └───────────────────┬────────────────────┘      │
│                      │                            │
│  ┌───────────────────▼────────────────────┐      │
│  │  Cognitive Loop (core_system.py)        │      │
│  │  • Dream cycle (3:00 AM)                │      │
│  │  • Consolidation (4:00 AM)              │      │
│  │  • Idea ranking (6:00 AM)               │      │
│  │  • Morning delivery (7:00 AM)           │      │
│  └─────────────────────────────────────────┘      │
│                                                   │
│  ┌─────────────────────────────────────────┐      │
│  │  Self-Healing (self_repair.py)          │      │
│  │  • Service diagnostics                  │      │
│  │  • Auto-restart                         │      │
│  │  • DB recovery from backup              │      │
│  └─────────────────────────────────────────┘      │
└─────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Ubuntu 22.04+ / Debian 12+
- Python 3.10+
- 4+ GB RAM
- 10+ GB disk space

### Installation

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/agent-smith.git
cd agent-smith

# 2. Create venv
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download model
mkdir -p models/deepseek-r1-1.5b
wget -O models/deepseek-r1-1.5b/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf \
  https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf

# 5. Configure
cp config.yaml.example config.yaml
# Edit config.yaml with your API keys

# 6. Run
./run-all.sh
```

### Verify

```bash
curl http://127.0.0.1:8766/health  # IKKF API
curl http://127.0.0.1:8768         # Dashboard
```

---

## 📁 Project Structure

```
agent-smith/
├── agents/              # Agent logic
│   ├── smith.py         # Main agent class
│   ├── llm_provider.py  # LLM routing (API + local)
│   ├── tool_registry.py # Tool management
│   ├── core_system.py   # Cognitive loop, performance monitor
│   ├── device_adapter.py # Hardware detection
│   ├── skill_learner.py # Skill acquisition
│   ├── tools/           # Tool implementations
│   │   ├── web_search.py    # Multi-engine search
│   │   ├── system_tools.py  # Shell, file, stats
│   │   └── media_tools.py   # TTS, Whisper
│   ├── autonomy/        # Self-healing, scheduler
│   ├── memory/          # Fact extraction, consolidation
│   ├── middleware/      # Rate limiting
│   ├── planner/         # Task planning
│   └── reasoning/       # Reflection
├── ikkf/                # Knowledge graph
│   ├── api.py           # REST API
│   ├── graph.py         # Graph operations
│   ├── storage.py       # SQLite storage
│   ├── node.py          # Node/Edge models
│   ├── webui.py         # Web UI
│   ├── dream_pipeline.py # Dream generation
│   └── consolidation.py # Memory consolidation
├── ikkf_sh/             # Skills layer (IKKF Shell)
│   ├── agents/          # Bot runner, orchestrator
│   ├── core/            # Deep search, planner, reasoning
│   ├── skills/          # Skill system
│   └── verification/    # Fact verification
├── web/                 # Dashboard
│   └── dashboard.py     # FastAPI dashboard
├── integrations/        # External integrations
│   └── telegram.py      # Telegram bot
├── scripts/             # Utility scripts
├── tests/               # Test suite
│   ├── test_basic.py    # Basic tests
│   └── test_v50.py      # v5.0 tests (16 tests)
├── models/              # LLM models (not included, download separately)
├── config.yaml          # Configuration
├── requirements.txt     # Python dependencies
├── run-all.sh           # Unified startup script
├── Dockerfile           # Docker support
└── docker-compose.yml   # Docker Compose
```

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [INSTALL.md](INSTALL.md) | Detailed installation guide |
| [USAGE.md](USAGE.md) | Operation guide |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Technical architecture |
| [ROADMAP.md](ROADMAP.md) | Development roadmap |

---

## 🧪 Running Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

**Test coverage:**
- Web search (OpenSERP + fallback)
- IKKF graph operations
- Fact verification
- Memory awareness
- Tool registry
- KungFu LLM (dream pipeline)

---

## 🔧 Configuration

### config.yaml

```yaml
agent:
  name: Agent Smith
  owner: Your Name
  personality: helpful  # helpful, concise, creative, technical

models:
  primary:
    api_key: YOUR_API_KEY
    base_url: https://api.example.com/v1
    model: your-model
    provider: your-provider
  fallback:
    model: deepseek-r1-1.5b
    path: models/deepseek-r1-1.5b/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf
    n_ctx: 2048
    n_threads: 2

telegram:
  token: YOUR_TELEGRAM_TOKEN
  chat_id: YOUR_CHAT_ID
```

### Environment Variables (.env)

```env
TELEGRAM_TOKEN=*** Models

| Model | Size | RAM | Speed | Quality |
|-------|------|-----|-------|---------|
| DeepSeek-R1 1.5B Q4_K_M | 1.1 GB | 1.5 GB | ~5 t/s | Good |
| Qwen 2.5 0.5B Q4_K_M | 0.5 GB | 0.7 GB | ~20 t/s | Basic |

---

## 🛠️ Tools

| Tool | Description |
|------|-------------|
| `web_search` | Multi-engine search (OpenSERP + Wikipedia + DDG) |
| `shell_exec` | Execute bash commands (with security restrictions) |
| `file_read` | Read project files |
| `project_overview` | List project structure |
| `get_system_stats` | CPU, RAM, disk, temperature |
| `tts` | Text-to-speech (edge-tts) |
| `whisper` | Speech recognition (Whisper) |

---

## 🌙 Dream Cycle

Agent Smith generates ideas while you sleep:

1. **3:00 AM** — Dream cycle: generates creative ideas from accumulated knowledge
2. **4:00 AM** — Consolidation: merges similar facts, removes duplicates
3. **6:00 AM** — Idea ranking: scores and ranks overnight ideas
4. **7:00 AM** — Morning delivery: sends best idea to Telegram

---

## 🏥 Self-Healing

Agent Smith monitors and recovers from failures:

- **Service monitoring** — Checks IKKF API, model availability
- **Auto-restart** — Restarts crashed services
- **Disk cleanup** — Removes old logs and temp files
- **DB recovery** — Restores graph from backup if corrupted
- **OOM protection** — Reduces context length on memory pressure

---

## 📊 Dashboard

Access the web dashboard at http://localhost:8768:

- Agent status (awake/idle/sleeping)
- System resources (CPU, RAM, disk)
- Tool usage statistics
- Recent activity log

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Write tests for new features
4. Submit a pull request

---

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [llama.cpp](https://github.com/ggerganov/llama.cpp) — Local LLM inference
- [OpenSERP](https://github.com/karust/openserp) — Multi-engine search
- [edge-tts](https://github.com/rany2/edge-tts) — Text-to-speech
- [OpenAI Whisper](https://github.com/openai/whisper) — Speech recognition
- [FastAPI](https://fastapi.tiangolo.com/) — Web framework

---

*Built with ❤️ for the AI agent community.*
