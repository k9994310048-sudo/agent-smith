"""
IKKF_SH — Deep Search
Ежедневный сбор данных из интернета с глубоким поиском.

Принципы:
1. Многослойный поиск: surface → deep → specialized
2. Источники: arXiv, GitHub, HackerNews, Reddit, специализированные блоги
3. Фильтрация по релевантности и свежести
4. Сохранение результатов в IKKF как [source] узлы
5. Приоритет на практическую ценность, а не хайп
"""

from __future__ import annotations
import json
import time
import logging
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

# Источники для глубокого поиска
DEEP_SOURCES = {
    "arxiv": {
        "name": "arXiv",
        "url": "https://export.arxiv.org/api/query",
        "params": lambda q: {"search_query": f"all:{q}", "max_results": 10, "sortBy": "submittedDate"},
    },
    "hackernews": {
        "name": "Hacker News",
        "url": "https://hacker-news.firebaseio.com/v0/topstories.json",
        "parser": "hn_top",
    },
    "github": {
        "name": "GitHub",
        "url": "https://api.github.com/search/repositories",
        "params": lambda q: {"q": f"{q} sort:stars", "per_page": 10},
    },
    "googlescholar": {
        "name": "Google Scholar (via SerpAPI)",
        "url": "",  # Требует API key
        "optional": True,
    },
}


@dataclass
class SearchResult:
    """Результат поиска."""
    title: str
    url: str
    summary: str
    source: str
    published: str = ""
    relevance_score: float = 0.0
    tags: List[str] = field(default_factory=list)


@dataclass
class DeepSearchReport:
    """Отчёт о глубоком поиске."""
    query: str
    timestamp: float = field(default_factory=time.time)
    results: List[SearchResult] = field(default_factory=list)
    summary: str = ""
    key_findings: List[str] = field(default_factory=list)

    def to_ikkf_nodes(self) -> List[dict]:
        """Конвертирует результаты в узлы для IKKF."""
        nodes = []
        for r in self.results:
            if r.relevance_score >= 0.5:
                nodes.append({
                    "content": f"[{r.source}] {r.title}\n{r.summary[:300]}",
                    "node_type": "fact",
                    "importance": r.relevance_score,
                    "source": "deep_search",
                    "tags": r.tags + ["auto_collected"],
                })
        return nodes


class DeepSearch:
    """Многослойный поиск информации в интернете."""

    def __init__(self, ikkf_api_url: str = "http://127.0.0.1:8766"):
        self.api_url = ikkf_api_url

    def search(self, query: str, sources: List[str] = None, max_results: int = 10) -> DeepSearchReport:
        """
        Основной метод поиска.
        1. Быстрый поиск (web_search)
        2. Глубокий поиск (arXiv, GitHub, HN)
        3. Ранжирование и фильтрация
        """
        report = DeepSearchReport(query=query)

        # Слой 1: Быстрый поиск
        logger.info(f"Deep Search: quick layer for '{query}'")
        # (интеграция с web_search tool — вызывается извне)

        # Слой 2: arXiv
        if sources is None or "arxiv" in sources:
            arxiv_results = self._search_arxiv(query)
            report.results.extend(arxiv_results)

        # Слой 3: GitHub
        if sources is None or "github" in sources:
            gh_results = self._search_github(query)
            report.results.extend(gh_results)

        # Ранжирование
        report.results.sort(key=lambda r: r.relevance_score, reverse=True)
        report.results = report.results[:max_results]

        # Сводка
        report.key_findings = [
            f"{r.title} ({r.source}, score: {r.relevance_score:.2f})"
            for r in report.results[:5]
        ]

        return report

    def _search_arxiv(self, query: str) -> List[SearchResult]:
        """Поиск в arXiv."""
        results = []
        try:
            params = f"search_query=all:{urllib.parse.quote(query)}&max_results=10&sortBy=submittedDate&sortOrder=descending"
            url = f"https://export.arxiv.org/api/query?{params}"
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = resp.read().decode("utf-8")

            # Простой парсинг Atom feed
            import xml.etree.ElementTree as ET
            root = ET.fromstring(data)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns)[:5]:
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")[:200]
                url = entry.find("atom:id", ns).text
                published = entry.find("atom:published", ns).text

                # Простая релевантность: пересечение слов
                query_words = set(query.lower().split())
                title_words = set(title.lower().split())
                overlap = len(query_words & title_words) / max(len(query_words), 1)

                results.append(SearchResult(
                    title=title[:150],
                    url=url,
                    summary=summary,
                    source="arXiv",
                    published=published,
                    relevance_score=min(overlap * 2, 1.0),
                    tags=["paper", "research"],
                ))
        except Exception as e:
            logger.warning(f"arXiv search failed: {e}")

        return results

    def _search_github(self, query: str) -> List[SearchResult]:
        """Поиск репозиториев на GitHub."""
        results = []
        try:
            url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}+sort:stars&per_page=10"
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read())

            for item in data.get("items", [])[:5]:
                results.append(SearchResult(
                    title=item["full_name"],
                    url=item["html_url"],
                    summary=(item.get("description") or "")[:200],
                    source="GitHub",
                    relevance_score=min(item.get("stargazers_count", 0) / 10000, 1.0),
                    tags=["code", "repository", "open-source"],
                ))
        except Exception as e:
            logger.warning(f"GitHub search failed: {e}")

        return results

    def daily_collection(self, topics: List[str]) -> Dict[str, DeepSearchReport]:
        """
        Ежедневный сбор данных по списку тем.
        Вызывается из cron или cognitive loop.
        """
        reports = {}
        for topic in topics:
            logger.info(f"Daily collection: {topic}")
            report = self.search(topic, max_results=5)
            reports[topic] = report

            # Сохраняем в IKKF
            try:
                import urllib.request
                for node in report.to_ikkf_nodes():
                    urllib.request.urlopen(
                        urllib.request.Request(
                            f"{self.api_url}/node",
                            data=json.dumps(node).encode(),
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        ),
                        timeout=5,
                    )
            except Exception as e:
                logger.warning(f"Failed to save to IKKF: {e}")

            # Пауза чтобы не перегрузить API
            time.sleep(1)

        return reports
