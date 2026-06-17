"""
IKKF Graph API — FastAPI сервер

Порт: 8766 (не 8765 — тот занят текущим IKKF)

Endpoints:
  POST   /node              — создать узел
  GET    /node/{id}         — получить узел
  PUT    /node/{id}         — обновить узел
  DELETE /node/{id}         — удалить узел
  GET    /nodes             — список узлов (с фильтрами)

  POST   /edge              — создать связь
  GET    /edge/{id}         — получить связь
  DELETE /edge/{id}         — удалить связь

  GET    /neighbors/{id}    — соседи узла
  GET    /path/{from}/{to}  — путь между узлами

  GET    /search            — поиск (text / context / vector)
  GET    /context           — контекст для LLM (связанные узлы)
  GET    /predict/{id}      — предсказать связанные

  #  POST   /consolidate       — запустить консолидацию (УДАЛЕНО — используйте consolidate.sh)
  GET    /stats             — статистика
  GET    /health            — проверка работоспособности
"""

import json
import os
import sys
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
import uvicorn

# Добавляем путь к graph модулю
try:
    from .graph import Graph
    from .node import Node, Edge, NODE_TYPES, EDGE_TYPES, CONTEXT_DIMS
    from .fill_context import fill_heuristic
except (ImportError, ValueError):
    from graph import Graph
    from node import Node, Edge, NODE_TYPES, EDGE_TYPES, CONTEXT_DIMS
    from fill_context import fill_heuristic

try:
    from reranker import get_reranker
except Exception:  # reranker опционален — поиск работает и без него
    get_reranker = None


# ---- Reciprocal Rank Fusion ----
# Объединяет несколько ранжированных списков по РАНГУ, а не по сырым скорам.
# Решает проблему несопоставимых шкал BM25 (0..∞) и косинуса (0..1).
# Формула (Cormack 2009, стандарт Elastic/Weaviate): score = Σ 1/(k + rank).
RRF_K = 60
# Сколько топ-кандидатов после RRF отдавать на cross-encoder.
# Реранкинг дорогой на CPU (особенно под нехватку RAM), поэтому пул маленький.
RERANK_POOL = 12
# Обрезка текста документа перед reranking. Для оценки релевантности
# достаточно начала; полный текст в 3000+ символов резко замедляет CPU.
RERANK_DOC_CHARS = 500


def _rrf_fuse(*ranked_lists):
    """
    ranked_lists: списки node_id, каждый уже отсортирован по убыванию
    релевантности (лучший первым). Возвращает {node_id: rrf_score}.
    """
    scores = {}
    for ranked in ranked_lists:
        for rank, node_id in enumerate(ranked, start=1):
            scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def _rerank_results(query, results, text_getter, top_k=None):
    """
    Переранжировать список результатов cross-encoder'ом по релевантности
    запросу. text_getter(result) -> текст документа. Возвращает results,
    отсортированный по rerank-скору; в каждый dict добавляется 'rerank'.
    Если reranker недоступен — возвращает results без изменений.
    """
    if get_reranker is None or not results:
        return results
    try:
        rr = get_reranker()
        # Режем пул кандидатов: реранкинг дорогой, оцениваем только топ-RERANK_POOL
        # (results уже отсортированы RRF/скором, лучшие сверху).
        pool = results[:RERANK_POOL]
        tail = results[RERANK_POOL:]
        docs = [(text_getter(r) or "")[:RERANK_DOC_CHARS] for r in pool]
        scores = rr.score(query, docs)
        for r, s in zip(pool, scores):
            r["rerank"] = round(float(s), 4)
        pool = sorted(pool, key=lambda x: x.get("rerank", -1e9), reverse=True)
        results = pool + tail
    except Exception:
        # любой сбой reranker не должен ронять поиск
        return results
    return results[:top_k] if top_k else results


# ---- Путь к БД ----

IKKF_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(IKKF_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "graph.db")
os.makedirs(DATA_DIR, exist_ok=True)

# ---- Приложение ----

app = FastAPI(
    title="IKKF Graph API",
    version="1.0",
    description="Граф знаний для AI-агентов",
)

# Глобальный граф (инициализируется при старте)
graph: Graph = None


@app.on_event("startup")
async def startup():
    global graph
    graph = Graph(DB_PATH)
    # Резидентная загрузка reranker — модель в RAM сразу, чтобы первый
    # поиск не платил ~7с за загрузку. Пик ~626МБ (int8). Если модель
    # отсутствует/упала — поиск продолжит работать на RRF без rerank.
    if get_reranker is not None:
        try:
            rr = get_reranker()
            rr.score("init", ["warmup"])  # прогрев: загрузка + первый прогон
            print(f"[startup] reranker загружен резидентно (loaded={rr.loaded})")
        except Exception as e:
            print(f"[startup] reranker не загружен ({e}) — поиск на RRF без rerank")


@app.on_event("shutdown")
async def shutdown():
    if graph:
        graph.close()


# ---- Pydantic модели ----

class NodeCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    node_type: str = Field(default="fact", description=f"Тип узла: {NODE_TYPES}")
    context: Optional[dict] = Field(default=None, description=f"Контекст: {CONTEXT_DIMS}")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)
    source: str = Field(default="api")
    project: str = Field(default="default")
    verified: int = Field(default=0, description="0=unverified, 1=verified")
    embedding: Optional[List[float]] = None

class NodeUpdate(BaseModel):
    content: Optional[str] = None
    node_type: Optional[str] = None
    context: Optional[dict] = None
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    project: Optional[str] = None
    metadata: Optional[dict] = None

class EdgeCreate(BaseModel):
    source_id: str
    target_id: str
    edge_type: str = Field(default="semantic", description=f"Тип связи: {EDGE_TYPES}")
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    bidirectional: bool = False

class ProjectCreate(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None

class DocumentCreate(BaseModel):
    id: str
    project_id: str
    source: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None

class ChunkCreate(BaseModel):
    id: str
    document_id: str
    project_id: str
    content: str
    position: int = 0


# ---- Health ----

@app.get("/health")
async def health():
    """Liveness probe - process alive."""
    return {"status": "ok", "service": "ikkf-graph-api", "version": "1.0"}

@app.get("/ready")
async def ready():
    """Readiness probe - DB ready."""
    try:
        db_path = os.path.join(os.path.dirname(__file__), "..", "data", "graph.db")
        if os.path.exists(db_path):
            size = os.path.getsize(db_path)
            return {"status": "ready", "db": "ok", "db_size_mb": round(size / 1024 / 1024, 1)}
        return {"status": "not_ready", "db": "missing"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/deep")
async def deep():
    """Deep health check - all dependencies."""
    import shutil
    checks = {}
    try:
        stat = shutil.disk_usage("/")
        free_pct = stat.free / stat.total * 100
        checks["disk"] = {"ok": free_pct > 10, "free_pct": round(free_pct, 1)}
    except Exception as e:
        checks["disk"] = {"ok": False, "error": str(e)}
    try:
        db_path = os.path.join(os.path.dirname(__file__), "..", "data", "graph.db")
        checks["db"] = {"ok": os.path.exists(db_path)}
    except Exception as e:
        checks["db"] = {"ok": False, "error": str(e)}
    all_ok = all(v.get("ok") for v in checks.values())
    return {"status": "healthy" if all_ok else "degraded", "checks": checks}


# ---- Nodes ----

@app.post("/node")
async def create_node(data: NodeCreate):
    """Создать узел с автозаполнением контекстных измерений."""
    try:
        # Автозаполнение контекста если не передан
        context = data.context
        if not context or all(v is None for v in context.values()):
            context = fill_heuristic(data.content)

        # Source-based spatial: приоритетнее чем эвристики по тексту
        # Если source явно указывает на origin — переопределяем эвристику
        if context:
            src = (data.source or "").lower()
            if src in ("api", "conversation", "dialog", "chat"):
                context["spatial"] = "conversation"
            elif any(src.endswith(ext) for ext in (".py", ".sh", ".js", ".go", ".rs", ".c", ".cpp", ".java")):
                context["spatial"] = "server"
            elif "://" in src:
                context["spatial"] = "external"
            elif src.startswith("/") or src.startswith("~"):
                context["spatial"] = "filesystem"

        node = graph.add_node(
            content=data.content,
            node_type=data.node_type,
            embedding=data.embedding,
            context=context,
            importance=data.importance,
            tags=data.tags,
            source=data.source,
            project=data.project,
            verified=data.verified,
            auto_embed=True,  # генерировать embedding при создании
        )
        return {"status": "created", "node": node.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/node/{node_id}")
async def get_node(node_id: str):
    """Получить узел по ID."""
    node = graph.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    return node.to_dict()

@app.put("/node/{node_id}")
async def update_node(node_id: str, data: NodeUpdate):
    """Обновить узел."""
    kwargs = {k: v for k, v in data.dict().items() if v is not None}
    node = graph.update_node(node_id, **kwargs)
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    return {"status": "updated", "node": node.to_dict()}

@app.delete("/node/{node_id}")
async def delete_node(node_id: str):
    """Удалить узел."""
    if graph.delete_node(node_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Узел не найден")


@app.get("/node/{node_id}/history")
async def get_node_history(node_id: str):
    """Получить историю изменений узла."""
    node = graph.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    return {"node_id": node_id, "content": node.content, "history": node.history}


@app.post("/node/{node_id}/revert")
async def revert_node(node_id: str):
    """Откатить узел к предыдущей версии (последней в history)."""
    node = graph.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    if not node.history:
        raise HTTPException(status_code=400, detail="Нет предыдущих версий для отката")
    # берём последнюю запись из history
    prev = node.history[-1]
    node.update_content(prev["content"], reason=f"откат к версии от {prev['created']}")
    # удаляём использованную запись из history (чтобы не было дублей при повторном откате)
    node.history.pop()
    graph.storage.save_node(node)
    return {"status": "reverted", "node": node.to_dict()}


@app.get("/node/{node_id}/summary")
async def get_node_summary(node_id: str):
    """Получить краткую сводку узла для context compression."""
    node = graph.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    return {"node_id": node_id, "summary": node.get_summary(), "full_length": len(node.content)}


@app.post("/node/{node_id}/compress")
async def compress_node(node_id: str, max_chars: int = Query(default=500, ge=100, le=5000)):
    """Сжать длинный контент узла: сохранить summary, обрезать content если нужно."""
    node = graph.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    if len(node.content) <= max_chars:
        return {"status": "no_change", "message": "Контент уже короткий"}
    # сохраняем summary (первые max_chars символов)
    summary = node.content[:max_chars].rsplit(" ", 1)[0] + "..."
    node.set_summary(summary)
    graph.storage.save_node(node)
    return {"status": "compressed", "summary": summary}


@app.get("/nodes/long")
async def list_long_nodes(threshold: int = Query(default=1000, ge=100), limit: int = 50):
    """Список длинных узлов для context compression."""
    nodes = graph.storage.list_long_nodes(threshold=threshold, limit=limit)
    return {"nodes": [{"id": n.id, "length": len(n.content), "project": n.project, "summary": n.get_summary()} for n in nodes], "count": len(nodes)}


@app.post("/nodes/summarize")
async def summarize_long_nodes(threshold: int = Query(default=500, ge=100), limit: int = Query(default=50, le=200)):
    """Массовая генерация summary для длинных узлов без summary."""
    nodes = graph.storage.list_long_nodes(threshold=threshold, limit=limit)
    updated = 0
    skipped = 0
    for node in nodes:
        meta = node.metadata if isinstance(node.metadata, dict) else json.loads(node.metadata) if node.metadata else {}
        if meta.get('summary'):
            skipped += 1
            continue
        if node.content and len(node.content) > threshold:
            summary = graph.storage._generate_summary(node.content)
            if summary:
                meta['summary'] = summary
                node.metadata = meta
                graph.storage.save_node(node, auto_summary=False)
                updated += 1
    return {"updated": updated, "skipped": skipped, "total": len(nodes)}


@app.get("/nodes")
async def list_nodes(
    node_type: Optional[str] = None,
    project: Optional[str] = None,
    status: str = "active",
    limit: int = Query(default=50, le=500),
    offset: int = 0,
):
    """Список узлов с фильтрами."""
    nodes = graph.storage.list_nodes(
        node_type=node_type, project=project, status=status, limit=limit, offset=offset
    )
    total = graph.storage.count_nodes(node_type=node_type, project=project)
    return {"nodes": [n.to_dict() for n in nodes], "total": total, "limit": limit, "offset": offset}


# ---- Edges ----

@app.post("/edge")
async def create_edge(data: EdgeCreate):
    """Создать связь."""
    try:
        edge = graph.add_edge(
            source_id=data.source_id,
            target_id=data.target_id,
            edge_type=data.edge_type,
            weight=data.weight,
            bidirectional=data.bidirectional,
        )
        if not edge:
            raise HTTPException(status_code=400, detail="Один из узлов не найден")
        return {"status": "created", "edge": edge.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/edge/{edge_id}")
async def get_edge(edge_id: str):
    """Получить связь."""
    edge = graph.storage.get_edge(edge_id)
    if not edge:
        raise HTTPException(status_code=404, detail="Связь не найдена")
    return edge.to_dict()

@app.delete("/edge/{edge_id}")
async def delete_edge(edge_id: str):
    """Удалить связь."""
    if graph.storage.delete_edge(edge_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Связь не найдена")


# ---- Graph traversal ----

@app.get("/neighbors/{node_id}")
async def get_neighbors(
    node_id: str,
    direction: str = Query(default="both", regex="^(in|out|both)$"),
    edge_type: Optional[str] = None,
    min_weight: float = 0.0,
):
    """Получить соседей узла."""
    if not graph.storage.get_node(node_id):
        raise HTTPException(status_code=404, detail="Узел не найден")
    neighbors = graph.get_neighbors(node_id, direction=direction, edge_type=edge_type, min_weight=min_weight)
    return {"neighbors": neighbors, "count": len(neighbors)}

@app.get("/path/{from_id}/{to_id}")
async def find_path(from_id: str, to_id: str, max_depth: int = Query(default=5, le=10)):
    """Найти путь между узлами."""
    path = graph.find_path(from_id, to_id, max_depth=max_depth)
    return {"path": path, "length": len(path), "found": len(path) > 0}


# ---- Search ----

def _filter_by_context(graph, results: list, filters: dict) -> list:
    """Filter search results by context dimensions.

    filters: {"spatial": "server", "emotional": "positive", ...}
    Uses LIKE matching on JSON context stored in nodes.context column.
    """
    if not filters:
        return results

    # Context is stored as JSON in nodes.context column
    # Filter in Python since we already have the results with node data
    filtered = []
    for r in results:
        node = r.get("node", r)
        ctx = node.get("context", {})
        if not isinstance(ctx, dict):
            try:
                ctx = json.loads(ctx) if ctx else {}
            except (json.JSONDecodeError, TypeError):
                ctx = {}
        match = True
        for dim, val in filters.items():
            ctx_val = ctx.get(dim, "")
            if ctx_val is None or val.lower() not in str(ctx_val).lower():
                match = False
                break
        if match:
            filtered.append(r)
    return filtered


@app.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    search_type: str = Query(default="text", regex="^(text|context|vector|hybrid)$"),
    project: Optional[str] = None,
    source: Optional[str] = Query(default=None, description="Filter by source (e.g. 'book:python-lectures')"),
    limit: int = Query(default=20, le=100),
    # Context dimension filters
    ctx_temporal: Optional[str] = Query(default=None, description="Filter by temporal context"),
    ctx_spatial: Optional[str] = Query(default=None, description="Filter by spatial context"),
    ctx_social: Optional[str] = Query(default=None, description="Filter by social context"),
    ctx_emotional: Optional[str] = Query(default=None, description="Filter by emotional context"),
    ctx_semantic: Optional[str] = Query(default=None, description="Filter by semantic context"),
):
    """Поиск по графу: text, context, vector, hybrid. Optional context dimension filters."""
    # When any post-filter is active, search wider then trim — otherwise filtered
    # nodes may never reach the top-N and get lost.
    has_filter = bool(source or project or ctx_temporal or ctx_spatial or
                      ctx_social or ctx_emotional or ctx_semantic)
    search_limit = min(limit * 10, 200) if has_filter else limit

    if search_type == "text":
        nodes = graph.search_text(q, limit=search_limit)
        results = [{"node": n.to_dict(), "score": n.importance} for n in nodes]
    elif search_type == "context":
        nodes = graph.context_search(semantic=q)
        results = [{"node": n.to_dict(), "score": n.importance} for n in nodes[:search_limit]]
    elif search_type == "vector":
        # Получаем embedding для запроса из старого IKKF
        query_embedding = _get_query_embedding(q)
        if query_embedding:
            vec_results = graph.vector_search(query_embedding, limit=search_limit, project=project)
            results = [{"node": r["node"].to_dict(), "score": r["score"]} for r in vec_results]
        else:
            # Fallback на текстовый поиск
            nodes = graph.search_text(q, limit=limit)
            results = [{"node": n.to_dict(), "score": n.importance} for n in nodes]
    elif search_type == "hybrid":
        # BM25 + Vector hybrid search через RRF (Reciprocal Rank Fusion).
        # Вместо суммы несопоставимых скоров объединяем по РАНГУ.
        fts_results = graph.storage.search_nodes_fts_ranked(q, limit=search_limit)
        # FTS5 rank: меньший (более отрицательный) = релевантнее → сортируем по возр. abs? 
        # search_nodes_fts_ranked уже возвращает по релевантности; берём порядок как есть.
        fts_ranked = [r["node_id"] for r in fts_results]

        # Vector search
        query_embedding = _get_query_embedding(q)
        vec_results = []
        if query_embedding:
            vec_results = graph.vector_search(query_embedding, limit=search_limit, project=project)
        vec_ranked = [r["node"].id for r in vec_results]

        # RRF: объединяем два ранжированных списка по рангу
        rrf_scores = _rrf_fuse(fts_ranked, vec_ranked)

        combined = {}
        for nid, rrf_s in rrf_scores.items():
            node = graph.storage.get_node(nid)
            if not node:
                continue
            combined[nid] = {"node": node.to_dict(), "score": round(rrf_s, 6),
                             "rrf": round(rrf_s, 6)}
        results = sorted(combined.values(), key=lambda x: x["score"], reverse=True)
        if not has_filter:
            results = results[:search_limit]

    else:
        raise HTTPException(status_code=400, detail=f"Неизвестный тип поиска: {search_type}")

    # Apply source filter (e.g. only book nodes)
    if source:
        results = [r for r in results
                   if source.lower() in str(r.get("node", {}).get("source", "")).lower()]

    # Apply project filter (post-filter — covers text/hybrid where project wasn't applied at query level)
    if project:
        results = [r for r in results
                   if project.lower() == str(r.get("node", {}).get("project", "")).lower()]

    # Apply context dimension filters
    ctx_filters = {
        "temporal": ctx_temporal,
        "spatial": ctx_spatial,
        "social": ctx_social,
        "emotional": ctx_emotional,
        "semantic": ctx_semantic,
    }
    active_filters = {k: v for k, v in ctx_filters.items() if v is not None}
    if active_filters:
        results = _filter_by_context(graph, results, active_filters)

    # Cross-encoder reranking: переоценивает релевантность пары (запрос, текст)
    # напрямую. Применяется к отфильтрованному пулу кандидатов, затем обрезка.
    results = _rerank_results(
        q, results,
        text_getter=lambda r: r.get("node", {}).get("content", ""),
        top_k=limit,
    )

    # Trim to requested limit after all filters applied (на случай если rerank выкл.)
    results = results[:limit]

    return {
        "query": q,
        "type": search_type,
        "results": results,
        "count": len(results),
    }

@app.get("/context/{node_id}")
async def get_context(
    node_id: str,
    depth: int = Query(default=2, ge=1, le=5),
    min_weight: float = 0.3,
):
    """Получить контекст для LLM (узел + связанные узлы)."""
    node = graph.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")

    related = graph.bfs(node_id, max_depth=depth, min_weight=min_weight)

    return {
        "center": node.to_dict(),
        "related": related,
        "context_text": _build_context_text(node, related),
    }


@app.get("/context")
async def search_context(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    depth: int = Query(default=2, ge=1, le=5),
    min_weight: float = 0.3,
    limit: int = Query(default=5, le=20),
):
    """Поиск контекста по тексту (находит узлы и их соседей)."""
    nodes = graph.search_text(q, limit=limit)
    if not nodes:
        return {"center": None, "related": [], "context_text": "", "query": q}

    # Берём самый релевантный узел как центр
    center = nodes[0]
    related = graph.bfs(center.id, max_depth=depth, min_weight=min_weight)

    return {
        "center": center.to_dict(),
        "related": related,
        "context_text": _build_context_text(center, related),
        "query": q,
    }

@app.get("/predict/{node_id}")
async def predict_related(node_id: str, limit: int = Query(default=10, le=50)):
    """Предсказать связанные узлы (2 хопа)."""
    if not graph.storage.get_node(node_id):
        raise HTTPException(status_code=404, detail="Узел не найден")
    predicted = graph.predict_related(node_id, limit=limit)
    return {"predicted": predicted, "count": len(predicted)}


# ---- RAG ----

class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Вопрос")
    project: Optional[str] = None
    max_nodes: int = Field(default=10, ge=1, le=50)
    max_depth: int = Field(default=2, ge=1, le=5)
    min_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    debug: bool = Field(default=False, description="Debug mode: показать seed/expand/rank детали")


@app.post("/rag")
async def rag_query(req: RAGRequest):
    """RAG запрос через граф знаний. Возвращает контекст для LLM."""
    from graph.graph_rag import GraphRAG
    rag = GraphRAG(graph)
    result = rag.query(
        question=req.query,
        max_context_nodes=req.max_nodes,
        max_depth=req.max_depth,
        min_weight=req.min_weight,
        project=req.project,
    )
    if not req.debug:
        result.pop("context_nodes", None)
    return result


# ---- LLM integration ----

class ParseRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Текст для парсинга")
    project: str = "default"

class ContextFillRequest(BaseModel):
    node_ids: Optional[list[str]] = None
    limit: int = Field(default=20, ge=1, le=100)


# ---- Projects (совместимость со старым IKKF) ----

@app.get("/projects")
async def list_projects():
    """Список проектов."""
    projects = graph.storage.list_projects()
    return {"projects": projects, "count": len(projects)}

@app.post("/project")
async def create_project(data: ProjectCreate):
    """Создать проект."""
    project_id = data.id or data.name.lower().replace(" ", "-").replace("_", "-")
    graph.storage.save_project(project_id, data.name, data.description)
    return {"status": "created", "id": project_id}

@app.get("/project/{project_id}")
async def get_project(project_id: str):
    """Получить проект."""
    project = graph.storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return project


# ---- Documents (совместимость со старым IKKF) ----

@app.get("/documents")
async def list_documents(project_id: Optional[str] = None, limit: int = Query(default=100, le=500)):
    """Список документов."""
    documents = graph.storage.list_documents(project_id=project_id, limit=limit)
    return {"documents": documents, "count": len(documents)}

@app.post("/document")
async def create_document(data: DocumentCreate):
    """Создать документ."""
    graph.storage.save_document(data.id, data.project_id, data.source, data.file_type, data.file_size)
    return {"status": "created", "id": data.id}


# ---- Chunks (совместимость со старым IKKF) ----

@app.get("/chunks")
async def list_chunks(
    document_id: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = Query(default=100, le=500),
):
    """Список чанков."""
    chunks = graph.storage.list_chunks(document_id=document_id, project_id=project_id, limit=limit)
    return {"chunks": chunks, "count": len(chunks)}

@app.post("/chunk")
async def create_chunk(data: ChunkCreate):
    """Создать чанк."""
    graph.storage.save_chunk(data.id, data.document_id, data.project_id, data.content, data.position)
    return {"status": "created", "id": data.id}

@app.get("/search/chunks")
async def search_chunks(
    q: str = Query(..., min_length=1),
    project_id: Optional[str] = None,
    limit: int = Query(default=20, le=100),
):
    """Полнотекстовый поиск по чанкам (FTS5)."""
    chunks = graph.storage.search_chunks_fts(q, project_id=project_id, limit=limit)
    return {"query": q, "results": chunks, "count": len(chunks)}


# ---- Maintenance ----

# NOTE: /consolidated endpoint removed — use consolidate.sh script instead
# to avoid database lock issues (API service holds DB connection).
# Run: bash /root/projects/i-know-kung-fu/graph/consolidate.sh

@app.get("/stats")
async def stats():
    """Статистика графа."""
    return graph.stats()


# ---- Helpers ----

def _get_query_embedding(query: str) -> Optional[list]:
    """Получить embedding для запроса через fastembed."""
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding(
            model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
        )
        embeddings = list(model.embed([query]))
        if embeddings:
            return embeddings[0].tolist()
    except Exception:
        pass
    return None


def _build_context_text(center: Node, related: list) -> str:
    """Построить текстовый контекст для LLM."""
    lines = [f"[Центр] {center.content}"]
    for r in related:
        node = r["node"]
        edge = r["edge"]
        lines.append(f"  → [{edge['edge_type']}] {node['content']}")
    return "\n".join(lines)


# ---- Vector search & hybrid RAG ----

@app.get("/search/vector")
async def search_vector(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    limit: int = Query(default=10, le=50, ge=1),
    min_score: float = Query(default=0.3, le=1.0, ge=0.0, description="Минимальный cosine similarity"),
):
    """Векторный поиск по embeddings (sqlite-vec с fallback на brute-force)."""
    try:
        from fastembed import TextEmbedding

        if not hasattr(graph.storage, '_embed_model') or graph.storage._embed_model is None:
            graph.storage._embed_model = TextEmbedding(
                model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
            )

        query_emb = list(graph.storage._embed_model.embed([q]))[0]

        # Fast vector search (sqlite-vec or brute-force fallback)
        fast_results = graph.storage.vector_search_fast(query_emb, limit=limit, min_score=min_score)

        results = []
        for r in fast_results:
            node = graph.storage.get_node(r["node_id"])
            if node and node.status == "active":
                results.append({
                    "node_id": r["node_id"],
                    "content": node.content[:200],
                    "score": r["score"],
                    "node_type": node.node_type,
                })

        return {"query": q, "results": results, "count": len(results), "method": "vector"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vector search error: {e}")


@app.get("/search/hybrid")
async def search_hybrid(
    q: str = Query(default=None, min_length=1, description="Поисковый запрос"),
    query: str = Query(default=None, min_length=1, description="Поисковый запрос (алиас для q)"),
    limit: int = Query(default=10, le=50, ge=1),
    vector_weight: float = Query(default=0.7, le=1.0, ge=0.0, description="Вес vector search (0=pure FTS5, 1=pure vector)"),
    debug: bool = Query(default=False, description="Debug mode: показать seed/expand/rank детали"),
):
    """Гибридный поиск: FTS5 keyword + vector similarity. Результаты объединяются и ранжируются."""
    search_query = q or query
    if not search_query:
        raise HTTPException(status_code=400, detail="Параметр 'q' или 'query' обязателен")
    import numpy as np

    # 1. FTS5 search
    fts_results = graph.storage.search_nodes_fts_ranked(search_query, limit=limit * 2)
    fts_scores = {}
    for r in fts_results:
        # bm25 rank: ближе к 0 = лучше. Нормализуем в 0..1
        rank = r.get("rank", 0)
        fts_scores[r["node_id"]] = abs(rank) if rank != 0 else 0.5

    # Нормализуем FTS5 scores в 0..1 (больше = лучше)
    if fts_scores:
        max_rank = max(fts_scores.values()) or 1.0
        fts_scores = {k: 1.0 - (v / max_rank) for k, v in fts_scores.items()}

    # 2. Vector search (fast sqlite-vec or brute-force fallback)
    vec_scores = {}
    try:
        from fastembed import TextEmbedding
        if not hasattr(graph.storage, '_embed_model') or graph.storage._embed_model is None:
            graph.storage._embed_model = TextEmbedding(
                model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
            )
        query_emb = list(graph.storage._embed_model.embed([search_query]))[0]

        # Use fast vector search
        fast_results = graph.storage.vector_search_fast(query_emb, limit=limit * 2, min_score=0.0)
        for r in fast_results:
            vec_scores[r["node_id"]] = r["score"]
    except Exception:
        pass

    # 3. Объединяем через RRF (Reciprocal Rank Fusion) — по рангу, не по скору.
    # vector_weight сохранён в сигнатуре для совместимости, но RRF его не требует.
    fts_ranked = sorted(fts_scores.keys(), key=lambda k: fts_scores[k], reverse=True)
    vec_ranked = sorted(vec_scores.keys(), key=lambda k: vec_scores[k], reverse=True)
    rrf_scores = _rrf_fuse(fts_ranked, vec_ranked)

    combined = []
    for node_id, rrf_s in rrf_scores.items():
        node = graph.get_node(node_id)
        if node and node.status == "active":
            combined.append({
                "node_id": node_id,
                "content": node.content,  # полный текст для reranker; обрежем ниже
                "score": round(rrf_s, 6),
                "rrf_score": round(rrf_s, 6),
                "fts_score": round(fts_scores.get(node_id, 0.0), 4),
                "vec_score": round(vec_scores.get(node_id, 0.0), 4),
                "node_type": node.node_type,
            })

    combined.sort(key=lambda x: x["score"], reverse=True)
    # Cross-encoder reranking топ-кандидатов по релевантности запросу
    combined = _rerank_results(
        search_query, combined,
        text_getter=lambda r: r.get("content", ""),
        top_k=limit,
    )
    # Обрезаем content до 200 символов для ответа (после reranking)
    for r in combined:
        r["content"] = r["content"][:200]
    response = {
        "query": search_query,
        "results": combined[:limit],
        "count": len(combined),
        "method": "hybrid",
        "vector_weight": vector_weight,
    }
    if debug:
        response["debug"] = {
            "fts_count": len(fts_scores),
            "vec_count": len(vec_scores),
            "combined_count": len(all_ids),
            "fts_top": sorted(fts_scores.items(), key=lambda x: x[1], reverse=True)[:5],
            "vec_top": sorted(vec_scores.items(), key=lambda x: x[1], reverse=True)[:5],
        }
    return response


# ---- Heuristic fill-context (быстрый, без LLM) ----

@app.post("/fill-context")
async def fill_context(req: ContextFillRequest):
    """Заполнить контекстуальные измерения через эвристики (без LLM). Скорость: <0.01с на узел."""
    if req.node_ids:
        nodes = [graph.get_node(nid) for nid in req.node_ids]
        nodes = [n for n in nodes if n]
    else:
        nodes = graph.storage.list_nodes(limit=req.limit)

    filled = 0
    skipped = 0
    for node in nodes:
        ctx = node.context or {}
        # Заполняем только пустые измерения
        needs = [d for d in ['spatial', 'emotional', 'social', 'semantic', 'temporal'] if not ctx.get(d)]
        if not needs:
            skipped += 1
            continue

        # Эвристическое заполнение
        heuristic = graph.storage.fill_context_heuristic(node.content)
        changed = False
        for dim in needs:
            val = heuristic.get(dim, "")
            if val:
                node.set_context(dim, val)
                # Сохраняем в node_contexts
                try:
                    graph.storage.conn.execute(
                        'INSERT OR REPLACE INTO node_contexts (node_id, context_dim, value) VALUES (?, ?, ?)',
                        (node.id, dim, str(val))
                    )
                except Exception:
                    pass
                changed = True
                filled += 1

        if changed:
            graph.storage.save_node(node)

    graph.storage.conn.commit()
    return {
        "filled": filled,
        "nodes_processed": len(nodes),
        "skipped_already_filled": skipped,
        "method": "heuristic",
    }


# ---- Maintenance endpoints ----

@app.post("/consolidate")
async def consolidate():
    """Запустить консолидацию графа (дедуп, decay, re-rank)."""
    try:
        from consolidation import Consolidator
        c = Consolidator(graph)
        result = c.run()
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/fts-sync")
async def fts_sync():
    """Пересоздать FTS5 индекс."""
    try:
        conn = graph.storage.conn
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM nodes_fts")
        old_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM nodes WHERE status='active'")
        node_count = cur.fetchone()[0]

        if old_count != node_count:
            # Удаляем старую таблицу и триггеры
            cur.execute("DROP TABLE IF EXISTS nodes_fts")
            cur.execute("DROP TRIGGER IF EXISTS nodes_fts_ai")
            cur.execute("DROP TRIGGER IF EXISTS nodes_fts_au")
            # Создаём с правильной схемой (node_id, project)
            cur.execute("""
                CREATE VIRTUAL TABLE nodes_fts USING fts5(
                    content, node_id UNINDEXED, project UNINDEXED,
                    tokenize='unicode61'
                )
            """)
            cur.execute("INSERT INTO nodes_fts(rowid, content, node_id, project) SELECT rowid, content, id, project FROM nodes WHERE status='active'")
            # Пересоздаём триггеры
            cur.execute("""
                CREATE TRIGGER nodes_fts_ai AFTER INSERT ON nodes BEGIN
                    INSERT INTO nodes_fts(rowid, content, node_id, project)
                    VALUES (new.rowid, new.content, new.id, new.project);
                END
            """)
            cur.execute("""
                CREATE TRIGGER nodes_fts_au AFTER UPDATE ON nodes BEGIN
                    DELETE FROM nodes_fts WHERE node_id = old.id;
                    INSERT INTO nodes_fts(rowid, content, node_id, project)
                    VALUES (new.rowid, new.content, new.id, new.project);
                END
            """)
            conn.commit()
            return {"status": "synced", "old": old_count, "new": node_count}
        return {"status": "ok", "count": node_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---- Async parse (job queue) ----

# In-memory job store (simple, for single-worker setup)
_parse_jobs = {}


@app.post("/parse", status_code=202)
async def parse_text_async(req: ParseRequest):
    """
    Асинхронный парсинг текста через LLM.
    Возвращает job_id. Результат доступен через GET /jobs/{job_id}/result
    """
    import uuid
    job_id = str(uuid.uuid4())[:8]

    _parse_jobs[job_id] = {
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "text": req.text[:1000],
        "result": None,
        "error": None,
    }

    # Запускаем в фоне (для production — отдельный worker)
    import asyncio
    asyncio.create_task(_run_parse_job(job_id, req))

    return {"job_id": job_id, "status": "pending", "message": "Используйте GET /jobs/{job_id} для проверки статуса"}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Проверить статус задачи."""
    job = _parse_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "status": job["status"], "created_at": job["created_at"]}


@app.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """Получить результат задачи."""
    job = _parse_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] == "pending":
        raise HTTPException(status_code=202, detail="Job still processing")
    if job["status"] == "error":
        raise HTTPException(status_code=500, detail=job["error"])
    return {"job_id": job_id, "status": "done", "result": job["result"]}


async def _run_parse_job(job_id: str, req: ParseRequest):
    """Фоновая обработка parse через LLM."""
    import asyncio
    job = _parse_jobs[job_id]
    job["status"] = "processing"

    try:
        # Вызываем LLM в thread pool чтобы не блокировать event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _sync_parse, req)
        job["result"] = result
        job["status"] = "done"
    except Exception as e:
        job["error"] = str(e)
        job["status"] = "error"


def _sync_parse(req: ParseRequest) -> dict:
    """Синхронный парсинг через LLM. Выполняется в отдельном потоке."""
    try:
        from kungfu_llm import get_llm
        llm = get_llm()
    except Exception as e:
        return {"error": f"LLM недоступна: {e}"}

    text = req.text[:2000]
    # English prompt works better for Qwen 1.5B with Russian text
    prompt = (
        "Extract structured data from the text. Answer ONLY in JSON format:\n"
        '{"entities": [{"name": "...", "type": "person/project/server/model/other"}], '
        '"facts": ["..."], "summary": "..."}\n'
        "Don't make up info. Use only the text provided.\n\n"
        "Example:\n"
        'Text: "John works at Google"\n'
        'Output: {"entities": [{"name": "John", "type": "person"}, {"name": "Google", "type": "project"}], '
        '"facts": ["John works at Google"], "summary": "John works at Google"}\n\n'
        f"Text: {text}\n"
        "Output:"
    )
    import re, json
    result = llm(prompt, max_tokens=500, temperature=0.1, stop=['</s>'])
    result_text = result['choices'][0]['text'].strip()
    json_str = re.search(r'\{.*\}', result_text, re.DOTALL)
    if json_str:
        try:
            data = json.loads(json_str.group())
            # Normalize keys
            if "entities" not in data:
                data["entities"] = []
            if "facts" not in data:
                data["facts"] = []
            if "summary" not in data:
                data["summary"] = ""
            data["classification"] = {"type": "fact"}
            data["importance"] = 0.5
            data["tags"] = []
            return data
        except json.JSONDecodeError:
            pass

    # Fallback: return raw text
    return {"entities": [], "facts": [], "summary": "", "raw_llm_output": result_text}


# ---- Killer API (простой интерфейс для внешних пользователей) ----

class AddRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Текст для добавления")
    metadata: dict = Field(default_factory=dict, description="Метаданные")
    project: str = "default"

class QueryRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Текст запроса")
    limit: int = Field(default=5, ge=1, le=20)
    project: str = None

class GraphRequest(BaseModel):
    node_id: str = Field(..., description="ID центрального узла")
    depth: int = Field(default=2, ge=1, le=5)
    min_weight: float = Field(default=0.3, ge=0.0, le=1.0)

@app.post("/api/v1/add")
async def add_text(req: AddRequest):
    """Добавить текст в граф. Автоматически создаёт узлы и связи."""
    from graph.graph_rag import GraphRAG
    rag = GraphRAG(graph)
    nodes = rag.add_from_text(req.text, source="api", project=req.project)
    return {
        "status": "ok",
        "nodes_created": len(nodes),
        "node_ids": [n.id for n in nodes],
    }

@app.post("/api/v1/query")
async def query_graph(req: QueryRequest):
    """Запрос к графу. Возвращает релевантные узлы и контекст."""
    from graph.graph_rag import GraphRAG
    rag = GraphRAG(graph)
    result = rag.query(
        question=req.text,
        max_context_nodes=req.limit,
        project=req.project,
    )
    return {
        "status": "ok",
        "question": result["question"],
        "context": result["context_text"],
        "stats": result["stats"],
    }

@app.post("/api/v1/graph")
async def get_graph(req: GraphRequest):
    """Получить подграф вокруг узла. Если node_id не найден — вернуть общую статистику."""
    center = graph.get_node(req.node_id)
    if not center:
        # Fallback: вернуть общую статистику и последние узлы
        recent = graph.storage.list_nodes(limit=10)
        return {
            "status": "ok",
            "center": None,
            "message": f"Node '{req.node_id}' not found, showing recent nodes",
            "recent_nodes": [n.to_dict() for n in recent],
            "stats": graph.stats(),
        }
    bfs = graph.bfs(req.node_id, max_depth=req.depth, min_weight=req.min_weight)
    return {
        "status": "ok",
        "center": center.to_dict(),
        "neighbors": bfs,
        "total_neighbors": len(bfs),
    }


# ---- Main ----

if __name__ == "__main__":
    port = int(os.environ.get("IKKF_GRAPH_PORT", "8766"))
    print(f"Starting IKKF Graph API on port {port}")
    print(f"DB: {DB_PATH}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
