"""
Whisper модуль для Agent Smith — распознавание речи (tiny model)

Использование:
    from whisper_module import transcribe, transcribe_file
    
    # Из файла
    text = transcribe_file("/path/to/audio.ogg")
    
    # Из аудио данных
    text = transcribe(audio_bytes)
"""

import os
import logging
import tempfile

logger = logging.getLogger(__name__)

# Настройки
DEFAULT_MODEL = "tiny"  # tiny — быстрый, легкий, подходит для макбука
DEFAULT_LANGUAGE = "ru"

# Кэш модели (lazy load)
_model = None


def _get_model(model_name: str = DEFAULT_MODEL):
    """Lazy load whisper модели."""
    global _model
    if _model is None:
        import whisper
        logger.info(f"Loading whisper model: {model_name}...")
        _model = whisper.load_model(model_name)
        logger.info(f"Whisper model loaded: {model_name}")
    return _model


def transcribe_file(audio_path: str, language: str = DEFAULT_LANGUAGE, model_name: str = DEFAULT_MODEL) -> str:
    """
    Распознать речь из аудио файла.
    
    Args:
        audio_path: Путь к аудио файлу
        language: Код языка (ru, en, etc.)
        model_name: Модель whisper (tiny, base, small, medium, large)
    
    Returns:
        Распознанный текст
    """
    model = _get_model(model_name)
    
    result = model.transcribe(
        audio_path,
        language=language,
        fp16=False  # fp16 не поддерживается на CPU
    )
    
    text = result["text"].strip()
    logger.info(f"Transcribed {len(audio_path)} bytes -> {len(text)} chars")
    return text


def transcribe(audio_bytes: bytes, language: str = DEFAULT_LANGUAGE, model_name: str = DEFAULT_MODEL) -> str:
    """
    Распознать речь из аудио данных в памяти.
    
    Args:
        audio_bytes: Аудио данные
        language: Код языка
        model_name: Модель whisper
    
    Returns:
        Распознанный текст
    """
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name
    
    try:
        return transcribe_file(temp_path, language, model_name)
    finally:
        os.unlink(temp_path)


def list_models() -> list:
    """Список доступных моделей whisper."""
    return ["tiny", "base", "small", "medium", "large", "turbo"]


if __name__ == "__main__":
    # Тест — проверка что модель загружается
    print("Loading whisper tiny...")
    model = _get_model("tiny")
    print(f"Model loaded: {model}")
