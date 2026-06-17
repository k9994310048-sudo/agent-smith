"""
TTS модуль для Agent Smith — через edge-tts (бесплатный, лёгкий)

Использование:
    from tts import speak, speak_async
    
    # Синхронно
    path = speak("Привет, мир!")
    
    # Асинхронно
    path = await speak_async("Привет, мир!")
"""

import asyncio
import os
import tempfile
import logging

logger = logging.getLogger(__name__)

# Настройки по умолчанию
DEFAULT_VOICE = "ru-RU-SvetlanaNeural"  # Русский женский голос
DEFAULT_LANG = "ru"
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/.agent-smith/audio")


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


async def speak_async(text: str, voice: str = None, output_dir: str = None) -> str:
    """
    Асинхронная генерация речи.
    
    Args:
        text: Текст для озвучки
        voice: Голос (по умолчанию ru-RU-SvetlanaNeural)
        output_dir: Директория для сохранения
    
    Returns:
        Путь к сгенерированному mp3 файлу
    """
    import edge_tts
    
    voice = voice or DEFAULT_VOICE
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    _ensure_dir(output_dir)
    
    # Ограничение длины (edge-tts лимит ~10000 символов)
    if len(text) > 8000:
        text = text[:8000] + "..."
    
    filename = f"tts_{asyncio.get_event_loop().time():.0f}.mp3"
    output_path = os.path.join(output_dir, filename)
    
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)
    
    logger.info(f"TTS generated: {output_path} ({os.path.getsize(output_path)} bytes)")
    return output_path


def speak(text: str, voice: str = None, output_dir: str = None) -> str:
    """
    Синхронная генерация речи.
    
    Args:
        text: Текст для озвучки
        voice: Голос
        output_dir: Директория для сохранения
    
    Returns:
        Путь к сгенерированному mp3 файлу
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(speak_async(text, voice, output_dir))
    finally:
        loop.close()


def list_voices_sync(lang: str = "ru") -> list:
    """Список доступных голосов для языка."""
    import edge_tts
    
    loop = asyncio.new_event_loop()
    try:
        voices = loop.run_until_complete(edge_tts.list_voices())
        return [v for v in voices if v["Locale"].startswith(lang)]
    finally:
        loop.close()


if __name__ == "__main__":
    # Тест
    path = speak("Привет! Это тест синтеза речи для Agent Smith.")
    print(f"Generated: {path}")
