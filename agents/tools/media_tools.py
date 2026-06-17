"""
TTS и Whisper инструменты для Agent Smith.
"""
import os
import sys

# Добавляем agents в path для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _tts_handler(text: str, voice: str = None) -> str:
    """Синтез речи через edge-tts."""
    from agents.tts import speak
    try:
        path = speak(text, voice=voice)
        return f"AUDIO:{path}"
    except Exception as e:
        return f"Error: {e}"


def _whisper_handler(audio_path: str, language: str = "ru") -> str:
    """Распознавание речи через Whisper tiny."""
    from agents.whisper_module import transcribe_file
    try:
        text = transcribe_file(audio_path, language=language)
        return text
    except Exception as e:
        return f"Error: {e}"


tts_tool = {
    "name": "tts",
    "description": "Синтез речи. Преобразует текст в аудио (mp3). Используй когда пользователь просит озвучить, проговорить, сказать голосом.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Текст для озвучки (макс ~8000 символов)"
            },
            "voice": {
                "type": "string",
                "description": "Голос (по умолчанию ru-RU-SvetlanaNeural). Варианты: ru-RU-SvetlanaNeural, ru-RU-DmitryNeural, en-US-JennyNeural"
            }
        },
        "required": ["text"]
    },
    "handler": _tts_handler
}

whisper_tool = {
    "name": "whisper",
    "description": "Распознавание речи. Преобразует аудио в текст. Используй когда приходит голосовое сообщение или аудио файл.",
    "parameters": {
        "type": "object",
        "properties": {
            "audio_path": {
                "type": "string",
                "description": "Путь к аудио файлу"
            },
            "language": {
                "type": "string",
                "description": "Код языка (ru, en и т.д.)"
            }
        },
        "required": ["audio_path"]
    },
    "handler": _whisper_handler
}
