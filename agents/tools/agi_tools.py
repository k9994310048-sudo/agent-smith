"""
AGI Tools — Self-Diagnosis and Self-Upgrade tools.
"""
import os
import subprocess
import logging
import sys

logger = logging.getLogger("agi-tools")
PROJECT_ROOT = "/home/mac/.agent-smith"

def self_diagnose_handler() -> str:
    """Проверка логов и синтаксиса проекта."""
    try:
        results = []
        # 1. Проверка последних ошибок в логах
        log_path = os.path.join(PROJECT_ROOT, "system.log")
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                last_lines = f.readlines()[-20:]
                errors = [line for line in last_lines if "Error" in line or "Exception" in line or "Traceback" in line]
                if errors:
                    results.append(f"❌ Найдены ошибки в логах:\n{''.join(errors[:5])}")
                else:
                    results.append("✅ Ошибок в логах не обнаружено.")

        # 2. Проверка синтаксиса ключевых файлов
        critical_files = ["main.py", "agents/smith.py", "agents/llm_provider.py"]
        for f in critical_files:
            path = os.path.join(PROJECT_ROOT, f)
            try:
                subprocess.check_call([sys.executable, "-m", "py_compile", path],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                results.append(f"❌ Синтаксическая ошибка в файле: {f}")

        return "\n".join(results)
    except Exception as e:
        return f"Ошибка при диагностике: {e}"

def self_upgrade_handler(file_path: str, new_content: str) -> str:
    """Обновить собственный код."""
    try:
        # Защита путей
        abs_path = os.path.abspath(os.path.expanduser(file_path))
        if not abs_path.startswith(PROJECT_ROOT):
            return "ОШИБКА: Попытка изменения файлов вне проекта запрещена."

        # Бэкап
        with open(abs_path, 'r') as f:
            old = f.read()
        with open(abs_path + ".bak", 'w') as f:
            f.write(old)

        # Запись
        with open(abs_path, 'w') as f:
            f.write(new_content)

        return f"✅ Успешно обновлено: {file_path}. Изменения вступят в силу после перезапуска."
    except Exception as e:
        return f"❌ Ошибка апгрейда: {e}"

self_diagnose_tool = {
    "name": "self_diagnose",
    "description": "Провести диагностику системы (логи, синтаксис). Используйте это, если чувствуете ошибки в работе.",
    "parameters": {"type": "object", "properties": {}},
    "handler": self_diagnose_handler
}

self_upgrade_tool = {
    "name": "self_upgrade",
    "description": "Обновить файл кода проекта. Используйте для самоисправления и апгрейда.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Путь к файлу"},
            "new_content": {"type": "string", "description": "Весь новый код файла"}
        },
        "required": ["file_path", "new_content"]
    },
    "handler": self_upgrade_handler
}
