"""
Agent Smith — Multi-Agent Orchestration
Координация клонов через A2A-подобный протокол.

Простой протокол:
- Родитель создаёт клонов и назначает задачи
- Клоны выполняют и отчитываются
- Родитель агрегирует результаты
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class A2AMessage:
    """Сообщение между агентами."""
    
    def __init__(self, sender_id: str, receiver_id: str, 
                 msg_type: str, payload: dict):
        self.id = str(uuid.uuid4())[:8]
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.msg_type = msg_type  # task | result | heartbeat | kill
        self.payload = payload
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            "id": self.id,
            "sender": self.sender_id,
            "receiver": self.receiver_id,
            "type": self.msg_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


class MultiAgentOrchestrator:
    """
    Оркестратор мультиагентной системы.
    
    Управляет:
    - Созданием / уничтожением клонов
    - Распределением задач
    - Сбором результатов
    - Обнаружением отказов
    """

    def __init__(self, max_agents: int = 5):
        self.max_agents = max_agents
        self.agents: dict[str, dict] = {}
        self.task_queue: list[dict] = []
        self.results: dict[str, dict] = {}
        self.messages: list[A2AMessage] = []

    def register_agent(self, agent_id: str, agent_type: str = "worker") -> dict:
        """Регистрация агента."""
        agent = {
            "id": agent_id,
            "type": agent_type,  # orchestrator | worker
            "state": "idle",
            "current_task": None,
            "created": datetime.utcnow().isoformat(),
        }
        self.agents[agent_id] = agent
        return agent

    def submit_task(self, task: str, priority: int = 5) -> str:
        """Добавление задачи в очередь."""
        task_id = str(uuid.uuid4())[:8]
        entry = {
            "id": task_id,
            "task": task,
            "priority": priority,
            "state": "pending",
            "assigned_to": None,
            "created": datetime.utcnow().isoformat(),
        }
        self.task_queue.append(entry)
        # Сортировка по приоритету
        self.task_queue.sort(key=lambda t: t["priority"], reverse=True)
        return task_id

    def assign_task(self, task_id: str, agent_id: str) -> bool:
        """Назначение задачи агенту."""
        for entry in self.task_queue:
            if entry["id"] == task_id:
                entry["state"] = "assigned"
                entry["assigned_to"] = agent_id
                if agent_id in self.agents:
                    self.agents[agent_id]["state"] = "working"
                    self.agents[agent_id]["current_task"] = task_id
                return True
        return False

    def collect_result(self, task_id: str, agent_id: str, result: dict):
        """Сбор результата от агента."""
        self.results[task_id] = {
            "agent_id": agent_id,
            "result": result,
            "timestamp": datetime.utcnow().isoformat(),
        }
        for entry in self.task_queue:
            if entry["id"] == task_id:
                entry["state"] = "done"
                break
        if agent_id in self.agents:
            self.agents[agent_id]["state"] = "idle"
            self.agents[agent_id]["current_task"] = None

    def get_status(self) -> dict:
        """Полный статус системы."""
        return {
            "agents": len(self.agents),
            "max_agents": self.max_agents,
            "queue": len(self.task_queue),
            "done": sum(1 for t in self.task_queue if t["state"] == "done"),
            "pending": sum(1 for t in self.task_queue if t["state"] == "pending"),
        }
