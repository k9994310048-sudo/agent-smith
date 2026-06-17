"""IKKF — Integrations with third-party frameworks."""

try:
    from .langchain import IKKFGraphMemory, get_langchain_memory
except ImportError:
    from langchain import IKKFGraphMemory, get_langchain_memory

__all__ = ["IKKFGraphMemory", "get_langchain_memory"]
