"""
LLM Provider v4.2 — Absolute Stability.
Truly async, resource-aware, and failure-proof.
Fixes: reduced timeout, explicit timeout handling.
"""
import json
import logging
import os
from pathlib import Path
import httpx
import asyncio
import yaml
import os
from typing import List, Dict, Any, AsyncGenerator, Optional

logger = logging.getLogger("llm-provider")

class LLMProvider:
    def __load_env(self):
        _p = Path(__file__).resolve().parent.parent / ".env"
        if _p.exists():
            for _l in _p.read_text().splitlines():
                _l = _l.strip()
                if _l and not _l.startswith("#") and "=" in _l:
                    _k, _v = _l.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._local_model = None
        self.__load_env()
        self.load_config()

    def load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                _raw = f.read()
                import re as _re
                _raw = _re.sub(r'\$\{([^}]+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), _raw)
                # Handle ENV_XXX placeholders
                for _m in list(_re.finditer(r'ENV_([A-Z_]+)', _raw)):
                    _var = _m.group(1)
                    _val = os.environ.get(_var, '')
                    if _val:
                        _raw = _raw.replace(_m.group(0), '"' + _val + '"')
                self.cfg = yaml.safe_load(_raw)
        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            self.cfg = {"models": {"primary": {}, "fallback": {}, "routing": {}}}

    def _get_cpu_load(self) -> float:
        try:
            load = os.getloadavg()[0]
            return (load / 2.0) * 100.0
        except: return 0.0

    async def generate_stream(self, messages: List[Dict], tools: List[Dict] = None, max_tokens: int = 1024) -> AsyncGenerator:
        """Intelligent routing with robust error handling."""

        m_cfg = self.cfg.get("models", {})
        primary = m_cfg.get("primary", {})
        routing = m_cfg.get("routing", {})

        architect_note = (
            "\n[INSTRUCTION: You are Agent Smith AGI v4.4. "
            "Execute Perceive->Reason->Act->Learn cycle. "
            "Use tools for any facts. Be extremely concise.]"
        )
        local_messages = [dict(m) for m in messages]
        for msg in local_messages:
            if msg.get("role") == "system":
                msg["content"] = str(msg.get("content", "")) + architect_note
                break

        use_api = routing.get("use_api", True)

        if routing.get("resource_aware") and self._get_cpu_load() > 85:
            logger.info("High CPU load detected. Forcing API usage to save local resources.")
            use_api = True

        # 3. Attempt Primary API (FIX 3: reduced timeout + retry)
        if use_api and primary.get("api_key"):
            base_url = primary.get("base_url", "").rstrip("/")
            api_key = primary.get("api_key")
            model_name = primary.get("model", "own-alpha")

            max_attempts = 3
            for attempt in range(max_attempts):
                timeout_val = 90.0 if attempt == 0 else 60.0
                try:
                    async with httpx.AsyncClient(timeout=timeout_val) as client:
                        payload = {
                            "model": model_name,
                            "messages": local_messages,
                            "stream": True,
                            "temperature": 0.2
                        }
                        if tools:
                            payload["tools"] = tools

                        async with client.stream(
                            "POST",
                            f"{base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}"},
                            json=payload
                        ) as resp:
                            if resp.status_code == 429:
                                # Rate limited — respect Retry-After header
                                retry_after = int(resp.headers.get("Retry-After", 0))
                                wait = retry_after if retry_after > 0 else min(10 * (2 ** attempt), 120)
                                logger.warning(f"Rate limited (429). Waiting {wait}s (attempt {attempt+1}/{max_attempts})")
                                await asyncio.sleep(wait)
                                continue

                            if resp.status_code != 200:
                                err_body = await resp.aread()
                                raise Exception(f"API Error {resp.status_code}: {err_body.decode()}")

                            async for line in resp.aiter_lines():
                                if line.startswith("data: ") and "[DONE]" not in line:
                                    try:
                                        chunk = json.loads(line[6:])
                                        if chunk and chunk.get("choices"):
                                            delta = chunk["choices"][0].get("delta", {})
                                            if delta: yield delta
                                    except json.JSONDecodeError:
                                        continue
                    return  # Success

                except httpx.TimeoutException:
                    logger.warning(f"API timeout (attempt {attempt+1}, timeout={timeout_val}s)")
                    if attempt < max_attempts - 1:
                        wait = min(5 * (2 ** attempt), 30)
                        logger.info(f"Retrying in {wait}s with reduced context...")
                        await asyncio.sleep(wait)
                        if len(local_messages) > 3:
                            local_messages = local_messages[:1] + local_messages[-2:]
                        continue
                    else:
                        yield {"content": f"🚨 API timeout after {max_attempts} attempts. Переключаюсь на локальную модель..."}

                except Exception as e:
                    logger.error(f"Primary LLM (API) failed: {e}. Failover triggered.")
                    if not routing.get("auto_failover", True):
                        yield {"content": f"🚨 API Error: {str(e)}"}
                        return
                    break  # Fall through to local

        # 4. Fallback: Local LLM
        fallback_cfg = m_cfg.get("fallback", {})
        try:
            if not self._local_model:
                from llama_cpp import Llama
                model_path = os.path.expanduser(fallback_cfg.get("path", ""))
                if not os.path.exists(model_path):
                    yield {"content": "🚨 Error: Neither API nor Local model found."}
                    return

                loop = asyncio.get_event_loop()
                self._local_model = await loop.run_in_executor(None, lambda: Llama(
                    model_path=model_path,
                    n_ctx=fallback_cfg.get("n_ctx", 2048),
                    n_threads=fallback_cfg.get("n_threads", 2),
                    verbose=False
                ))

            loop = asyncio.get_event_loop()
            def get_local_stream():
                return self._local_model.create_chat_completion(
                    messages=local_messages, stream=True, tools=tools, max_tokens=max_tokens
                )

            # Limit local model to prevent infinite loops
            local_stream = await asyncio.wait_for(
                loop.run_in_executor(None, get_local_stream),
                timeout=120.0
            )
            for chunk in local_stream:
                if chunk and chunk.get("choices"):
                    yield chunk["choices"][0].get("delta", {})

        except Exception as e:
            logger.error(f"Local LLM Fallback failed: {e}")
            yield {"content": f"🚨 Critical Error: All LLM providers failed. {str(e)}"}

    async def generate(self, messages: List[Dict], tools: List[Dict] = None, max_tokens: int = 1024) -> Dict:
        """Synchronous wrapper around the async stream."""
        content = ""
        tool_calls = {}
        async for delta in self.generate_stream(messages, tools, max_tokens):
            if delta.get("content"):
                content += delta["content"]

            t_calls = delta.get("tool_calls")
            if t_calls:
                for tc in t_calls:
                    idx = tc.get("index", 0)
                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": tc.get("id"), "function": {"name": "", "arguments": ""}}
                    if tc.get("id"): tool_calls[idx]["id"] = tc["id"]
                    fn = tc.get("function", {})
                    if fn.get("name"): tool_calls[idx]["function"]["name"] = fn["name"]
                    if fn.get("arguments"): tool_calls[idx]["function"]["arguments"] += fn["arguments"]

        return {"content": content, "tool_calls": list(tool_calls.values())}

    @property
    def mode(self) -> str:
        primary_model = self.cfg.get("models", {}).get("primary", {}).get("model", "unknown")
        return f"v4.2 Hybrid ({primary_model})"