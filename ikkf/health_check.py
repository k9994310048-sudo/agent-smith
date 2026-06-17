#!/usr/bin/env python3
"""
IKKF — Мониторинг здоровья проекта (Светофор)

Запуск: python3 -m graph.health_check
       python3 graph/health_check.py

Выводит статус каждого компонента:
  🟢 OK — работает стабильно
  🟡 WARN — есть недочёты, но функционирует
  🔴 FAIL — сломано, не работает

Код выхода: 0 = всё зелёное, 1 = есть жёлтое/красное
"""

import sys
import os
import json
import sqlite3
import time
import subprocess

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── Конфигурация ───────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH_DIR = os.path.join(PROJECT_ROOT, "graph")
DB_PATH = os.path.join(PROJECT_ROOT, "data", "graph.db")
API_URL = "http://127.0.0.1:8766"
WEBUI_URL = "http://127.0.0.1:8767"

# Пороги для контекстных измерений
CONTEXT_WARN = 50   # ниже этого — жёлтый
CONTEXT_FAIL = 20   # ниже этого — красный

# Пороги для связности графа
CONNECTIVITY_WARN = 30  # % изолированных узлов
CONNECTIVITY_FAIL = 50

# ─── Утилиты ────────────────────────────────────────────────

class Checker:
    def __init__(self):
        self.results = []
        self.errors = []

    def add(self, component, status, detail=""):
        """
        status: "ok" | "warn" | "fail"
        """
        icons = {"ok": "🟢", "warn": "🟡", "fail": "🔴"}
        self.results.append((component, status, detail))
        if status != "ok":
            self.errors.append((component, status, detail))
        icon = icons.get(status, "⚪")
        print(f"  {icon} {component}: {detail}")

    def summary(self):
        ok = sum(1 for _, s, _ in self.results if s == "ok")
        warn = sum(1 for _, s, _ in self.results if s == "warn")
        fail = sum(1 for _, s, _ in self.results if s == "fail")
        total = len(self.results)
        print(f"\n{'='*60}")
        print(f"ИТОГО: {total} проверок | 🟢 {ok} | 🟡 {warn} | 🔴 {fail}")
        if fail > 0:
            print(f"\n🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ ({fail}):")
            for comp, status, detail in self.results:
                if status == "fail":
                    print(f"   → {comp}: {detail}")
        if warn > 0:
            print(f"\n🟡 НЕДОЧЁТЫ ({warn}):")
            for comp, status, detail in self.results:
                if status == "warn":
                    print(f"   → {comp}: {detail}")
        print(f"{'='*60}")
        return fail == 0 and warn == 0

# ─── Проверки ───────────────────────────────────────────────

def check_filesystem(c: Checker):
    """Проверка наличия всех критических файлов."""
    print("\n📁 ФАЙЛОВАЯ СТРУКТУРА")
    
    critical_files = [
        ("graph/api.py", "API сервер"),
        ("graph/storage.py", "SQLite хранилище"),
        ("graph/graph.py", "Граф операции"),
        ("graph/node.py", "Модели узлов/связей"),
        ("graph/graph_rag.py", "RAG пайплайн"),
        ("graph/fill_context.py", "Заполнение контекста"),
        ("graph/consolidation.py", "Консолидация"),
        ("graph/kungfu_llm.py", "LLM обёртка"),
        ("graph/ikkf_tool.py", "CLI инструмент"),
        ("graph/SKILL.md", "Навык для Hermes"),
        ("data/graph.db", "База данных"),
    ]
    
    for rel_path, desc in critical_files:
        full_path = os.path.join(PROJECT_ROOT, rel_path)
        exists = os.path.exists(full_path)
        size = os.path.getsize(full_path) if exists else 0
        if exists and size > 0:
            c.add(f"  {desc} ({rel_path})", "ok", f"{size} bytes")
        elif exists:
            c.add(f"  {desc} ({rel_path})", "warn", "файл пустой")
        else:
            c.add(f"  {desc} ({rel_path})", "fail", "файл отсутствует")
    
    # Проверка мусора
    junk_files = ["core.py", "memory_system.py", "TECHNICAL_SPEC.md", "moondream_full.py"]
    junk_found = [f for f in junk_files if os.path.exists(os.path.join(PROJECT_ROOT, f))]
    if junk_found:
        c.add("  Мусор в корне", "warn", f"найдено: {', '.join(junk_found)}")
    else:
        c.add("  Мусор в корне", "ok", "чисто")


