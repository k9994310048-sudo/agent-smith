#!/usr/bin/env python3
"""
IKKF — Заполнение context dimensions (temporal/spatial/social/emotional/semantic)
через эвристики + LLM. Пишет в поле context JSON таблицы nodes.

Запуск:
  python3 -m graph.fill_context           # полный backfill
  python3 -m graph.fill_context --status  # текущее состояние
  python3 -m graph.fill_context --max 50  # только первые 50 узлов
"""
import sqlite3
import json
import time
import re
import os
import sys
import numpy as np

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "graph.db")

# ---- Эвристики для быстрого заполнения ----

def extract_temporal(text: str) -> str | None:
    text_lower = text.lower()
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
    ver_match = re.search(r'\bv?(\d+\.\d+[\d.]*)', text)
    if ver_match:
        return f"version {ver_match.group(1)}"
    if any(w in text_lower for w in ['обновл', 'обнов', 'release', 'релиз']):
        return "recent"
    # Технический факт без времени = актуален сейчас
    if any(w in text_lower for w in [
        'код', 'code', 'функци', 'сервер', 'api', 'версия', 'version',
        'систем', 'system', 'настройк', 'config', 'архитектур', 'architecture',
    ]):
        return "ongoing"
    return None


def extract_spatial(text: str) -> str | None:
    """Извлечь пространственный контекст (source/origin, НЕ геолокация).

    spatial = откуда пришёл факт, где он "живёт":
    - server: технический факт (код, инфраструктура, настройки)
    - conversation: из диалога/разговора человека с AI
    - external: внешний источник (статья, GitHub, wiki)
    - personal: личный факт, предпочтение, принцип человека
    - filesystem: файловый путь или директория
    - location: геолокация (город, страна, конкретное место)
    """
    text_lower = text.lower()

    # Явная геолокация (проверяем первой — она самая точная)
    cities = [
        'москва', 'санкт-петербург', 'екатеринбург', 'новосибирск', 'казань',
        'moscow', 'london', 'berlin', 'paris', 'tokyo', 'new york',
        'beijing', 'shanghai', 'dubai', 'singapore',
    ]
    for city in cities:
        if city in text_lower:
            return city.capitalize()

    # Файловые пути = filesystem
    if re.search(r'/[a-zA-Z0-9_./-]{3,}', text):
        match = re.search(r'(/[a-zA-Z0-9_./-]{3,})', text)
        if match:
            return f"path:{match.group(1)[:30]}"

    # URL = external
    url_match = re.search(r'(https?://[^\s]+)', text)
    if url_match:
        return url_match.group(1)[:80]

    # IP-адреса = server
    ip_match = re.search(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', text)
    if ip_match:
        return f"IP {ip_match.group(1)}"

    # Локационные паттерны (сервер, офис, облако...)
    location_patterns = [
        r'\b(сервер|сервере|сервером)\b',
        r'\b(домашний сервер|домашняя сеть)\b',
        r'\b(офис|офисе)\b',
        r'\b(дата-центр|datacenter)\b',
        r'\b(облако|cloud|aws|azure|gcp)\b',
        r'\b(роутер|router)\b',
        r'\b(vps|vds|хостинг|hosting)\b',
        r'\b(network|lan|wan|vpn|internet)\b',
    ]
    for pattern in location_patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(0)[:50]

    # Source-based: определяем origin по ключевым словам в тексте
    # (порядок важен — более специфичные проверки первыми)

    # Personal: личные факты, мнения, принципы, предпочтения
    personal_kw = [
        'клим', 'klim', 'предпочитаю', 'люблю', 'нравится', 'хочу',
        'считаю', 'думаю', 'полагаю', 'убеждён', 'привычка', 'характер',
        'терпение', 'фрустрация', 'раздражение', 'предпочитает',
        'я ', ' мы ', 'наш ', 'мой ', 'моя ', 'моё ', 'мои ',
        'my ', 'our ', 'me ', 'i ', 'we ',
    ]
    if sum(1 for w in personal_kw if w in text_lower) >= 1:
        return "personal"

    # Conversation: из диалога, обсуждения
    conv_kw = [
        'разговор', 'диалог', 'обсудили', 'решили', 'договорились',
        'согласовали', 'итог', 'вывод', 'предложил', 'согласился',
        'обсуждение', 'дискуссия', 'вопрос', 'ответ',
        'принцип', 'правило', 'план', 'стратегия',
        'предпочтение', 'мнение', 'идея', 'концепция',
        'conversation', 'discussed', 'decided', 'agreed',
        'plan', 'strategy', 'preference', 'opinion', 'idea',
    ]
    if sum(1 for w in conv_kw if w in text_lower) >= 1:
        return "conversation"

    # External: внешний источник
    ext_kw = [
        'статья', 'пост', 'блог', 'документация', 'docs',
        'википедия', 'wikipedia', 'github', 'stackoverflow',
        'tutorial', 'guide', 'article', 'blog',
        'reference', 'source', 'источник',
        'цитата', 'quote', 'цитирую', 'согласно', 'по данным',
        'исследование', 'research', 'study', 'paper',
        'отчёт', 'report', 'аналитика',
    ]
    if sum(1 for w in ext_kw if w in text_lower) >= 1:
        return "external"

    # Server: технический факт (2+ тех. термина)
    tech_kw = [
        'python', 'node', 'java', 'rust', 'go',
        'api', 'rest', 'graphql',
        'http', 'https', 'url', 'endpoint',
        'sql', 'database',
        'server', 'client', 'host', 'port',
        'code', 'script', 'module', 'library',
        'framework', 'package', 'dependency',
        'function', 'class', 'method',
        'test', 'debug', 'build',
        'run', 'execute', 'process',
        'async', 'await', 'event',
        'data', 'file', 'config',
        'version', 'update', 'install',
        'storage', 'cache', 'queue',
        'memory', 'cpu', 'disk', 'network',
        'security', 'auth', 'encrypt', 'token',
        'json', 'xml', 'yaml',
        'html', 'css', 'dom',
        'frontend', 'backend',
        'app', 'application', 'service',
        'container', 'image', 'cluster',
        'cloud', 'aws', 'azure', 'gcp',
        'deploy', 'release', 'pipeline',
        'git', 'commit', 'branch', 'merge',
        'repository', 'repo',
        'project', 'task', 'ticket', 'issue', 'bug',
        'feature', 'refactor', 'optimize', 'performance',
        'error', 'exception', 'log', 'metric',
        'monitor', 'health', 'status', 'check',
        'verify', 'validate', 'assert',
        'result', 'output', 'input',
        'deployment', 'infrastructure', 'architecture',
        'algorithm', 'protocol', 'schema', 'format',
        'ssl', 'tls', 'cert',
        'jwt', 'oauth', 'sso',
        'firewall', 'proxy', 'gateway', 'router',
        'load', 'balancer',
        'redis', 'mongodb', 'postgres', 'mysql',
        'sqlite', 'elasticsearch',
        'embedding', 'vector', 'tensor',
        'dimension', 'shape', 'size',
        'image', 'video', 'audio',
        'text', 'document', 'folder', 'directory',
        'path', 'uri', 'link', 'href',
        'action', 'method', 'query',
        'header', 'body', 'cookie', 'session',
        'permission', 'role', 'acl',
        'redirect', 'heap', 'graph', 'tree',
        'list', 'array', 'map', 'set', 'dict',
        'string', 'number', 'boolean', 'null',
        'true', 'false', 'if', 'else', 'for', 'while',
        'throw', 'try', 'catch', 'finally',
        'object', 'interface', 'type', 'enum',
        'struct', 'trait', 'impl', 'extends',
        'public', 'private', 'protected', 'static',
        'const', 'let', 'var', 'def', 'fn',
        'include', 'use',
        'plugin', 'extension',
        'route',
        'credential',
        'switch',
    ]
    tech_count = sum(1 for w in tech_kw if w in text_lower)
    if tech_count >= 2:
        return "server"

    return None


def extract_social(text: str) -> str | None:
    text_lower = text.lower()
    names = [
        'клим', 'klim', 'bidancev', 'быданцев',
        'owl', 'hermès', 'hermés', 'hermes',
        'qwen', 'llama', 'fastembed', 'chatgpt', 'gpt',
        'nous', 'roberta', 'minilm', 'llama.cpp',
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
    if any(w in text_lower for w in ['разговор', 'диалог', 'обсудили', 'решили', 'договорились', 'согласовали']):
        return "personal"
    return None


def extract_emotional(text: str) -> str | None:
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


def extract_semantic(text: str) -> str:
    text_lower = text.lower()
    categories = {
        'setup': ['установк', 'install', 'setup', 'настройк', 'config', 'инициализац'],
        'deployment': ['деплой', 'deploy', 'продакшн', 'production', 'systemd', 'service'],
        'troubleshooting': ['ошибк', 'error', 'баг', 'bug', 'debug', 'fix', 'исправл', 'проблем'],
        'architecture': ['архитектур', 'architecture', 'дизайн', 'design', 'схема', 'модуль'],
        'data': ['данны', 'data', 'база', 'database', 'storage', 'sqlite', 'embedd'],
        'network': ['сеть', 'network', 'порт', 'port', 'ufw', 'firewall'],
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


def fill_heuristic(text: str) -> dict:
    return {
        "temporal": extract_temporal(text),
        "spatial": extract_spatial(text),
        "social": extract_social(text),
        "emotional": extract_emotional(text),
        "semantic": extract_semantic(text),
    }


def needs_llm(dimensions: dict) -> bool:
    filled = sum(1 for v in dimensions.values() if v is not None)
    return filled < 3


def fill_via_llm_with_llm(llm, content: str) -> dict:
    text = content[:200]
    prompt = f"""Extract context from this text. Reply with ONLY a JSON object, no other text.

Text: {text}

Reply format:
{{"temporal": "<time or date, max 3 words, or null>", "spatial": "<source: server|conversation|external|personal|filesystem, or null>", "social": "<person or group, max 3 words, or null>", "emotional": "<positive or negative or neutral or null>", "semantic": "<one word category or null>"}}

JSON:"""
    try:
        result = llm._ask(prompt, max_tokens=80, temperature=0.0)
        json_match = re.search(r'\{[^{}]*\}', result, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            cleaned = {}
            for key in ['temporal', 'spatial', 'social', 'emotional', 'semantic']:
                val = data.get(key)
                if val and str(val).lower() not in ['null', 'none', '', 'n/a']:
                    cleaned[key] = str(val)[:50]
            return cleaned
    except Exception:
        pass
    return {}


def run(max_nodes=None, use_llm=False):
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
    if max_nodes:
        to_fill = to_fill[:max_nodes]
    print(f"Total active nodes: {len(rows)}")
    print(f"Nodes to fill (context < 5/5): {len(to_fill)}")
    print(f"LLM mode: {'ON' if use_llm else 'OFF (heuristics only)'}")
    if not to_fill:
        print("Nothing to fill!")
        conn.close()
        return
    llm = None
    if use_llm:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from graph.kungfu_llm import KungFuLLM
        llm = KungFuLLM(n_ctx=512, n_threads=2)
    filled_count = 0
    heuristic_only = 0
    llm_used = 0
    errors = 0
    for i, (nid, content) in enumerate(to_fill):
        text = content[:300]
        dims = fill_heuristic(text)
        if use_llm and llm:
            try:
                llm_dims = fill_via_llm_with_llm(llm, content)
                for key in ['temporal', 'spatial', 'social', 'emotional', 'semantic']:
                    if dims.get(key) is None and llm_dims.get(key) and str(llm_dims[key]).lower() not in ['null', 'none', '']:
                        dims[key] = str(llm_dims[key])[:50]
                llm_used += 1
            except Exception:
                heuristic_only += 1
        else:
            heuristic_only += 1
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
        if (i + 1) % 20 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(to_fill) - i - 1) / rate if rate > 0 else 0
            print(f"  Progress: {i+1}/{len(to_fill)}, filled: {filled_count}, "
                  f"heuristic: {heuristic_only}, llm: {llm_used}, "
                  f"{rate:.1f}/sec, ETA: {remaining/60:.1f}min", flush=True)
    elapsed = time.time() - start_time
    print(f"\nDone! Filled: {filled_count}/{len(to_fill)}, "
          f"Heuristic: {heuristic_only}, LLM: {llm_used}, Errors: {errors}")
    print(f"Time: {elapsed/60:.1f}min, Rate: {len(to_fill)/elapsed:.1f}/sec")
    conn.close()


def status():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM nodes WHERE status='active'")
    total = cur.fetchone()[0]
    cur.execute("""
        SELECT context FROM nodes
        WHERE status='active' AND context IS NOT NULL AND context != ''
    """)
    contexts = [json.loads(r[0]) if r[0] else {} for r in cur.fetchall()]
    dims = {'temporal': 0, 'spatial': 0, 'social': 0, 'emotional': 0, 'semantic': 0}
    fully_filled = 0
    for ctx in contexts:
        filled_dims = 0
        for dim in dims:
            val = ctx.get(dim)
            if val is not None and str(val).lower() not in ['null', '', 'raw_text']:
                dims[dim] += 1
                filled_dims += 1
        if filled_dims >= 4:
            fully_filled += 1
    print(f"Total active nodes: {total}")
    print(f"Analyzed contexts: {len(contexts)}")
    print(f"Fully filled (4+/5 dims): {fully_filled} ({fully_filled/total*100:.1f}%)")
    print(f"\nBy dimension:")
    for dim, count in sorted(dims.items()):
        pct = count / total * 100
        bar = '█' * int(pct / 2) + '░' * (50 - int(pct / 2))
        print(f"  {dim:12s}: {count:4d}/{total} ({pct:5.1f}%) |{bar}|")
    conn.close()


if __name__ == "__main__":
    if "--status" in sys.argv:
        status()
    else:
        max_nodes = None
        use_llm = "--llm" in sys.argv
        for i, arg in enumerate(sys.argv):
            if arg == "--max" and i + 1 < len(sys.argv):
                max_nodes = int(sys.argv[i + 1])
        run(max_nodes=max_nodes, use_llm=use_llm)
