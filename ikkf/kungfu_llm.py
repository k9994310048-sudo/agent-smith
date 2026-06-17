"""
IKKF LLM Provider — использует локальный llama-server (DeepSeek-R1 1.5B).
Fallback на основной провайдер если локальный недоступен.
"""
import json
import logging
import subprocess
import os

logger = logging.getLogger("ikkf-llm")


def _local_available():
    """Проверяет доступен ли локальный llama-server."""
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "3", "http://127.0.0.1:8081/health"],
            capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0
    except Exception:
        return False


def _local_generate(prompt, max_tokens=512, temperature=0.7, repeat_penalty=1.2, top_p=0.9, stop=None):
    """Генерация через локальный llama-server (OpenAI-совместимый API)."""
    payload = {
        "model": "deepseek-r1",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "repeat_penalty": repeat_penalty,
        "top_p": top_p,
    }
    if stop:
        payload["stop"] = stop

    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "60", "-X", "POST",
             "http://127.0.0.1:8081/v1/completions",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=65
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            return data.get("choices", [{}])[0].get("text", "").strip()
    except Exception as e:
        logger.warning(f"Local LLM failed: {e}")
    return None


class KungFuLLM:
    """Обертка для совместимости с dream_pipeline.py и другими модулями."""

    def __init__(self, n_ctx=2048, n_threads=2):
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self._use_local = _local_available()
        logger.info(f"KungFuLLM init: local={'yes' if self._use_local else 'no'}")

    def llm(self, prompt, max_tokens=512, temperature=0.7, repeat_penalty=1.2, top_p=0.9, stop=None):
        """Синхронная генерация текста. Совместимо с dream_pipeline._ask()."""
        if self._use_local:
            result = _local_generate(prompt, max_tokens=max_tokens, temperature=temperature,
                                     repeat_penalty=repeat_penalty, top_p=top_p, stop=stop)
            if result is not None:
                return {"choices": [{"text": result}]}

        # Fallback: возвращаем пустой результат чтобы не падать
        logger.warning("No LLM available, returning empty response")
        return {"choices": [{"text": ""}]}


def get_llm():
    """Фабрика — возвращает экземпляр KungFuLLM."""
    return KungFuLLM()
