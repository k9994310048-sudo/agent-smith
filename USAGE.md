# Usage Guide — Agent Smith

## Table of Contents

- [Starting Agent Smith](#starting-agent-smith)
- [Interfaces](#interfaces)
- [Configuration](#configuration)
- [Tools](#tools)
- [Cognitive Loop](#cognitive-loop)
- [IKKF Graph Memory](#ikkf-graph-memory)
- [Self-Healing](#self-healing)
- [Scheduled Tasks](#scheduled-tasks)
- [Logs and Monitoring](#logs-and-monitoring)
- [Stopping Agent Smith](#stopping-agent-smith)

---

## Starting Agent Smith

### Standard Start
```bash
cd agent-smith
source venv/bin/activate
./run-all.sh
```

### Manual Start (for debugging)
```bash
cd agent-smith
source venv/bin/activate
python3 main.py
```

### Start with systemd
```bash
sudo systemctl start agent-smith
```

### What Happens on Start

1. **Port cleanup** — kills any processes on ports 8766, 8767, 8768
2. **IKKF API** starts on port 8766 (graph memory)
3. **IKKF Web UI** starts on port 8767 (graph visualization)
4. **Agent Smith** initializes:
   - Loads configuration from `config.yaml`
   - Connects to LLM provider (API or local)
   - Initializes tool registry (7 tools)
   - Connects to IKKF graph database
   - Runs self-diagnostics
5. **Dashboard** starts on port 8768
6. **Telegram bot** starts listening for messages
7. **Cognitive loop** starts (background task processing)
8. **Morning delivery check** starts (hourly check for 7:00 AM delivery)

---

## Interfaces

### Telegram Bot

The primary interface for interacting with Agent Smith.

**Setup:**
1. Create a bot with @BotFather on Telegram
2. Get the bot token
3. Add token to `config.yaml` or `.env`
4. Start Agent Smith
5. Send a message to your bot

**Communication:**
- Send any message — Agent Smith will respond
- Long responses (>4000 chars) are split into multiple messages
- Markdown formatting is converted to Telegram HTML

**Tips:**
- Ask Agent Smith to search the internet: "Find latest news about AI"
- Ask about system status: "How are you?"
- Request file operations: "Read the README.md"
- Use voice messages (Whisper will transcribe)

### Web Dashboard

**URL:** http://localhost:8768

Real-time dashboard showing:
- Agent status (awake/idle/sleeping)
- System resources (CPU, RAM, disk)
- Recent activity
- Tool usage statistics

### IKKF Web UI

**URL:** http://localhost:8767

Graph visualization interface:
- Browse nodes and edges
- Search the knowledge graph
- View connections between facts
- Explore agent memory

### IKKF API

**URL:** http://localhost:8766

REST API for programmatic access:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/nodes` | GET | List nodes |
| `/nodes/{id}` | GET | Get node by ID |
| `/nodes` | POST | Create node |
| `/search` | GET | Search nodes |
| `/neighbors/{id}` | GET | Get neighboring nodes |
| `/stats` | GET | Graph statistics |

---

## Configuration

### config.yaml

Main configuration file. Copy from example:
```bash
cp config.yaml.example config.yaml
```

**Structure:**
```yaml
agent:
  name: Agent Smith
  owner: Your Name
  personality: helpful

models:
  primary:
    api_key: YOUR_API_KEY
    base_url: https://api.example.com/v1
    model: model-name
    provider: provider-name
    stream: true
  fallback:
    model: deepseek-r1-1.5b
    n_ctx: 2048
    n_threads: 2
    path: models/deepseek-r1-1.5b/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf
    provider: local
  routing:
    auto_failover: true
    resource_aware: true
    use_api: true

telegram:
  chat_id: YOUR_CHAT_ID
  token: YOUR_TELEGRAM_TOKEN
```

### Environment Variables

Create `.env` file for secrets:
```env
TELEGRAM_TOKEN=your_bot_token_here
```

### Personalities

Switch personalities by changing `agent.personality` in config:

- **helpful** (default) — polite, detailed responses
- **concise** — brief, to the point
- **creative** — unconventional thinking
- **technical** — deep, precise technical answers

---

## Tools

Agent Smith has 7 tools available:

### web_search

Search the internet for real-time information.

- **Usage:** "Search for latest AI news"
- **Returns:** Titles, URLs, and snippets from multiple search engines
- **Engines:** OpenSERP (Bing, Yandex, Google, DDG, Baidu) + Wikipedia fallback
- **No API key required** for fallback mode

### shell_exec

Execute bash commands (with security restrictions).

- **Forbidden:** rm, sudo, apt, pip install, git clone, wget, chmod, chown
- **Safe for:** ls, cat, grep, find, ps, df, free, etc.

### file_read

Read project files (up to 1500 characters).

- **Security:** Only files within the project directory can be accessed

### project_overview

List project directory structure.

### get_system_stats

Get real system statistics: uptime, CPU load, RAM usage, disk usage, CPU temperature.

### tts

Text-to-speech synthesis via edge-tts.

### whisper

Speech recognition from audio files via OpenAI Whisper.

---

## Cognitive Loop

Agent Smith runs an autonomous cognitive loop in the background.

### Dream Cycle

- **When:** Daily at 3:00 AM
- **What:** Agent generates creative ideas based on accumulated knowledge
- **Process:** Selects random facts from IKKF, sends to LLM with dream prompt, saves ideas to graph

### Idea Pipeline

- **When:** Daily at 6:00 AM
- **What:** Ranks and processes dreams into actionable ideas

### Morning Delivery

- **When:** Daily at 7:00 AM
- **What:** Sends the best idea of the day to Telegram

### Self-Correction

- **When:** Periodically
- **What:** Agent checks its own knowledge graph for contradictions

---

## IKKF Graph Memory

IKKF (Intelligent Knowledge Graph Framework) is Agent Smith long-term memory.

### Adding Facts

Facts are automatically extracted from conversations:
1. User sends a message
2. Agent responds
3. Fact extractor analyzes the conversation
4. New facts are added to the graph
5. Facts are automatically linked to related nodes

### Searching Memory

Agent searches memory before responding to augment its knowledge.

### Graph Visualization

Open http://localhost:8767 to see nodes, edges, and relationships.

---

## Self-Healing

Agent Smith monitors its own health and recovers from failures:

- Restarts crashed services
- Falls back to local model if API is unavailable
- Clears disk space if needed
- Reduces context length if out of memory

---

## Scheduled Tasks

| Task | Frequency | Description |
|------|-----------|-------------|
| IKKF Auto-save | Every 5 min | Save graph to disk |
| Backup | Daily 2:00 AM | Backup graph.db |
| Dream Cycle | Daily 3:00 AM | Generate dreams |
| Consolidation | Daily 4:00 AM | Merge similar facts |
| Idea Ranking | Daily 6:00 AM | Rank overnight ideas |
| Morning Delivery | Daily 7:00 AM | Send best idea to Telegram |

---

## Logs and Monitoring

### Log Files

| File | Description |
|------|-------------|
| `system.log` | Main agent log |
| `data/dream.log` | Dream generation log |
| `data/consolidation.log` | Memory consolidation log |

### View Logs

```bash
tail -f ~/.agent-smith/system.log
tail -f ~/.agent-smith/data/dream.log
```

### Health Check

```bash
curl http://127.0.0.1:8766/health
curl http://127.0.0.1:8768
```

---

## Stopping Agent Smith

### Graceful Stop
```bash
# If running in terminal
Ctrl+C

# If running as systemd service
sudo systemctl stop agent-smith
```

### Force Stop
```bash
pkill -f "python3 main.py"
fuser -k 8766/tcp 8767/tcp 8768/tcp
```

### Restart
```bash
sudo systemctl restart agent-smith
```
