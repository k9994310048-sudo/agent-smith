#!/usr/bin/env python3
"""
LLM backfill для context dimensions — heuristic only version.
Запуск: python3 llm_backfill.py [--max N]
"""
import sqlite3
import json
import time
import re
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "graph.db")
LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "llm_backfill.log")

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

# ---- Эвристики ----

def extract_temporal(text):
    text_lower = text.lower()
    # Явные даты и годы
    date_patterns = [
        r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b',
        r'\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b',
        r'\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b',
        r'\b\d{4}[-/]\d{1,2}\b',
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}',
        r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}',
        r'\b\d{1,2}\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b',
        r'\b(январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь)[а-я]*\b',
        r'\b(понедельник|вторник|среда|четверг|пятница|суббота|воскресенье)\b',
        r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
        r'\b(сегодня|вчера|завтра|позавчера)\b',
        r'\b(today|yesterday|tomorrow)\b',
        r'\b(утром|днём|вечером|ночью)\b',
        r'\b(morning|afternoon|evening|night)\b',
        r'\b\d{1,2}:\d{2}\b',
        r'\b(весна|лето|осень|зима|весной|летом|осенью|зимой)\b',
        r'\b(spring|summer|autumn|winter)\b',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(0)[:50]
    # Относительное время
    time_words = [
        'неделя', 'месяц', 'год', 'час', 'минута', 'секунда',
        'week', 'month', 'year', 'hour', 'minute', 'second',
        'давно', 'недавно', 'сейчас', 'потом', 'раньше',
        'ago', 'recently', 'now', 'later', 'before', 'today',
        'каждый день', 'ежедневно', 'еженедельно', 'daily', 'weekly',
        'после', 'до', 'во время', 'в течение', 'during', 'after', 'before',
        'период', 'периодичн', 'цикл', 'cycle',
        'постоянно', 'всегда', 'никогда', 'sometimes', 'always', 'never',
        'раз в', 'once', 'twice', 'обычно', 'часто', 'редко',
        'typically', 'usually', 'often', 'rarely',
        'прошлый', 'этот', 'следующий', 'прошлого', 'этой', 'следующего',
        'last', 'this', 'next',
    ]
    for word in time_words:
        if word in text_lower:
            idx = text_lower.index(word)
            start = max(0, idx - 20)
            end = min(len(text), idx + 30)
            return text[start:end].strip()[:50]
    # Версия = временной маркер
    ver_match = re.search(r'\bv?(\d+\.\d+[\d.]*)', text)
    if ver_match:
        return f"version {ver_match.group(1)}"
    # Обновление = недавно
    if any(w in text_lower for w in ['обновл', 'обнов', 'release', 'релиз']):
        return "recent"
    # Технический факт без времени = актуален сейчас (ongoing)
    tech_words = [
        'сервер', 'api', 'база', 'database', 'код', 'code',
        'функци', 'method', 'class', 'модуль', 'настройк', 'конфиг',
        'deploy', 'install', 'update', 'version', 'узел', 'node',
        'граф', 'graph', 'embedding', 'vector', 'search', 'query',
        'python', 'fastapi', 'sqlite', 'json', 'http', 'rest',
        'docker', 'linux', 'ubuntu', 'bash', 'ssh', 'cron',
        'структура', 'архитектура', 'схема', 'алгоритм',
        'контекст', 'context', 'памят', 'memory', 'knowledge',
        'хранение', 'storage', 'save', 'load', 'file',
        'systemd', 'nginx', 'service', 'config', 'settings',
    ]
    if any(w in text_lower for w in tech_words):
        return "ongoing"
    return None

