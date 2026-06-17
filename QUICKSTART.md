# Quick Start — Agent Smith + IKKF

## 🚀 First Time Setup

```bash
cd /home/mac/.agent-smith

# Run setup
python3 main.py --setup

# This will ask for:
# - Your name
# - Telegram Bot Token (from @BotFather)
# - Telegram Chat ID (optional, for morning reports)
# - Local model path (auto-detected)
# - API key (optional, for switching to external LLM)
```

## ▶️ Run the Full System

```bash
cd /home/mac/.agent-smith
python3 main.py
```

This will:
1. ✅ Auto-start IKKF Graph API on port 8766
2. ✅ Initialize Agent Smith with local Qwen2.5-1.5B
3. ✅ Connect IKKFBridge to IKKF API
4. ✅ Start Telegram Bot
5. ✅ Wait for messages

The system **defaults to local model**. IKKF is enabled by default.

## 📊 Test IKKF API

While system is running, in another terminal:

```bash
# Check health
curl http://127.0.0.1:8766/health
# Expected: {"status":"ok","service":"ikkf-graph-api","version":"1.0"}

# Search test
curl "http://127.0.0.1:8766/search/hybrid?q=python&limit=3"
# Returns: {"results":[...], "total":...}

# Get stats
curl http://127.0.0.1:8766/stats
# Shows: nodes count, edges count, avg importance, etc.
```

## 💬 Test via Telegram

Send to your bot:
```
Hello! What's my name?
```

Expected response (bot will use memory):
```
Hi [owner_name]! I'm Agent Smith with infinite memory.
I remember everything you tell me.
```

The agent will:
1. Search IKKF for related facts
2. Build context
3. Call local LLM
4. Extract and store new facts
5. Return answer

## 🔄 Optional: Run Dream Cycle

Generate ideas from facts in memory:

```bash
python3 main.py --dream
```

This:
1. ✨ Generates a "dream" by combining random facts creatively
2. 💡 Creates ideas from dreams
3. 📤 Sends morning report to Telegram (if chat_id is set)

For automated nightly dreams, add to crontab:
```bash
# 2 AM every night
0 2 * * * cd /home/mac/.agent-smith && python3 main.py --dream
```

## 🔑 Switch to External LLM

### Option 1: Via Telegram
Send to bot:
```
/api sk-or-v1-YOUR_OPENROUTER_KEY
```

### Option 2: Edit config
```bash
# Stop the agent first
# Edit ~/.agent-smith/config.json:
{
  "api_key": "sk-or-v1-...",
  "api_url": "https://openrouter.ai/api/v1",
  "model": "openai/gpt-4:free",
  "use_api": true  # Switch to API
}

# Restart
python3 main.py
```

To switch back to local:
```json
{
  "use_api": false
}
```

## 📁 File Locations

- **Config**: `~/.agent-smith/config.json`
- **Memory**: `~/.agent-smith/memory.json`
- **IKKF DB**: `~/.agent-smith/data/graph.db`
- **Agent code**: `/home/mac/.agent-smith/agents/`
- **IKKF API code**: `/home/mac/.agent-smith/ikkf/graph/`

## 🛠️ Manual Operations

### Start only IKKF API
```bash
./start-ikkf-api.sh
# Runs on http://127.0.0.1:8766
```

### Check agent status
```bash
python3 main.py --status
# Prints config (no secrets)
```

### View memory
```bash
cat ~/.agent-smith/memory.json | python3 -m json.tool
```

### Query IKKF directly
```python
from agents.ikkf_bridge import IKKFBridge

bridge = IKKFBridge()
results = bridge.search("python programming")
print(results)

# Store a fact
node_id = bridge.store(
    content="Python is a great language",
    node_type="fact",
    importance=0.8,
    tags=["programming", "python"]
)
```

## ⚠️ Common Issues

### "IKKF API not available"
- Check: `curl http://127.0.0.1:8766/health`
- Try: `./start-ikkf-api.sh` in another terminal
- Agent will continue in offline mode (uses local memory only)

### "Qwen model not found"
- Check: `ls -la models/qwen2.5-1.5b/`
- Expected file: `qwen2.5-1.5b-instruct-q4_k_m.gguf` (~1.5 GB)

### "Telegram bot not responding"
- Check token: `python3 main.py --status`
- Verify token with: `curl "https://api.telegram.org/botTOKEN/getMe"`
- Make sure chat_id is set in config

### "Port 8766 already in use"
- Kill existing: `fuser -k 8766/tcp`
- Then restart: `./start-ikkf-api.sh`

## 📚 Learn More

- [ARCHITECTURE.md](ARCHITECTURE.md) — System design and components
- [agents/smith.py](agents/smith.py) — Agent logic
- [agents/ikkf_bridge.py](agents/ikkf_bridge.py) — IKKF integration
- [ikkf/graph/README.md](ikkf/graph/README.md) — IKKF documentation

## 🎯 Next Steps

1. ✅ Run setup: `python3 main.py --setup`
2. ✅ Test: Send message to bot
3. ✅ Monitor: Check `/health` endpoint
4. ✅ Schedule dreams: Add cron job
5. ✅ Optional: Switch to external LLM if desired

Enjoy! 🚀
