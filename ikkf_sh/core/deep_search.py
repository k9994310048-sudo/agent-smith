"""
IKKF_SH — Show Me
Deep Search: ежедневный сбор данных из интернета с глубоким поиском
"""

import json
import logging
import os
import time
import urllib.request
import urllib.parse
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Источники для глубокого поиска
SEARCH_SOURCES = {
    "arxiv": {
        "name": "arXiv (научные статьи)",
        "url": "https://export.arxiv.org/api/query",
        "params": lambda q: {"search_query": f"all:{q}", "max_results": 5}
    },
    "ddg": {
        "name": "DuckDuckGo",
        "url": "https://html.duckduckgo.com/html/",
        "params": lambda q: {"q": q}
    },
    "github": {
        "name": "GitHub Trending",
        "url": "https://api.github.com/search/repositories",
        "params": lambda q: {"q": q, "sort": "stars", "order": "desc"}
    }
}

SEARCH_CACHE_DIR = os.path.expanduser("~/projects/ikkf_sh/data/search_cache")


class DeepSearch:
    """
    Глубокий поиск по нескольким источникам.
    Кэширует результаты, чтобы не дёргать API повторно.
    """

    def __init__(self):
        os.makedirs(SEARCH_CACHE_DIR, exist_ok=True)

    def search(self, query: str, sources: List[str] = None,
               max_results: int = 5) -> Dict[str, List[dict]]:
        """
        Поиск по нескольким источникам одновременно.
        """
        sources = sources or ["arxiv", "ddg"]
        results = {}

        for source in sources:
            if source in SEARCH_SOURCES:
                try:
                    src = SEARCH_SOURCES[source]
                    params = src["params"](query)
                    url = src["url"] + "?" + urllib.parse.urlencode(params)

                    req = urllib.request.Request(url, headers={
                        "User-Agent": "IKKF_SH DeepSearch/1.0"
                    })
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = resp.read().decode("utf-8", errors="ignore")

                    results[source] = {
                        "raw": data[:3000],
                        "url": url,
                        "timestamp": time.time()
                    }
                    logger.info(f"DeepSearch [{source}]: OK")
                except Exception as e:
                    results[source] = {"error": str(e)}
                    logger.warning(f"DeepSearch [{source}]: {e}")

        return results

    def search_and_store(self, query: str, api_url: str = "http://127.0.0.1:8766") -> str:
        """
        Поиск + сохранение результатов в IKKF.
        Возвращает сводку.
        """
        results = self.search(query)
        stored = 0

        for source, data in results.items():
            if "error" in data:
                continue
            fact = f"Deep Search [{source}] {query}: {data.get('raw', '')[:200]}"
            try:
                store_data = json.dumps({
                    "content": fact,
                    "node_type": "fact",
                    "importance": 0.6,
                    "source": "ikkf_sh_deep_search",
                    "tags": ["search", source, query[:50]]
                }).encode()
                req = urllib.request.Request(
                    f"{api_url}/node",
                    data=store_data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    stored += 1
            except Exception as e:
                logger.warning(f"Failed to store search result: {e}")

        return f"Deep Search '{query}': {len(results)} sources, {stored} stored"
