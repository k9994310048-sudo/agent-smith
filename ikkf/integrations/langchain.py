"""
IKKF — LangChain Memory Adapter

Позволяет использовать IKKF как бэкенд памяти для LangChain.
Подключается к любому LangChain агенту через BaseMemory API.

Использование:
    from ikkf.integrations.langchain import IKKFMemory
    memory = IKKFMemory()
"""

import os
import sys
import json
from typing import Optional

# Добавляем корень проекта в path
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class IKKFGraphMemory:
    """
    Обёртка IKKF графа для использования как память агента.

    Простой API: add(), query(), get_graph()
    """

    def __init__(self, db_path: str = None):
        from graph.graph import Graph

        if db_path is None:
            db_path = os.path.join(_ROOT, "data", "graph.db")
        self.graph = Graph(db_path)

    def add(self, text: str, role: str = "user", tags: list = None):
        """Добавить факт в граф."""
        parts = [f"[{role}] {text}"]
        if tags:
            parts.append(f"tags: {', '.join(tags)}")
        content = " | ".join(parts)
        self.graph.add_node(content, node_type="fact", project="langchain-memory")

    def query(self, question: str, limit: int = 5) -> str:
        """Найти релевантные факты через RAG."""
        from graph.graph_rag import GraphRAG
        rag = GraphRAG(self.graph)
        result = rag.query(question, max_context_nodes=limit)
        return result.get("context_text", "")

    def get_graph(self) -> dict:
        """Получить информацию о графе."""
        return self.graph.stats()

    def close(self):
        """Закрыть соединение с БД."""
        self.graph.close()


# ---- LangChain BaseMemory adapter (опционально) ----

def get_langchain_memory(db_path: str = None):
    """
    Создать LangChain-совместимый memory adapter.

    Возвращает объект совместимый с langchain.memory.BaseMemory.
    Если langchain не установлен — возвращает IKKFGraphMemory.
    """
    try:
        from langchain.memory import BaseMemory
        from langchain.schema import BaseChatMessageHistory

        class IKKFMemory(BaseMemory):
            """LangChain Memory backed by IKKF Graph."""

            memory_key: str = "history"
            graph_memory: IKKFGraphMemory = None
            session_id: str = "default"

            def __init__(self, db_path: str = None, session_id: str = "default", **kwargs):
                super().__init__(**kwargs)
                self.graph_memory = IKKFGraphMemory(db_path)
                self.session_id = session_id

            @property
            def memory_variables(self) -> list:
                return [self.memory_key]

            def load_memory_variables(self, inputs: dict) -> dict:
                """Загрузить контекст из графа."""
                query = inputs.get("input", "")
                if not query:
                    query = str(inputs)
                context = self.graph_memory.query(query)
                return {self.memory_key: context}

            def save_context(self, inputs: dict, outputs: dict):
                """Сохранить контекст в граф."""
                user_input = inputs.get("input", str(inputs))
                ai_output = outputs.get("output", str(outputs))

                self.graph_memory.add(f"Question: {user_input}", role="user")
                self.graph_memory.add(f"Answer: {ai_output[:300]}", role="assistant")

            def clear(self):
                """Очистить память сессии."""
                # В текущей реализации не удаляем данные
                pass

        return IKKFMemory(db_path=db_path)

    except ImportError:
        # LangChain не установлен — возвращаем простую обёртку
        return IKKFGraphMemory(db_path)


# ---- Примеры использования ----

if __name__ == "__main__":
    import tempfile

    print("=== Тест IKKF LangChain Adapter ===\n")

    # Тестовый граф
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name

    try:
        # Простой API
        mem = IKKFGraphMemory(db)
        mem.add("User is building IKKF project", role="user", tags=["project"])
        mem.add("IKKF uses SQLite for storage", role="system", tags=["architecture"])
        mem.add("User prefers Russian language", role="user", tags=["preference"])

        print("1. Query test:")
        result = mem.query("What is IKKF?")
        print(f"   Result:\n{result}")

        print("\n2. Graph stats:")
        stats = mem.get_graph()
        print(f"   Nodes: {stats['nodes_total']}, Edges: {stats['edges_total']}")

        mem.close()

        # LangChain adapter test (если установлен)
        print("\n3. LangChain adapter test:")
        lc_mem = get_langchain_memory(db)
        print(f"   Type: {type(lc_mem).__name__}")
        if hasattr(lc_mem, 'load_memory_variables'):
            print(f"   Has load_memory_variables: True")
            print(f"   Has save_context: True")
        else:
            print(f"   Simple IKKFGraphMemory (no LangChain)")

        print("\n=== Тесты завершены ===")

    finally:
        os.unlink(db)