def extract_spatial(text):
    text_lower = text.lower()
    # IP
    ip_match = re.search(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', text)
    if ip_match:
        return f"IP {ip_match.group(1)}"
    # URL
    url_match = re.search(r'(https?://[^\s]+)', text)
    if url_match:
        return url_match.group(1)[:80]
    # Города
    cities = [
        'москва', 'санкт-петербург', 'екатеринбург', 'новосибирск', 'казань',
        'нижний новгород', 'samara', 'омск', 'ростов', 'краснодар',
        'moscow', 'london', 'berlin', 'paris', 'tokyo', 'new york',
        'beijing', 'shanghai', 'сеул', 'амстердам', 'стокгольм',
        'dublin', 'минск', 'киева', 'tallinn', 'рига', 'вильнюс',
        'софия', 'бухарест', 'warsaw', 'prague', 'budapest',
        'dubai', 'singapore', 'mumbai', 'delhi', 'bangalore',
    ]
    for city in cities:
        if city in text_lower:
            return city.capitalize()
    # Локации
    location_patterns = [
        r'\b(сервер|сервере|сервером)\b',
        r'\b(домашний сервер|домашняя сеть|дома)\b',
        r'\b(офис|офисе)\b',
        r'\b(дата-центр|datacenter|data center)\b',
        r'\b(облако|cloud|aws|azure|gcp)\b',
        r'\b(гараж|подвал|чердак|комната|кабинет)\b',
        r'\b(garage|basement|attic|room|office)\b',
        r'\b(роутер|router)\b',
        r'\b(vps|vds|дедик|dedicated|хостинг|hosting)\b',
        r'\b(макбук|macbook|mac|ubuntu|linux|windows)\b',
        r'\b(macbook|mac|ubuntu|linux|windows)\b',
        r'\b(сеть|network|lan|wan|vpn|интернет)\b',
        r'\b(network|lan|wan|vpn|internet)\b',
    ]
    for pattern in location_patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(0)[:50]
    # Локальный/удалённый
    if any(w in text_lower for w in ['локально', 'local', 'удалённо', 'remote', 'ssh', 'по сети', 'online']):
        if 'удалённо' in text_lower or 'remote' in text_lower:
            return "remote"
        if 'локально' in text_lower or 'local' in text_lower:
            return "local"
        return "network"
    # Файловые пути
    if re.search(r'/[a-zA-Z0-9_./-]{3,}', text):
        match = re.search(r'(/[a-zA-Z0-9_./-]{3,})', text)
        if match:
            return f"path:{match.group(1)[:30]}"
    # Технический контекст = server (дефолт для тех узлов)
    tech_spatial = [
        r'\bport\s+\d+', r'\bпорт\s+\d+',
        r'\bapi\b', r'\bendpoint', r'\burl\b',
        r'\bhttp[s]?://', r'\bgrpc\b', r'\brest\b',
        r'\bdocker\b', r'\bkubernetes\b', r'\bk8s\b',
        r'\bsystemd\b', r'\bservice\b',
        r'\bnginx\b', r'\bapache\b', r'\bcaddy\b',
        r'\bsqlite\b', r'\bpostgres', r'\bmysql\b', r'\bmongo',
        r'\bredis\b', r'\belastic',
        r'\bfastapi\b', r'\bflask\b', r'\bdjango\b',
        r'\buvicorn\b', r'\bgunicorn\b',
        r'\bfile\b', r'\bpath\b', r'\bdir\b',
        r'/root/', r'/home/', r'/var/', r'/etc/', r'/tmp/',
        r'\bconfig\b', r'\bsettings\b',
        r'\bdeploy\b', r'\brelease\b',
        r'\bproduction\b', r'\bprod\b', r'\bstaging\b',
        r'\bdev\b', r'\bdevelopment\b',
        r'\bgithub\b', r'\bgitlab\b', r'\brepository\b',
        r'\bgit\b', r'\bcommit\b', r'\bbranch\b',
        r'\bpython\b', r'\bnode\b', r'\bjs\b', r'\bts\b',
        r'\bjava\b', r'\brust\b', r'\bgo\b',
        r'\bsql\b', r'\bnosql\b', r'\bdb\b', r'\bdatabase\b',
        r'\bcode\b', r'\bscript\b', r'\bmodule\b', r'\blibrary\b',
        r'\bframework\b', r'\bpackage\b', r'\bdependency\b',
        r'\balgorithm\b', r'\bfunction\b', r'\bclass\b', r'\bmethod\b',
        r'\btest\b', r'\bdebug\b', r'\bbuild\b', r'\bcompile\b',
        r'\brun\b', r'\bexecute\b', r'\bprocess\b', r'\bthread\b',
        r'\basync\b', r'\bawait\b', r'\bcallback\b', r'\bevent\b',
        r'\bdata\b', r'\benv\b', r'\bparam\b', r'\barg\b',
        r'\breturn\b', r'\bimport\b', r'\bexport\b', r'\brequire\b',
    ]
    for pattern in tech_spatial:
        if re.search(pattern, text_lower):
            return "server"
    return None

def extract_social(text):
    text_lower = text.lower()
    names = [
        'клим', 'klim', 'bidancev', 'быданцев',
        'owl', 'hermès', 'hermés', 'hermes',
        'qwen', 'llama', 'fastembed', 'chatgpt', 'gpt',
        'nous', 'roberta', 'minilm', 'llama.cpp',
        'макбук', 'macbook',
        'telegram', 'телефон', 'phone',
    ]
    for name in names:
        if name in text_lower:
            return name.strip()
    mentions = re.findall(r'@(\w+)', text)
    if mentions:
        return f"@{mentions[0]}"
    if any(w in text_lower for w in ['я ', ' мы ', 'наш ', ' my ', ' our ', ' team', 'меня ', 'нас ']):
        return "personal"
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
    if email_match:
        return email_match.group(0)
    role_patterns = [
        r'\b(разработчик|программист|developer|engineer)\b',
        r'\b(пользователь|клиент|user|client)\b',
        r'\b(admin|root|sudo)\b',
        r'\b(автор|author|creator)\b',
        r'\b(агент|agent|bot|бот)\b',
        r'\b(llm|model|модель)\b',
    ]
    for pattern in role_patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(0)
    if any(w in text_lower for w in ['systemd', 'nginx', 'docker', 'api', 'сервер', 'server', 'database', 'база']):
        return "developer"
    return None

def extract_emotional(text):
    text_lower = text.lower()
    negative = [
        'ошибка', 'баг', 'критично', 'паника', 'сломан', 'неработает',
        'error', 'bug', 'critical', 'broken', 'failed', 'failure',
        'frustrat', 'злость', 'бесит', 'надоело', 'устал', 'плохой',
        'bad', 'wrong', 'terrible', 'awful', 'hate', 'anger',
        'проблема', 'проблем', 'issue', 'problem', 'warning',
        'опасно', 'уязвим', 'danger', 'vulnerab', 'security',
        'нельзя', 'невозможно', 'impossible', 'cannot', "can't",
        'фрустрация', 'терпение', 'разочарован', 'разочарование',
        'fail', 'crash', 'dead', 'kill', 'refuse', 'denied', 'forbidden',
        'некорректно', 'неверно', 'invalid', 'incorrect',
        'пустой', 'пуст', 'пустые', 'empty', 'null', 'none',
        'не удалось', 'не получилось', 'не найдено', 'not found',
        'отклонён', 'отказано', 'rejected', 'refused',
    ]
    neg_count = sum(1 for word in negative if word in text_lower)
    if neg_count >= 2:
        return "negative"
    positive = [
        'отлично', 'супер', 'ура', 'получилось', 'работает', 'готово',
        'great', 'excellent', 'awesome', 'perfect', 'done', 'success',
        'хорошо', 'класс', 'молодец', 'thanks', 'thank', 'спасибо',
        'good', 'nice', 'wonderful', 'amazing', 'love', 'like',
        'легко', 'просто', 'easy', 'simple', 'smooth',
        'доволен', 'рад', 'happy', 'glad', 'pleased',
        'реализовано', 'выполнено', 'завершено', 'completed', 'finished',
        'исправлено', 'fixed', 'решено', 'resolved',
        'работает', 'working', 'pass', 'passed', '✅',
    ]
    pos_count = sum(1 for word in positive if word in text_lower)
    if pos_count >= 1:
        return "positive"
    technical_words = [
        'сервер', 'api', 'база', 'database', 'код', 'code',
        'функция', 'функци', 'method', 'class', 'модуль',
        'настройк', 'конфиг', 'deploy', 'install', 'update',
        'version', 'release', 'patch', 'fix', 'feat', 'commit',
        'узел', 'нода', 'node', 'граф', 'graph', 'edge', 'связь',
        'embedding', 'vector', 'search', 'query', 'index',
        'python', 'fastapi', 'sqlite', 'json', 'http', 'rest',
        'docker', 'linux', 'ubuntu', 'bash', 'ssh', 'cron',
        'структура', 'архитектура', 'схема', 'алгоритм',
        'реализац', 'implement', 'design', 'pattern',
        'контекст', 'context', 'памят', 'memory', 'knowledge',
        'хранение', 'storage', 'save', 'load', 'file',
    ]
    tech_count = sum(1 for word in technical_words if word in text_lower)
    if tech_count >= 1:
        return "neutral"
    if len(text) < 50:
        return "neutral"
    return None

def extract_semantic(text):
    text_lower = text.lower()
    categories = {
        'setup': ['установк', 'install', 'setup', 'настройк', 'config', 'инициализац'],
        'deployment': ['деплой', 'deploy', 'продакшн', 'production', 'systemd', 'service'],
        'troubleshooting': ['ошибк', 'error', 'баг', 'bug', 'debug', 'fix', 'исправл', 'проблем'],
        'architecture': ['архитектур', 'architecture', 'дизайн', 'design', 'схема', 'модуль'],
        'data': ['данны', 'data', 'база', 'database', 'storage', 'sqlite', 'embedd'],
        'network': ['сеть', 'network', 'ssh', 'туннел', 'tunnel', 'порт', 'port', 'ufw', 'firewall'],
        'memory': ['памят', 'memory', 'граф', 'graph', 'знани', 'knowledge', 'context'],
        'security': ['безопасност', 'security', 'парол', 'password', 'auth', 'encrypt', 'ssl'],
        'performance': ['производительност', 'performance', 'оптимиз', 'optimization', 'speed', 'fast'],
        'communication': ['сообщени', 'message', 'telegram', 'чат', 'chat', 'бот', 'bot'],
        'learning': ['обучени', 'learning', 'учеб', 'study', 'tutorial', 'пример', 'example'],
        'planning': ['план', 'plan', 'задач', 'task', 'todo', 'roadmap', 'этап', 'phase'],
    }
    for category, keywords in categories.items():
        for kw in keywords:
            if kw in text_lower:
                return category
    return "general"

def fill_heuristic(text):
    return {
        "temporal": extract_temporal(text),
        "spatial": extract_spatial(text),
        "social": extract_social(text),
        "emotional": extract_emotional(text),
        "semantic": extract_semantic(text),
    }

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--max', type=int, default=None)
    args = parser.parse_args()

    with open(LOG_FILE, "w") as f:
        f.write("")

    start_time = time.time()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur = conn.cursor()

    cur.execute("""
        SELECT id, content, context FROM nodes
        WHERE status = 'active'
        AND content IS NOT NULL
        AND LENGTH(TRIM(content)) > 10
        AND NOT content LIKE '/%'
        AND NOT content LIKE 'http%'
    """)
    rows = cur.fetchall()

    to_fill = []
    for nid, content, context_json in rows:
        try:
            ctx = json.loads(context_json) if context_json else {}
        except (json.JSONDecodeError, TypeError):
            ctx = {}
        filled = sum(
            1 for k in ['temporal', 'spatial', 'social', 'emotional', 'semantic']
            if ctx.get(k) is not None and str(ctx[k]).lower() not in ['null', '', 'raw_text']
        )
        if filled < 5:
            to_fill.append((nid, content))

    if args.max:
        to_fill = to_fill[:args.max]

    log(f"Total active nodes: {len(rows)}")
    log(f"Nodes to fill: {len(to_fill)}")

    if not to_fill:
        log("Nothing to fill!")
        conn.close()
        return

    filled_count = 0
    errors = 0

    for i, (nid, content) in enumerate(to_fill):
        text = content[:300]
        dims = fill_heuristic(text)

        try:
            cur.execute(
                "UPDATE nodes SET context = ?, updated_at = ? WHERE id = ?",
                (json.dumps(dims, ensure_ascii=False), time.strftime('%Y-%m-%dT%H:%M:%S'), nid)
            )
            conn.commit()
            filled_count += 1
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                time.sleep(0.5)
                try:
                    conn.rollback()
                except Exception:
                    pass
                errors += 1
                continue
            else:
                errors += 1
                continue

        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(to_fill) - i - 1) / rate if rate > 0 else 0
            log(f"Progress: {i+1}/{len(to_fill)}, filled: {filled_count}, "
                f"{rate:.1f}/sec, ETA: {remaining/60:.1f}min")

    elapsed = time.time() - start_time
    log(f"\nDone! Filled: {filled_count}/{len(to_fill)}, Errors: {errors}")
    log(f"Time: {elapsed:.1f}sec, Rate: {len(to_fill)/elapsed:.1f}/sec")

    conn.close()

if __name__ == "__main__":
    main()
