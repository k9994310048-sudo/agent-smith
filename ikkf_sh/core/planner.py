"""
IKKF_SH — Show Me
Action Planner: декомпозиция задач, выбор инструментов, выполнение
"""

import json
import logging
import subprocess
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class Tool:
    """Описание инструмента агента"""

    def __init__(self, name: str, description: str,
                 func: Callable, params: Dict[str, str] = None):
        self.name = name
        self.description = description
        self.func = func
        self.params = params or {}


class ActionPlanner:
    """
    Планировщик действий.
    Декомпозирует задачу в шаги, выбирает инструменты, выполняет.
    """

    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Регистрация базовых инструментов"""
        self.register_tool(Tool(
            name="shell",
            description="Выполнить команду в shell",
            func=self._exec_shell,
            params={"command": "команда для выполнения"}
        ))
        self.register_tool(Tool(
            name="web_search",
            description="Поиск в интернете",
            func=self._web_search,
            params={"query": "поисковый запрос"}
        ))
        self.register_tool(Tool(
            name="web_fetch",
            description="Получить содержимое страницы",
            func=self._web_fetch,
            params={"url": "URL страницы"}
        ))
        self.register_tool(Tool(
            name="ik_search",
            description="Поиск в IKKF графе знаний",
            func=self._ik_search,
            params={"query": "поисковый запрос", "limit": "лимит результатов"}
        ))
        self.register_tool(Tool(
            name="ik_store",
            description="Сохранить факт в IKKF",
            func=self._ik_store,
            params={"fact": "текст факта", "importance": "важность 0-1"}
        ))
        self.register_tool(Tool(
            name="file_read",
            description="Прочитать файл",
            func=self._file_read,
            params={"path": "путь к файлу"}
        ))
        self.register_tool(Tool(
            name="file_write",
            description="Записать файл",
            func=self._file_write,
            params={"path": "путь к файлу", "content": "содержимое"}
        ))
        self.register_tool(Tool(
            name="telegram_send",
            description="Отправить сообщение в Telegram",
            func=self._telegram_send,
            params={"chat_id": "ID чата", "message": "текст сообщения"}
        ))

    def register_tool(self, tool: Tool):
        self.tools[tool.name] = tool
        logger.debug(f"Tool registered: {tool.name}")

    def get_available_tools(self) -> Dict[str, str]:
        return {name: t.description for name, t in self.tools.items()}

    def execute(self, tool_name: str, params: Dict[str, Any]) -> str:
        """Выполнить инструмент"""
        if tool_name not in self.tools:
            return f"ERROR: Unknown tool '{tool_name}'. Available: {list(self.tools.keys())}"
        try:
            result = self.tools[tool_name].func(**params)
            return str(result)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return f"ERROR: {e}"

    # ── Default tool implementations ──────────────────────────────

    def _exec_shell(self, command: str) -> str:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=30
        )
        return result.stdout + result.stderr

    def _web_search(self, query: str) -> str:
        try:
            import urllib.request
            import urllib.parse
            params = urllib.parse.urlencode({"q": query, "limit": 5})
            url = f"https://html.duckduckgo.com/html/?{params}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", errors="ignore")[:2000]
        except Exception as e:
            return f"Search error: {e}"

    def _web_fetch(self, url: str) -> str:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", errors="ignore")[:3000]
        except Exception as e:
            return f"Fetch error: {e}"

    def _ik_search(self, query: str, limit: int = 5) -> str:
        try:
            import urllib.request
            import urllib.parse
            params = urllib.parse.urlencode({
                "q": query, "search_type": "hybrid", "limit": limit
            })
            url = f"http://127.0.0.1:8766/search/hybrid?{params}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read())
            items = result.get("results", [])
            if not items:
                return "No results"
            lines = []
            for r in items:
                content = r.get("content", "")[:150]
                score = r.get("vec_score", 0)
                lines.append(f"[{score:.2f}] {content}")
            return "\n".join(lines)
        except Exception as e:
            return f"IKKF search error: {e}"

    def _ik_store(self, fact: str, importance: float = 0.7) -> str:
        try:
            import urllib.request
            data = json.dumps({
                "content": fact,
                "node_type": "fact",
                "importance": importance,
                "source": "ikkf_sh"
            }).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:8766/node",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read())
            node_id = result.get("node", {}).get("id", "?")[:12]
            return f"Stored: {node_id}"
        except Exception as e:
            return f"IKKF store error: {e}"

    def _file_read(self, path: str) -> str:
        try:
            with open(path, "r") as f:
                return f.read()[:5000]
        except Exception as e:
            return f"Read error: {e}"

    def _file_write(self, path: str, content: str) -> str:
        try:
            with open(path, "w") as f:
                f.write(content)
            return f"Written: {path}"
        except Exception as e:
            return f"Write error: {e}"

    def _telegram_send(self, chat_id: str, message: str) -> str:
        try:
            import urllib.request
            import urllib.parse
            # Token from secrets
            with open("/root/.ikkf_secrets") as f:
                for line in f:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        token = line.strip().split("=", 1)[1]
                        break
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text": message[:4000],
                "parse_mode": "Markdown"
            }).encode()
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
            if result.get("ok"):
                return f"Sent to {chat_id}"
            return f"Telegram error: {result}"
        except Exception as e:
            return f"Telegram error: {e}"
