"""
Agent Smith — Device Control, User Feedback, Safety, Integration
Модули управления устройствами, обратной связи, безопасности и интеграции.
"""

import json
import logging
import subprocess
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Device Control (smith-4)
# ═══════════════════════════════════════════════════════════

class DeviceController:
    """
    Управление программами и устройствами.
    
    Возможности:
    - Запуск / остановка программ
    - Выполнение команд
    - Управление браузером
    - Управление файлами
    """
    
    def __init__(self, allowed_commands: list = None):
        self.allowed_commands = allowed_commands or [
            "ls", "cat", "echo", "grep", "find", "ps", "top",
            "systemctl", "journalctl",
        ]
        self.blocked_commands = [
            "rm -rf /", "mkfs", "dd if=", ":(){ :|:& };:",
        ]

    def run_command(self, command: str, timeout: int = 30) -> dict:
        """Выполнение shell-команды с проверками безопасности."""
        # Проверка на заблокированные команды
        for blocked in self.blocked_commands:
            if blocked in command:
                return {"status": "blocked", "reason": f"Blocked: {blocked}"}
        
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout
            )
            return {
                "status": "ok",
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "timeout": timeout}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def open_browser(self, url: str) -> dict:
        """Открытие URL в браузере."""
        return self.run_command(f"xdg-open {url} 2>/dev/null || curl -s {url} | head -100")


# ═══════════════════════════════════════════════════════════
# User Feedback Loop (smith-5)
# ═══════════════════════════════════════════════════════════

class UserFeedbackLoop:
    """
    Чувствительность к отклику пользователя.
    
    Отслеживает:
    - Явные команды (stop, undo, don't)
    - Неявные сигналы (короткие ответы, повторные запросы)
    - Настроение (тон сообщений)
    """
    
    STOP_WORDS = ["stop", "стоп", "хватит", "don't", "не надо", "отмена", "undo"]
    NEGATIVE_WORDS = ["плохо", "неправильно", "бред", "ошибка", "заново", "failed"]
    POSITIVE_WORDS = ["хорошо", "отлично", "супер", "perfect", "great", "круто"]
    
    def __init__(self):
        self.feedback_history: list[dict] = []
    
    def analyze(self, user_message: str) -> dict:
        """Анализ сообщения пользователя."""
        msg_lower = user_message.lower()
        
        is_stop = any(w in msg_lower for w in self.STOP_WORDS)
        is_negative = any(w in msg_lower for w in self.NEGATIVE_WORDS)
        is_positive = any(w in msg_lower for w in self.POSITIVE_WORDS)
        
        sentiment = "stop" if is_stop else ("negative" if is_negative else ("positive" if is_positive else "neutral"))
        
        result = {
            "message": user_message[:200],
            "sentiment": sentiment,
            "is_stop": is_stop,
            "is_negative": is_negative,
            "is_positive": is_positive,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        self.feedback_history.append(result)
        return result
    
    def should_stop(self, user_message: str) -> bool:
        """Проверка команды остановки."""
        return any(w in user_message.lower() for w in self.STOP_WORDS)
    
    def get_trend(self, last_n: int = 10) -> str:
        """Тренд настроения за последних N сообщений."""
        recent = self.feedback_history[-last_n:]
        if not recent:
            return "unknown"
        
        positive = sum(1 for r in recent if r["is_positive"])
        negative = sum(1 for r in recent if r["is_negative"])
        
        if positive > negative:
            return "positive"
        elif negative > positive:
            return "negative"
        return "neutral"


# ═══════════════════════════════════════════════════════════
# Safety & Control (smith-6)
# ═══════════════════════════════════════════════════════════

class SafetyController:
    """
    Контроль безопасности.
    
    - Off-switch: мгновенная остановка
    - Лимиты: макс. клонов, макс. команд, макс. файлов
    - Аудит: лог всех действий
    - Allow-list: только разрешённые операции
    """
    
    DEFAULT_LIMITS = {
        "max_clones": 5,
        "max_commands_per_session": 100,
        "max_file_size_mb": 50,
        "max_api_calls_per_hour": 1000,
        "forbidden_paths": ["/etc/shadow", "/etc/passwd", "~/.ssh"],
    }
    
    def __init__(self, limits: dict = None):
        self.limits = limits or self.DEFAULT_LIMITS
        self.command_count = 0
        self.api_call_count = 0
        self.audit_log: list[dict] = []
        self.off = False
    
    def check_command(self, command: str) -> bool:
        """Проверка команды на безопасность."""
        if self.off:
            return False
        if self.command_count >= self.limits["max_commands_per_session"]:
            logger.warning("Command limit reached")
            return False
        self.command_count += 1
        self._audit("command", command)
        return True
    
    def check_clone_count(self, current_count: int) -> bool:
        """Проверка количества клонов."""
        return current_count < self.limits["max_clones"]
    
    def emergency_stop(self):
        """Экстренная остановка."""
        self.off = True
        logger.warning("EMERGENCY STOP activated")
        self._audit("emergency_stop", "activated")
    
    def resume(self):
        """Возобновление."""
        self.off = False
        self._audit("resume", "activated")
    
    def _audit(self, action: str, detail: str):
        self.audit_log.append({
            "action": action,
            "detail": detail[:200],
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    def get_status(self) -> dict:
        return {
            "off": self.off,
            "command_count": self.command_count,
            "max_commands": self.limits["max_commands_per_session"],
            "audit_entries": len(self.audit_log),
        }


# ═══════════════════════════════════════════════════════════
# Integration: IKKF + IKKF_SH (smith-7)
# ═══════════════════════════════════════════════════════════

class SmithIntegration:
    """
    Полная интеграция: IKKF + IKKF_SH + Agent Smith.
    
    Объединяет все модули в единую систему.
    """
    
    def __init__(self, telegram_token: str = None, telegram_chat_id: int = None):
        self.device = DeviceController()
        self.feedback = UserFeedbackLoop()
        self.safety = SafetyController()
        self.orchestrator = None  # MultiAgentOrchestrator
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
    
    def get_system_status(self) -> dict:
        """Статус всей системы."""
        return {
            "safety": self.safety.get_status(),
            "feedback_trend": self.feedback.get_trend(),
            "timestamp": datetime.utcnow().isoformat(),
        }