def check_database(c: Checker):
    """Проверка целостности базы данных."""
    print("\n🗄️  БАЗА ДАННЫХ")
    
    if not os.path.exists(DB_PATH):
        c.add("  БД существует", "fail", f"файл {DB_PATH} не найден")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        
        # Таблицы
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        required_tables = ["nodes", "edges", "node_embeddings", "nodes_fts"]
        missing = [t for t in required_tables if t not in tables]
        if missing:
            c.add("  Таблицы", "fail", f"отсутствуют: {missing}")
        else:
            c.add("  Таблицы", "ok", f"все {len(required_tables)} таблиц на месте")
        
        # Узлы
        total_nodes = conn.execute("SELECT COUNT(*) FROM nodes WHERE status='active'").fetchone()[0]
        if total_nodes > 0:
            c.add("  Узлы", "ok", f"{total_nodes} активных")
        else:
            c.add("  Узлы", "fail", "нет активных узлов")
        
        # Связи
        total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        if total_edges > 0:
            c.add("  Связи", "ok", f"{total_edges} связей")
        else:
            c.add("  Связи", "warn", "нет связей — граф не связан")
        
        # Эмбеддинги
        total_embs = conn.execute("SELECT COUNT(*) FROM node_embeddings").fetchone()[0]
        emb_pct = total_embs / total_nodes * 100 if total_nodes > 0 else 0
        if emb_pct >= 95:
            c.add("  Эмбеддинги", "ok", f"{total_embs}/{total_nodes} ({emb_pct:.0f}%)")
        elif emb_pct >= 70:
            c.add("  Эмбеддинги", "warn", f"{total_embs}/{total_nodes} ({emb_pct:.0f}%) — не все")
        else:
            c.add("  Эмбеддинги", "fail", f"{total_embs}/{total_nodes} ({emb_pct:.0f}%) — критично")
        
        # Связность графа
        isolated = conn.execute("""
            SELECT COUNT(*) FROM nodes n 
            WHERE n.status='active' 
            AND n.id NOT IN (SELECT source_id FROM edges UNION SELECT target_id FROM edges)
        """).fetchone()[0]
        iso_pct = isolated / total_nodes * 100 if total_nodes > 0 else 0
        if iso_pct < CONNECTIVITY_WARN:
            c.add("  Связность", "ok", f"{iso_pct:.0f}% изолированных")
        elif iso_pct < CONNECTIVITY_FAIL:
            c.add("  Связность", "warn", f"{iso_pct:.0f}% изолированных — BFS не расширяет")
        else:
            c.add("  Связность", "fail", f"{iso_pct:.0f}% изолированных — граф разорван")
        
        # Контекстные измерения
        rows = conn.execute("SELECT context FROM nodes WHERE status='active' AND context IS NOT NULL AND context != ''").fetchall()
        dims = {"temporal": 0, "spatial": 0, "social": 0, "emotional": 0, "semantic": 0}
        for r in rows:
            try:
                ctx = json.loads(r[0])
                for d in dims:
                    if ctx.get(d) and str(ctx[d]).lower() not in ["null", "", "raw_text"]:
                        dims[d] += 1
            except:
                pass
        
        print("\n📐 КОНТЕКСТНЫЕ ИЗМЕРЕНИЯ")
        for dim, count in sorted(dims.items()):
            pct = count / total_nodes * 100 if total_nodes > 0 else 0
            if pct >= CONTEXT_WARN:
                c.add(f"  {dim}", "ok", f"{pct:.1f}%")
            elif pct >= CONTEXT_FAIL:
                c.add(f"  {dim}", "warn", f"{pct:.1f}% — низкое покрытие")
            else:
                c.add(f"  {dim}", "fail", f"{pct:.1f}% — критично мало")
        
        # FTS5 индекс
        fts_count = conn.execute("SELECT COUNT(*) FROM nodes_fts").fetchone()[0]
        if fts_count == total_nodes:
            c.add("  FTS5 индекс", "ok", f"{fts_count} записей")
        elif fts_count > 0:
            c.add("  FTS5 индекс", "warn", f"{fts_count}/{total_nodes} — не все узлы индексированы")
        else:
            c.add("  FTS5 индекс", "fail", "индекс пуст")
        
        # Размер БД
        db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
        c.add("  Размер БД", "ok", f"{db_size:.1f} MB")
        
        conn.close()
    except Exception as e:
        c.add("  БД", "fail", f"ошибка: {e}")


