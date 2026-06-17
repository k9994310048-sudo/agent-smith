#!/usr/bin/env python3
"""
Dream Pipeline — полный конвейер от снов до проектов.

Объединяет:
  - Оценку идей (из idea_pipeline.py)
  - Ранжирование (сортировка по score, топ-N)
  - Проект-карточки (goal, steps, resources, risks)
  - Утреннюю доставку в Telegram

Запуск:
  python3 dream_pipeline.py --once           # полный цикл
  python3 dream_pipeline.py --dry-run        # только показать
  python3 dream_pipeline.py --review         # обзор всех проектов
  python3 dream_pipeline.py --top 3          # топ-N идей (по умолчанию 3)
"""

import os
import sys
import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime

# ---- Config ----
IKKF_API = "http://127.0.0.1:8766"
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'dream-pipeline.log')
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'dream-pipeline-progress.json')

DEFAULT_THRESHOLD = 65
DEFAULT_TOP_N = 3

# Активные проекты — для оценки связи
ACTIVE_PROJECTS = [
    "IKKF", "OWL", "робот", "affiliate", "партнёр", "доход",
    "память", "агент", "граф", "бизнес", "telegram", "сайт",
    "магазин", "бот", "поиск", "сравнение"
]

# ---- Logging ----
def log(msg):
    ts = datetime.now().isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
    except:
        pass

# ---- IKKF API ----
def ikkf_post(path, data):
    url = f"{IKKF_API}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def ikkf_get(path):
    with urllib.request.urlopen(f"{IKKF_API}{path}", timeout=15) as r:
        return json.loads(r.read())

def ikkf_patch_node(node_id, fields):
    url = f"{IKKF_API}/node/{node_id}"
    body = json.dumps(fields).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

# ---- LLM ----
_llm = None

def get_llm():
    global _llm
    if _llm is None:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from kungfu_llm import get_llm as _kf_get_llm
            _llm = _kf_get_llm()
            _ = _llm.llm
        except Exception as e:
            log(f"LLM unavailable: {e}")
            _llm = False
    return _llm or None

def _ask(llm, prompt, max_tokens=300, temperature=0.3):
    resp = llm.llm(prompt, max_tokens=max_tokens, temperature=temperature,
                   repeat_penalty=1.2, top_p=0.9,
                   stop=["</s>", "Human:", "User:"])
    return resp["choices"][0]["text"].strip()

def _extract_json(text):
    m = re.search(r'\{.*\}', text, re.DOTALL)
    return m.group() if m else ""

# ---- Evidence ----
def count_supporting_facts(idea_text):
    try:
        q = urllib.parse.quote(idea_text[:120])
        res = ikkf_get(f"/search?q={q}&limit=10")
        results = res.get("results", [])
        support = 0
        for r in results:
            node = r.get("node", r)
            proj = node.get("project", "")
            if proj in ("dreams", "dct", "lmtai", "parked", "to-discuss"):
                continue
            score = r.get("score", 0)
            if score and score > 0.01:
                support += 1
        return min(support, 10)
    except Exception as e:
        log(f"  evidence error: {e}")
        return 0

def project_relevance(idea_text):
    low = idea_text.lower()
    hits = sum(1 for kw in ACTIVE_PROJECTS if kw.lower() in low)
    return min(hits / 3.0, 1.0)

# ---- Scoring ----
def score_idea(idea_text):
    llm = get_llm()
    coherence = 0.5
    value_kind = "неясна"
    feasibility = "неясно"
    reasoning = ""
    value_model = 0.5

    if llm is not None:
        prompt = f"""Оцени идею для предпринимателя. Ответь ТОЛЬКО валидным JSON.

Идея: "{idea_text[:300]}"

Оцени:
- coherence: 0.0-1.0, насколько это осмысленная связная идея
- value_kind: "деньги" / "социальная" / "личная" / "нет"
- value: 0.0-1.0, насколько идея полезна (любая польза)
- feasibility: "наши_инструменты" / "внешние_инструменты" / "неясно"
- reason: краткое обоснование одним предложением

JSON: {{"coherence": 0.0, "value_kind": "...", "value": 0.0, "feasibility": "...", "reason": "..."}}"""
        try:
            raw = _ask(llm, prompt, max_tokens=250, temperature=0.2)
            js = _extract_json(raw)
            if js:
                data = json.loads(js)
                coherence = float(data.get("coherence", 0.5))
                value_kind = data.get("value_kind", "неясна")
                value_model = float(data.get("value", 0.5))
                feasibility = data.get("feasibility", "неясно")
                reasoning = (data.get("reason", "") or "").strip()
        except Exception as e:
            log(f"  score LLM error: {e}")

    coherence = min(1.0, max(0.0, coherence))
    value_model = min(1.0, max(0.0, value_model))

    support = count_supporting_facts(idea_text)
    realism = min(support / 4.0, 1.0)
    proj_rel = project_relevance(idea_text)

    value = value_model if value_kind != "нет" else value_model * 0.3
    total = (coherence * 0.30 + value * 0.30 + realism * 0.25 + proj_rel * 0.15) * 100

    return {
        "total": round(total, 1),
        "coherence": round(coherence, 2),
        "value": round(value, 2),
        "value_kind": value_kind,
        "realism": round(realism, 2),
        "support_facts": support,
        "project_relevance": round(proj_rel, 2),
        "feasibility": feasibility,
        "reason": reasoning,
    }

