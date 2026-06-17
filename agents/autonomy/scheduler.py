"""
Планировщик автономных задач для Agent Smith.
Управляет фоновыми процессами: сны, идеи, консолидация.
"""
import logging
import time
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AutonomousScheduler:
    def __init__(self, agent):
        self.agent = agent
        self.running = False
        self._thread = None
        # Ставим last_run на текущее время при инициализации,
        # чтобы задачи не запускались МГНОВЕННО при старте.
        now = datetime.now()
        self.tasks = {
            "dream": {"interval_hours": 24, "last_run": now},
            "consolidation": {"interval_hours": 48, "last_run": now},
            "self_correction": {"interval_hours": 12, "last_run": now},
            "system_check": {"interval_hours": 1, "last_run": now}
        }

    def start(self):
        """Запустить планировщик в фоновом потоке."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Autonomous scheduler started.")

    def _loop(self):
        while self.running:
            now = datetime.now()

            # Проверка задач
            for name, info in self.tasks.items():
                if info["last_run"] is None or (now - info["last_run"]) > timedelta(hours=info["interval_hours"]):
                    self._run_task(name)
                    info["last_run"] = now

            # Спим 10 минут перед следующей проверкой
            time.sleep(600)

    def _run_task(self, name):
        logger.info(f"Running autonomous task: {name}")
        try:
            if name == "dream":
                self.agent.dream()
                self.agent.generate_ideas()
            elif name == "consolidation":
                if hasattr(self.agent, "memory_manager"):
                    self.agent.memory_manager.run_cleanup()
            elif name == "self_correction":
                if hasattr(self.agent, "self_correct"):
                    # Запускаем в исполнителе
                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(None, lambda: asyncio.run(self.agent.self_correct()))
            elif name == "system_check":
                # Автоматическая проверка ресурсов
                stats = self.agent.tools.execute("get_system_stats", {})
                logger.info(f"Health check: {stats}")
        except Exception as e:
            logger.error(f"Autonomous task '{name}' failed: {e}")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1)
