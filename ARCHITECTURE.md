# Agent Smith + IKKF Integration — Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   main.py (Entry Point)                     │
│                   - Start IKKF API on :8766                │
│                   - Initialize Agent Smith                  │
│                   - Run Telegram Bot                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌───────────────────┐       ┌────────────────────┐
│   IKKF Graph API  │       │   Agent Smith      │
│  (FastAPI :8766)  │       │   - LLMProvider    │
│  - Nodes CRUD     │       │   - Process msg    │
│  - Hybrid search  │       │   - Extract facts  │
│  - RAG pipeline   │       │   - Dream cycle    │
│  - Cognitive loop │       │   - Skills mgmt    │
└─────────┬─────────┘       └────────┬───────────┘
          │                         │
          │  IKKFBridge            │ (uses)
          │  ├─ search()           │
          │  ├─ store()            │
          │  ├─ context()          │
          │  └─ health()           │
          │                         │
          └────────────┬────────────┘
                       │
                 ┌─────▼─────┐
                 │  SQLite   │
                 │ graph.db  │
                 └───────────┘
```

## Key Components

### 1. **LLMProvider** (`agents/llm_provider.py`)
- Local GGUF model: Qwen2.5-1.5B
- External API support (OpenRouter, OpenAI, etc.)
- Mode detection: local vs api

### 2. **AgentSmith** (`agents/smith.py`)
- Main agent class with PRAL cycle (Perceive → Reason → Act → Learn)
- Integrates IKKFBridge for context retrieval
- Auto-stores new facts in IKKF graph
- Config-driven (local model by default, API optional)

### 3. **IKKFBridge** (`agents/ikkf_bridge.py`)
- HTTP client to IKKF Graph API
- Methods:
  - `search(query)` - hybrid search (BM25 + vector + importance)
  - `store(content, type, importance, tags)` - save nodes
  - `context(query)` - RAG pipeline with graph expansion
  - `ideas()` - fetch generated ideas from dreams
  - `health()` - API health check

### 4. **IKKF Graph API** (`ikkf/graph/api.py`)
- FastAPI server on port 8766
- Features:
  - 7 node types (fact, concept, action, idea, entity, event, project)
  - 8 edge types (semantic, temporal, causal, etc.)
  - Context dimensions (temporal, spatial, emotional, semantic)
  - Hybrid search with RRF fusion
  - Optional cross-encoder reranking
  - SQLite-only storage (~10 MB)

### 5. **Cognitive Loop** (`ikkf/graph/`)
- **Dreams** (`ikkf_dream.py`): Generate creative connections from random facts
- **Idea Rank** (`ikkf_idea_rank.py`): Rate ideas on coherence/value/feasibility
- **RAG Pipeline** (`ikkf_graph_rag.py`): Context expansion via BFS
- **Auto-save** (`ikkf_auto_save.py`): Periodic graph consolidation

## Data Flow

### Message Processing
```
User Message
    ↓
[Agent Smith]
    ├─ Search IKKF for context
    │  └─ IKKFBridge.search(msg)
    │     └─ IKKF API /search/hybrid
    │
    ├─ Build system prompt with context
    │
    ├─ Call LLM (local or API)
    │
    └─ Extract facts
       └─ Store in IKKF
          └─ IKKFBridge.store(fact)
             └─ IKKF API /node POST

Response → User (via Telegram)
```

### Cognitive Cycle (Nightly)
```
[ikkf_cognitive_loop.py]
    ├─ Dream phase
    │  └─ Pick N random facts
    │     └─ Generate creative story (LLM)
    │        └─ Save as idea node
    │
    └─ Idea ranking phase
       └─ For each dream/idea
          ├─ Score on 3 axes (coherence, value, feasibility)
          └─ Save ranking metadata
