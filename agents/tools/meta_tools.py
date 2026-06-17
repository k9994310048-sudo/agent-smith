"""
Meta Tools — Инструменты для самоапгрейда и управления правами.
"""
import os
import logging

logger = logging.getLogger("meta-tools")

def request_permission_handler(action_description: str) -> str:
    """Запросить у пользователя разрешение на выполнение действия."""
    # В v3.2 мы просто помечаем действие как "требующее подтверждения"
    # Бот увидит этот ответ и должен будет спросить пользователя в чате.
    return f"PERMISSION_REQUIRED: {action_description}. Пожалуйста, подтвердите это действие, написав 'РАЗРЕШАЮ: {action_description}'"

def apply_patch_handler(file_path: str, new_content: str) -> str:
    """Применить исправление или апгрейд к файлу."""
    try:
        # 1. Проверяем путь
        if not file_path.startswith("/home/mac/.agent-smith"):
            return "ОШИБКА: Попытка изменения файлов за пределами проекта."

        # 2. Сохраняем старую версию
        with open(file_path, 'r') as f:
            old_content = f.read()

        with open(file_path + ".bak", 'w') as f:
            f.write(old_content)

        # 3. Записываем новую
        with open(file_path, 'w') as f:
            f.write(new_content)

        return f"✅ Файл {file_path} успешно обновлен. Рекомендуется перезапуск."
    except Exception as e:
        return f"❌ Ошибка при применении патча: {e}"

request_permission_tool = {
    "name": "request_permission",
    "description": "Запросить разрешение у владельца на системное действие (апгрейд, удаление, доступ к файлам вне проекта).",
    "parameters": {
        "type": "object",
        "properties": {
            "action_description": {"type": "string", "description": "Описание действия"}
        },
        "required": ["action_description"]
    },
    "handler": request_permission_handler
}

apply_patch_tool = {
    "name": "apply_patch",
    "description": "Применить программный код (патч) к файлу проекта для апгрейда или исправления ошибки.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Путь к файлу"},
            "new_content": {"type": "string", "description": "Полный новый контент файла"}
        },
        "required": ["file_path", "new_content"]
    },
    "handler": apply_patch_handler
}