# ---- Project Card ----
def generate_project_card(idea_text, score=None):
    """Сгенерировать проект-карточку: goal, steps, resources, risks.
    idea_text может быть строкой или словарем от rank_ideas."""
    # Handle dict input from rank_ideas
    if isinstance(idea_text, dict):
        idea_str = idea_text.get("idea", idea_text.get("content", str(idea_text)))
        score = idea_text.get("score", score)
    else:
        idea_str = str(idea_text)

    llm = get_llm()
    if llm is None:
        return {
            "goal": idea_str[:200],
            "steps": ["Определить детали", "Реализовать", "Проверить"],
            "resources": ["Время", "Инструменты"],
            "risks": ["Неизвестно"],
        }

    prompt = f"""Для этой идеи создай проект-карточку. Ответь ТОЛЬКО валидным JSON.

Идея: "{idea_str[:300]}"

JSON формат:
{{
  "goal": "одна фраза — что хотим достичь",
  "steps": ["шаг 1", "шаг 2", "шаг 3"],
  "resources": ["ресурс 1", "ресурс 2"],
  "risks": ["риск 1", "риск 2"]
}}

JSON:"""
    try:
        raw = _ask(llm, prompt, max_tokens=300, temperature=0.4)
        js = _extract_json(raw)
        if js:
            card = json.loads(js)
            # Валидация
            for key in ["goal", "steps", "resources", "risks"]:
                if key not in card:
                    card[key] = [] if key != "goal" else idea_text[:200]
            return card
    except Exception as e:
        log(f"  card LLM error: {e}")

    return {
        "goal": idea_text[:200],
        "steps": ["Определить детали", "Реализовать", "Проверить"],
        "resources": ["Время", "Инструменты"],
        "risks": ["Неизвестно"],
    }

# ---- Hypothesis ----
def build_hypothesis(idea_text, score):
    llm = get_llm()
    if llm is None:
        return f"Если реализовать: «{idea_text[:150]}» — возможен полезный результат."

    prompt = f"""Построй короткую гипотезу: «Если [действие], то [результат], потому что [причина]». Одно-два предложения. Конкретно.

Идея: "{idea_text[:300]}"

Гипотеза:"""
    try:
        h = _ask(llm, prompt, max_tokens=150, temperature=0.4).strip()
        h = h.split("\n")[0].strip()
        return h if len(h) > 15 else f"Если реализовать «{idea_text[:120]}» — возможен полезный результат."
    except:
        return f"Если реализовать «{idea_text[:120]}» — возможен полезный результат."

# ---- Tool check ----
def tool_check(score):
    feas = score.get("feasibility", "неясно")
    if feas == "наши_инструменты":
        return "lmtai", "реализуемо нашими инструментами"
    elif feas == "внешние_инструменты":
        return "parked", "нужны внешние инструменты — отложено"
    else:
        return "lmtai", "реализуемость неясна — решение за User"

# ---- Ranking + Card generation ----
def rank_ideas(ideas, threshold=DEFAULT_THRESHOLD, top_n=DEFAULT_TOP_N, dry_run=False):
    """Оценить, отранжировать, сгенерировать карточки для топ-N идей."""
    scored = []
    for node in ideas:
        idea_text = node.get("content", "")
        score = score_idea(idea_text)
        scored.append((score, node))

    # Сортировка по total score (убывание)
    scored.sort(key=lambda x: -x[0]["total"])

    results = []
    for score, node in scored:
        idea_text = node.get("content", "")
        hypothesis = build_hypothesis(idea_text, score)
        target, tool_reason = tool_check(score)

        # Генерировать карточку только для топ-N или DCT
        card = None
        if score["total"] >= threshold or len(results) < top_n:
            card = generate_project_card(idea_text, score)

        result = {
            "node_id": node.get("id"),
            "idea": idea_text,
            "score": score,
            "hypothesis": hypothesis,
            "target": target,
            "tool_reason": tool_reason,
            "card": card,
        }
        results.append(result)

        # Сохранить в IKKF
        if not dry_run:
            tags = list(set((node.get("tags") or []) + ["dream-insight", target]))
            meta = {
                "score": score,
                "hypothesis": hypothesis,
                "tool_check": tool_reason,
                "routed_at": datetime.now().isoformat(),
            }
            if card:
                meta["card"] = card
            ikkf_patch_node(node.get("id"), {
                "project": target,
                "tags": tags,
                "metadata": {**(node.get("metadata") or {}), **meta},
            })

    return results

