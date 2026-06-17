#!/usr/bin/env python3
"""
IKKF Dream — генерация снов из графа знаний.
Использует DeepSeek-R1 через llama-server API.

Запуск:
  python3 ikkf_dream.py --once      # один сон
  python3 ikkf_dream.py --dry-run   # только показать
  python3 ikkf_dream.py --facts 5   # количество фактов
"""
import os
import sys
import json
import re
import time
import random
import urllib.request
from datetime import datetime

# ---- Config ----
IKKF_API = "http://127.0.0.1:8766"
LLAMA_SERVER_URL = "http://127.0.0.1:8081"
LOG_FILE = os.path.expanduser("~/.agent-smith/data/dream.log")

EXCLUDE_PROJECTS = {
    "conversation-log", "project_conclusion-log",
    "auto-rules", "python-book", "dreams"
}
EXCLUDE_PREFIXES = ("book:", "hermes-memory")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- Logging ----

def log(msg):
    ts = datetime.utcnow().isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ---- IKKF API ----

def ikkf_post(path, data):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        f"{IKKF_API}{path}",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def ikkf_get(path):
    with urllib.request.urlopen(f"{IKKF_API}{path}", timeout=15) as r:
        return json.loads(r.read())

# ---- Local LLM ----

def call_llm(user_prompt, max_tokens=512, temperature=0.85):
    payload = {
        "model": "DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf",
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{LLAMA_SERVER_URL}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read())
    text = resp["choices"][0]["message"]["content"].strip()
    # Убрать thinking-блок DeepSeek-R1
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
    return text

# ---- Fact selection ----

def is_good_fact(node):
    c = (node.get("content") or "").strip()
    if len(c) < 25 or len(c) > 400:
        return False
    if node.get("project", "") in EXCLUDE_PROJECTS:
        return False
    s = node.get("source", "") or ""
    if any(s.startswith(p) for p in EXCLUDE_PREFIXES):
        return False
    lo = c.lower()
    if lo.startswith("[page"):
        return False
    if " user:" in lo[:30] or lo.startswith(("user:", "assistant:")):
        return False
    return True

def pick_facts(n=4):
    pool = []
    for ntype in ("fact", "concept", "idea", "skill", "event"):
        try:
            data = ikkf_get(f"/nodes?node_type={ntype}&limit=200")
            pool.extend(data.get("nodes", []))
        except Exception as e:
            log(f"fetch {ntype}: {e}")
    good = [x for x in pool if is_good_fact(x)]
    if len(good) < 2:
        return []
    random.shuffle(good)
    picked, used_proj = [], set()
    # Сначала из разных проектов
    for node in good:
        p = node.get("project", "default")
        if p not in used_proj:
            picked.append(node)
            used_proj.add(p)
        if len(picked) >= n:
            break
    # Добираем если не хватило
    for node in good:
        if node not in picked:
            picked.append(node)
        if len(picked) >= n:
            break
    return picked[:n]

# ---- Dream generation ----

def generate_dream(facts):
    lines = []
    for f in facts:
        c = f.get("content", "")[:200]
        lines.append(f"- {c}")
    facts_block = "\n".join(lines)

    dream_prompt = (
        "You are a sleeping AI mind. At night, you blend fragments of memory into a short surreal dream.\n\n"
        "RULES:\n"
        "- Exactly 3-4 sentences, no more\n"
        "- Figurative, associative style — like a real dream\n"
        "- Do NOT retell facts, do NOT explain\n"
        "- Forbidden: \"This dream symbolizes\", \"Explanation:\", numbering\n\n"
        f"Memory fragments:\n{facts_block}\n\n"
        "Dream (3-4 sentences):"
    )

    try:
        raw = call_llm(dream_prompt, max_tokens=512, temperature=0.85)
    except Exception as e:
        log(f"dream gen error: {e}")
        return None, None

    dream = raw.strip()
    if not dream or len(dream) < 30:
        return None, None

    # Извлечь идею
    insight = None
    try:
        ip = (
            "Read this dream and extract ONE concrete action idea — "
            "what could be done differently. Format: What if [action]. "
            "One sentence. If no idea, answer: none\n\n"
            f"Dream: {dream[:400]}\n\nIdea:"
        )
        raw2 = call_llm(ip, max_tokens=256, temperature=0.5)
        ins = raw2.split("\n")[0].strip()
        ins = re.sub(r"[\.\s]+(нет|no|none)\s*$", "", ins, flags=re.IGNORECASE).strip()
        if not ins.lower().startswith(("нет", "no", "none")) and len(ins) >= 8:
            insight = ins
    except Exception:
        pass

    return dream, insight

# ---- Save ----

def save_dream(dream, insight, facts, dry_run=False):
    day = datetime.utcnow().isoformat()[:10]
    source_ids = [str(f.get("id", ""))[:8] for f in facts]

    payload = {
        "content": dream,
        "node_type": "idea",
        "importance": 0.4,
        "tags": ["dream", "self-learning"],
        "project": "dreams",
        "metadata": {"source_facts": source_ids, "insight": insight or ""},
        "context": {
            "semantic": "сон",
            "social": "ikkf",
            "temporal": day,
            "emotional": "neutral",
            "spatial": "dream",
        },
    }

    if dry_run:
        log("[DRY-RUN] сон не сохранён")
        return None

    try:
        r = ikkf_post("/node", payload)
        did = r.get("id") or (r.get("node") or {}).get("id")
        log(f"Сон сохранён id={str(did)[:8]}")
        if insight:
            ikkf_post("/node", {
                "content": insight,
                "node_type": "idea",
                "importance": 0.5,
                "tags": ["dream-insight", "self-learning"],
                "project": "dreams",
                "metadata": {"from_dream": str(did)},
                "context": {
                    "semantic": "идея-из-сна",
                    "social": "ikkf",
                    "temporal": day,
                    "spatial": "dream",
                },
            })
            log(f"Идея: {insight[:80]}")
        return did
    except Exception as e:
        log(f"save error: {e}")
        return None

# ---- Main ----

def run_once(n_facts=4, dry_run=False):
    log("=== IKKF Dream start ===")
    facts = pick_facts(n_facts)
    if len(facts) < 2:
        log("Недостаточно фактов")
        return None
    log(f"Фактов: {len(facts)}")
    for f in facts:
        log(f"  [{f.get('project','')}] {f.get('content','')[:60]}")

    dream, insight = generate_dream(facts)
    if not dream:
        log("Сон не сгенерирован")
        return None

    log(f"СОН: {dream[:120]}")
    if insight:
        log(f"ИДЕЯ: {insight[:80]}")

    save_dream(dream, insight, facts, dry_run=dry_run)
    log("=== IKKF Dream done ===")
    return {"dream": dream, "insight": insight, "facts": facts}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="IKKF Dream generator")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--facts", type=int, default=4)
    args = parser.parse_args()
    run_once(args.facts, dry_run=args.dry_run)