```

## Configuration

### config.json
```json
{
  "telegram_token": "YOUR_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID",
  "owner_name": "Your Name",
  "agent_name": "Agent Smith",
  
  "local_model_path": "models/qwen2.5-1.5b/qwen2.5-1.5b-instruct-q4_k_m.gguf",
  "use_api": false,
  
  "api_key": "",
  "api_url": "https://openrouter.ai/api/v1",
  "model": "openai/gpt-oss-20b:free",
  
  "ikkf_enabled": true,
  "ikkf_api_url": "http://127.0.0.1:8766"
}
```

## Running the System

### 1. Start everything
```bash
cd /home/mac/.agent-smith
source venv/bin/activate
python3 main.py
```

This automatically:
- Starts IKKF Graph API on :8766
- Initializes Agent Smith
- Connects IKKFBridge
- Starts Telegram bot

### 2. Start IKKF API only
```bash
./start-ikkf-api.sh
```

### 3. Run dream cycle (for cron)
```bash
python3 main.py --dream
```

## Directory Structure

```
/home/mac/.agent-smith/
├── main.py                      # Entry point with auto-start IKKF
├── config.json                  # Configuration
├── memory.json                  # Local JSON memory
├── data/
│   └── graph.db                 # IKKF SQLite database
│
├── agents/
│   ├── smith.py                 # Main Agent Smith
│   ├── llm_provider.py           # LLM abstraction (local + API)
│   ├── ikkf_bridge.py            # Bridge to IKKF API
│   └── __init__.py
│
├── ikkf/                         # IKKF Graph module (from ikkf-github)
│   ├── graph/
│   │   ├── api.py               # FastAPI server
│   │   ├── graph.py             # Graph data structure
│   │   ├── node.py              # Node/Edge classes
│   │   ├── storage.py           # SQLite layer
│   │   ├── graph_rag.py         # RAG pipeline
│   │   ├── ikkf_dream.py        # Dream generation
│   │   ├── ikkf_idea_rank.py    # Idea ranking
│   │   ├── reranker.py          # Optional cross-encoder
│   │   ├── fill_context.py      # Context enrichment
│   │   └── [other scripts]
│   └── __init__.py
│
├── integrations/
│   ├── telegram.py               # Telegram Bot
│   └── __init__.py
│
├── skills/                       # User-defined skills (JSON)
├── models/
│   └── qwen2.5-1.5b/            # Local LLM (GGUF format)
│       └── qwen2.5-1.5b-instruct-q4_k_m.gguf
│
├── start.sh                      # Simple venv+python launcher
├── start-ikkf-api.sh            # Launch IKKF Graph API on :8766
└── venv/                         # Python virtual environment
```

## Dependencies

### Core (already installed)
- Python 3.12
- llama-cpp-python (for GGUF loading)
- fastapi, uvicorn (for IKKF API)
- python-telegram-bot (for Telegram)

### Optional
- chromadb (for old IKKF migration)
- sentence-transformers (for embedding fallback)
- torch (for better reranking)

## Integration Checklist

✅ IKKFBridge created in agents/ikkf_bridge.py
✅ IKKF Graph API integrated via HTTP
✅ AgentSmith uses IKKF.search() for context
✅ AgentSmith.extract_facts() stores in IKKF
✅ main.py auto-starts IKKF API on port 8766
✅ config.json updated with ikkf_enabled flag
✅ start-ikkf-api.sh created for manual start
✅ Health checks before agent initialization

## Next Steps

### Optional Enhancements
1. Add dream scheduler (cron job for nightly cognitive loop)
2. Implement Telegram commands: /dream, /ideas, /memory-stats
3. Add skill loading from IKKF nodes
4. Connect to IKKF web UI (localhost:8766/ui)
5. Export memory to JSON/CSV
6. Multi-project organization in IKKF
7. Backup/restore functionality

### Testing
```bash
# Check IKKF health
curl http://127.0.0.1:8766/health

# Search test
curl "http://127.0.0.1:8766/search/hybrid?q=test&limit=5"

# Stats
curl http://127.0.0.1:8766/stats
```

## Notes

- Local model runs ~200ms/token on CPU (Qwen2.5-1.5B)
- IKKF database grows ~50KB per 100 facts
- Context window management is automatic
- No external API calls needed (unless use_api=true)
- All data stays local unless explicitly exported