# ---- Morning Delivery ----
def format_morning_message(results, top_n=DEFAULT_TOP_N):
    """Форматировать утреннее сообщение для Telegram."""
    lines = []
    lines.append("🌅 Доброе утро, User!")
    lines.append("")
    lines.append("Вот что я придумал ночью:")
    lines.append("")

    for i, r in enumerate(results[:top_n]):
        score = r["score"]
        card = r.get("card", {})

        lines.append(f"💡 #{i+1} — {score['total']}%")
        lines.append(f"   {r['idea'][:120]}")
        lines.append(f"   🔬 {r['hypothesis']}")

        if card:
            lines.append(f"   🎯 Цель: {card.get('goal', '')[:100]}")
            steps = card.get('steps', [])
            if steps:
                lines.append(f"   📋 Шаги: {', '.join(steps[:3])}")
            risks = card.get('risks', [])
            if risks:
                lines.append(f"   ⚠️ Риски: {', '.join(risks[:2])}")

        lines.append(f"   → {r['target'].upper()} ({r['tool_reason']})")
        lines.append("")

    lines.append("---")
    lines.append("Напиши номер (1, 2, 3) чтобы одобрить, или 'пропустить'.")

    return "\n".join(lines)

# ---- Progress ----
def load_progress():
    try:
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    except:
        return {"processed_ids": [], "last_run": None}

def save_progress(p):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(p, f)

# ---- Fetch ideas ----
def get_unprocessed_ideas():
    ideas = []
    for proj in ("dreams",):
        try:
            data = ikkf_get(f"/nodes?project={proj}&limit=100")
            for n in data.get("nodes", []):
                tags = n.get("tags") or []
                if "dream-insight" in tags:
                    ideas.append(n)
        except Exception as e:
            log(f"  fetch error: {e}")
    return ideas

# ---- Main ----
def run_once(threshold=DEFAULT_THRESHOLD, top_n=DEFAULT_TOP_N, dry_run=False):
    log("=== Dream Pipeline start ===")
    ideas = get_unprocessed_ideas()
    progress = load_progress()
    processed = set(progress.get("processed_ids", []))

    todo = [i for i in ideas if i.get("id") not in processed]
    log(f"Ideas to process: {len(todo)} (total dream-insight: {len(ideas)})")

    if not todo:
        log("No new ideas to process.")
        return []

    results = rank_ideas(todo, threshold=threshold, top_n=top_n, dry_run=dry_run)

    if not dry_run:
        progress["processed_ids"] = list(processed | {r["node_id"] for r in results})
        progress["last_run"] = datetime.now().isoformat()
        save_progress(progress)

    # Статистика
    counts = {}
    for r in results:
        t = r["target"]
        counts[t] = counts.get(t, 0) + 1

    log(f"Results: LMTAI={counts.get('lmtai',0)} Parked={counts.get('parked',0)} To-discuss={counts.get('to-discuss',0)}")

    # Утреннее сообщение
    msg = format_morning_message(results, top_n=top_n)
    log(f"Morning message generated ({len(msg)} chars)")

    # Сохранить сообщение для Telegram-бота
    msg_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'morning-message.txt')
    with open(msg_file, 'w') as f:
        f.write(msg)
    log(f"Morning message saved to {msg_file}")

    log("=== Dream Pipeline done ===")
    return results

def run_review():
    """Показать все проекты."""
    folders = [
        ("lmtai", "📁 LMTAI — реализуемо"),
        ("parked", "🅿️ PARKED — отложено"),
        ("to-discuss", "💬 TO-DISCUSS — на обсуждение"),
    ]
    for proj, title in folders:
        try:
            data = ikkf_get(f"/nodes?project={proj}&limit=50")
            nodes = data.get("nodes", [])
        except Exception as e:
            print(f"{title}: error {e}")
            continue
        print(f"\n{title} — {len(nodes)} items")
        print("=" * 60)
        for n in nodes:
            meta = n.get("metadata") or {}
            sc = meta.get("score", {})
            total = sc.get("total", "?") if isinstance(sc, dict) else "?"
            print(f"\n  [{total}%] {n.get('content','')[:140]}")
            if meta.get("hypothesis"):
                print(f"        🔬 {meta['hypothesis'][:160]}")
            card = meta.get("card", {})
            if card:
                print(f"        🎯 {card.get('goal', '')[:100]}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    args = parser.parse_args()

    if args.review:
        run_review()
    else:
        results = run_once(threshold=args.threshold, top_n=args.top, dry_run=args.dry_run)
        if results:
            print(f"\nTop {min(3, len(results))} ideas:")
            for i, r in enumerate(results[:3]):
                print(f"  #{i+1} [{r['score']['total']}%] {r['idea'][:80]}")
                print(f"       {r['hypothesis'][:100]}")