def check_api(c: Checker):
    """Проверка API endpoints."""
    print("\n🌐 API (порт 8766)")
    
    try:
        import requests
    except ImportError:
        c.add("  requests", "fail", "модуль requests не установлен")
        return
    
    # Health
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        if r.status_code == 200:
            c.add("  /health", "ok", r.json().get("status", "ok"))
        else:
            c.add("  /health", "fail", f"HTTP {r.status_code}")
    except Exception as e:
        c.add("  /health", "fail", f"недоступен: {e}")
        return  # Если health не работает — остальное тоже
    
    # Stats
    try:
        r = requests.get(f"{API_URL}/stats", timeout=5)
        if r.status_code == 200:
            d = r.json()
            c.add("  /stats", "ok", f"{d.get('nodes_active', '?')} узлов, {d.get('edges_total', '?')} связей")
        else:
            c.add("  /stats", "fail", f"HTTP {r.status_code}")
    except Exception as e:
        c.add("  /stats", "fail", str(e))
    
    # Hybrid search
    try:
        r = requests.get(f"{API_URL}/search/hybrid", params={"q": "test", "limit": 3}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            count = d.get("count", 0)
            if count > 0:
                c.add("  /search/hybrid", "ok", f"{count} результатов")
            else:
                c.add("  /search/hybrid", "warn", "0 результатов — поиск не работает")
        else:
            c.add("  /search/hybrid", "fail", f"HTTP {r.status_code}")
    except Exception as e:
        c.add("  /search/hybrid", "fail", str(e))
    
    # Hybrid search с query алиасом
    try:
        r = requests.get(f"{API_URL}/search/hybrid", params={"query": "test", "limit": 3}, timeout=10)
        if r.status_code == 200:
            c.add("  /search/hybrid (query=)", "ok", "алиас работает")
        else:
            c.add("  /search/hybrid (query=)", "fail", f"HTTP {r.status_code}")
    except Exception as e:
        c.add("  /search/hybrid (query=)", "fail", str(e))
    
    # RAG
    try:
        r = requests.post(f"{API_URL}/rag", json={"query": "что такое IKKF", "max_nodes": 5}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            seeds = d.get("stats", {}).get("seeds_found", 0)
            expanded = d.get("stats", {}).get("expanded_count", 0)
            if seeds >= 5:
                c.add("  /rag", "ok", f"{seeds} seeds, {expanded} expanded")
            elif seeds > 0:
                c.add("  /rag", "warn", f"{seeds} seeds — мало, expanded={expanded}")
            else:
                c.add("  /rag", "fail", "0 seeds — RAG не находит узлы")
        else:
            c.add("  /rag", "fail", f"HTTP {r.status_code}")
    except Exception as e:
        c.add("  /rag", "fail", str(e))
    
    # Node CRUD
    try:
        # Create
        r = requests.post(f"{API_URL}/node", json={"content": "FastAPI health check test on port 8766", "node_type": "fact"}, timeout=5)
        if r.status_code == 200:
            nid = r.json()["node"]["id"]
            ctx = r.json()["node"].get("context", {})
            filled_dims = sum(1 for v in ctx.values() if v and str(v).lower() not in ["null", "", "raw_text"])
            
            # Read
            r2 = requests.get(f"{API_URL}/node/{nid}", timeout=5)
            read_ok = r2.status_code == 200
            
            # Delete
            r3 = requests.delete(f"{API_URL}/node/{nid}", timeout=5)
            del_ok = r3.status_code == 200
            
            if read_ok and del_ok and filled_dims >= 4:
                c.add("  Node CRUD", "ok", f"create/read/delete OK, context {filled_dims}/5")
            elif read_ok and del_ok:
                c.add("  Node CRUD", "warn", f"CRUD OK, но context только {filled_dims}/5")
            else:
                c.add("  Node CRUD", "fail", f"read={read_ok}, delete={del_ok}")
        else:
            c.add("  Node CRUD", "fail", f"create вернул HTTP {r.status_code}")
    except Exception as e:
        c.add("  Node CRUD", "fail", str(e))
    
    # Edge CRUD
    try:
        r1 = requests.post(f"{API_URL}/node", json={"content": "Edge test node one", "node_type": "fact"}, timeout=5)
        r2 = requests.post(f"{API_URL}/node", json={"content": "Edge test node two", "node_type": "fact"}, timeout=5)
        if r1.status_code == 200 and r2.status_code == 200:
            nid1, nid2 = r1.json()["node"]["id"], r2.json()["node"]["id"]
            re = requests.post(f"{API_URL}/edge", json={
                "source_id": nid1, "target_id": nid2,
                "edge_type": "associative", "weight": 0.5
            }, timeout=5)
            edge_ok = re.status_code == 200
            
            # Cleanup
            requests.delete(f"{API_URL}/node/{nid1}")
            requests.delete(f"{API_URL}/node/{nid2}")
            
            if edge_ok:
                c.add("  Edge CRUD", "ok", "create edge OK")
            else:
                c.add("  Edge CRUD", "fail", f"create edge HTTP {re.status_code}")
        else:
            c.add("  Edge CRUD", "fail", "не удалось создать тестовые узлы")
    except Exception as e:
        c.add("  Edge CRUD", "fail", str(e))
    
    # Fill-context
    try:
        r = requests.post(f"{API_URL}/fill-context", json={"limit": 3}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            c.add("  /fill-context", "ok", f"filled={d.get('filled', 0)}")
        else:
            c.add("  /fill-context", "fail", f"HTTP {r.status_code}")
    except Exception as e:
        c.add("  /fill-context", "fail", str(e))


def check_systemd(c: Checker):
    """Проверка systemd сервисов."""
    print("\n⚙️  SYSTEMD")
    
    result = subprocess.run(
        ["systemctl", "is-active", "ikkf-graph"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        c.add("  ikkf-graph.service", "ok", "active")
    else:
        c.add("  ikkf-graph.service", "fail", result.stdout.strip() or "inactive")


def check_webui(c: Checker):
    """Проверка Web UI."""
    print("\n🖥️  WEB UI (порт 8767)")
    
    webui_file = os.path.join(GRAPH_DIR, "webui.py")
    if not os.path.exists(webui_file):
        c.add("  webui.py", "fail", "файл отсутствует")
        return
    
    try:
        import requests
        r = requests.get(f"{WEBUI_URL}/", timeout=5)
        if r.status_code == 200 and "IKKF" in r.text:
            c.add("  Web UI", "ok", "страница отдаётся")
        elif r.status_code == 200:
            c.add("  Web UI", "warn", "страница есть но нет IKKF в заголовке")
        else:
            c.add("  Web UI", "fail", f"HTTP {r.status_code}")
    except Exception as e:
        c.add("  Web UI", "fail", f"недоступен: {e}")


def check_integration(c: Checker):
    """Проверка интеграции с Hermes."""
    print("\n🔗 ИНТЕГРАЦИЯ С HERMES")
    
    # CLAUDE.md
    claude_path = os.path.expanduser("~/CLAUDE.md")
    if os.path.exists(claude_path):
        with open(claude_path) as f:
            content = f.read()
        if "IKKF" in content and "8766" in content:
            c.add("  CLAUDE.md", "ok", "IKKF упомянут")
        else:
            c.add("  CLAUDE.md", "warn", "IKKF не упомянут или устаревший")
    else:
        c.add("  CLAUDE.md", "warn", "файл отсутствует")
    
    # SKILL.md
    skill_path = os.path.join(GRAPH_DIR, "SKILL.md")
    if os.path.exists(skill_path):
        with open(skill_path) as f:
            content = f.read()
        if "8766" in content and "search/hybrid" in content:
            c.add("  SKILL.md", "ok", "актуален")
        else:
            c.add("  SKILL.md", "warn", "возможно устаревший")
    else:
        c.add("  SKILL.md", "fail", "файл отсутствует")
    
    # ikkf_tool.py
    tool_path = os.path.join(GRAPH_DIR, "ikkf_tool.py")
    if os.path.exists(tool_path):
        c.add("  ikkf_tool.py", "ok", "CLI инструмент на месте")
    else:
        c.add("  ikkf_tool.py", "fail", "CLI инструмент отсутствует")


def check_cron(c: Checker):
    """Проверка cron задач."""
    print("\n⏰ CRON")
    
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode == 0:
        lines = result.stdout.strip().split("\n")
        ikkf_lines = [l for l in lines if "ikkf" in l.lower() and not l.startswith("#")]
        if ikkf_lines:
            c.add("  Cron задачи", "ok", f"{len(ikkf_lines)} задач IKKF")
        else:
            c.add("  Cron задачи", "warn", "нет задач IKKF в crontab")
    else:
        c.add("  Cron задачи", "warn", "crontab недоступен")


# ─── Главная функция ────────────────────────────────────────

def main():
    print("=" * 60)
    print("🏥 IKKF — ПРОВЕРКА ЗДОРОВЬЯ ПРОЕКТА")
    print(f"⏰ {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    c = Checker()
    
    check_filesystem(c)
    check_database(c)
    check_api(c)
    check_systemd(c)
    check_webui(c)
    check_integration(c)
    check_cron(c)
    
    all_ok = c.summary()
    
    if all_ok:
        print("\n✅ Всё зелёное! Проект здоров.")
    else:
        print("\n⚠️  Есть проблемы. Исправь красные, потом жёлтые.")
    
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
