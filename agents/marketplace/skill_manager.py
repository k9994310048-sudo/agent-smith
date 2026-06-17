"""
Менеджер навыков (Skill Marketplace) для Agent Smith.
Позволяет искать и устанавливать новые навыки.
"""
import json
import os
import urllib.request
import logging

logger = logging.getLogger(__name__)

SKILLS_DIR = os.path.expanduser("~/.agent-smith/skills")

def install_skill_handler(skill_name: str, source_url: str = None) -> str:
    """Установить новый навык из JSON-файла."""
    os.makedirs(SKILLS_DIR, exist_ok=True)

    if not source_url:
        # Псевдо-маркетплейс: если URL не указан, берем из нашего "реестра"
        registry = {
            "coder": "https://raw.githubusercontent.com/example/agent-smith-skills/main/coder.json",
            "translator": "https://raw.githubusercontent.com/example/agent-smith-skills/main/translator.json"
        }
        source_url = registry.get(skill_name.lower())

    if not source_url:
        return f"Ошибка: Навык '{skill_name}' не найден в реестре и URL не указан."

    try:
        with urllib.request.urlopen(source_url, timeout=10) as response:
            skill_data = json.loads(response.read().decode())

        file_path = os.path.join(SKILLS_DIR, f"{skill_name}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(skill_data, f, indent=2, ensure_ascii=False)

        return f"Навык '{skill_name}' успешно установлен. Перезапустите агента для активации."
    except Exception as e:
        return f"Ошибка при установке навыка: {str(e)}"

install_skill_tool = {
    "name": "install_skill",
    "description": "Установить новый навык (скилл) для агента. Используйте, если вам не хватает способностей для решения задачи.",
    "parameters": {
        "type": "object",
        "properties": {
            "skill_name": {"type": "string", "description": "Имя навыка"},
            "source_url": {"type": "string", "description": "URL JSON-файла навыка (опционально)"}
        },
        "required": ["skill_name"]
    },
    "handler": install_skill_handler
}
