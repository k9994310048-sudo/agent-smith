#!/usr/bin/env python3
"""
IKKF Reranker — лёгкий cross-encoder для переранжирования результатов поиска.

Зачем: гибридный поиск (BM25 + vector) смешивает шкалы и пускает в топ
короткий диалоговый шум. Cross-encoder оценивает РЕЛЕВАНТНОСТЬ пары
(запрос, документ) напрямую и расставляет результаты правильно.

Модель: jina-reranker-v2-base-multilingual, int8 ONNX (~267 МБ на диске).
  - Мультиязычная (русский работает корректно)
  - int8-квантование: ~790 МБ RAM пик (против 1890 МБ у fp32)
  - Скорость на CPU: топ-20 за ~0.3 сек

Дизайн под слабое железо:
  - lazy load: модель грузится только при первом вызове rerank()
  - жёсткие лимиты потоков и памяти ONNX (настраиваются через env)
  - модель можно выгрузить из RAM методом unload()

ENV-переменные (необязательные):
  IKKF_RERANK_THREADS     — число потоков ONNX (default: 1)
  IKKF_RERANK_MAXLEN      — макс. длина токенов на документ (default: 512)
  IKKF_RERANK_MODEL_DIR   — путь к папке с model_int8.onnx + tokenizer.json
"""

import os
import threading
from typing import List, Tuple, Optional

import numpy as np

# ---- Пути / конфиг ----

_DEFAULT_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "reranker",
)
MODEL_DIR = os.environ.get("IKKF_RERANK_MODEL_DIR", _DEFAULT_MODEL_DIR)
MODEL_FILE = os.path.join(MODEL_DIR, "model_int8.onnx")
TOKENIZER_FILE = os.path.join(MODEL_DIR, "tokenizer.json")

THREADS = int(os.environ.get("IKKF_RERANK_THREADS", "2"))
MAX_LEN = int(os.environ.get("IKKF_RERANK_MAXLEN", "256"))


class Reranker:
    """Cross-encoder reranker с ленивой загрузкой и лимитом памяти."""

    def __init__(self, threads: int = THREADS, max_len: int = MAX_LEN):
        self.threads = threads
        self.max_len = max_len
        self._sess = None
        self._tok = None
        self._input_names = None
        self._lock = threading.Lock()

    # ---- Ленивая загрузка ----

    def _ensure_loaded(self):
        if self._sess is not None:
            return
        with self._lock:
            if self._sess is not None:
                return
            if not os.path.exists(MODEL_FILE):
                raise FileNotFoundError(
                    f"Reranker модель не найдена: {MODEL_FILE}\n"
                    f"Скачай model_int8.onnx из "
                    f"jinaai/jina-reranker-v2-base-multilingual/onnx/"
                )
            import onnxruntime as ort
            from tokenizers import Tokenizer

            so = ort.SessionOptions()
            # --- жёсткие лимиты под слабое железо ---
            so.intra_op_num_threads = self.threads
            so.inter_op_num_threads = 1
            so.enable_cpu_mem_arena = False   # не держать большой пул памяти
            so.enable_mem_pattern = False     # не преаллоцировать под формы
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self._sess = ort.InferenceSession(
                MODEL_FILE, so, providers=["CPUExecutionProvider"]
            )
            self._input_names = {i.name for i in self._sess.get_inputs()}

            tok = Tokenizer.from_file(TOKENIZER_FILE)
            tok.enable_padding()
            tok.enable_truncation(max_length=self.max_len)
            self._tok = tok

    def unload(self):
        """Выгрузить модель из RAM (например, после периода простоя)."""
        with self._lock:
            self._sess = None
            self._tok = None
            self._input_names = None
            import gc
            gc.collect()

    @property
    def loaded(self) -> bool:
        return self._sess is not None

    # ---- Основной API ----

    def score(self, query: str, documents: List[str]) -> List[float]:
        """Вернуть сырые logit-оценки релевантности для каждого документа."""
        if not documents:
            return []
        self._ensure_loaded()
        enc = self._tok.encode_batch([(query, d) for d in documents])
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        inp = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._input_names:
            inp["token_type_ids"] = np.zeros_like(ids)
        inp = {k: v for k, v in inp.items() if k in self._input_names}
        out = self._sess.run(None, inp)
        scores = out[0]
        scores = scores.squeeze(-1) if scores.ndim > 1 else scores
        return [float(s) for s in np.atleast_1d(scores)]

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
    ) -> List[Tuple[int, float]]:
        """
        Переранжировать документы по релевантности запросу.

        Возвращает список (исходный_индекс, score), отсортированный по score
        убыванию. top_k обрезает результат.
        """
        scores = self.score(query, documents)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k] if top_k else ranked


# ---- Синглтон ----

_INSTANCE: Optional[Reranker] = None
_INSTANCE_LOCK = threading.Lock()


def get_reranker() -> Reranker:
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = Reranker()
    return _INSTANCE


if __name__ == "__main__":
    import time
    rr = get_reranker()
    q = "какие исключения возбуждает smtplib при отправке почты"
    docs = [
        "smtplib.SMTPRecipientsRefused — все получатели отвергнуты сервером",
        "User example text for reranker test",
        "urllib.urlopen создает файлоподобный объект",
    ]
    t = time.time()
    res = rr.rerank(q, docs)
    print(f"rerank {len(docs)} docs за {time.time()-t:.2f}s (вкл. загрузку)")
    for idx, sc in res:
        print(f"  [{idx}] {sc:+.3f}  {docs[idx][:50]}")
