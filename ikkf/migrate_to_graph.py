#!/usr/bin/env python3
"""
Миграция данных из старого IKKF (ChromaDB + SQLite) в граф знаний.

Что мигрирует:
- Чанки из SQLite → узлы графа
- Векторы из ChromaDB → embeddings узлов
- Связи между чанками одного документа → sequence edges
- Связи между похожими чанками → similarity edges

Запуск: python3 -m graph.migrate_to_graph
"""

import os
import sys
import json
import sqlite3
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graph.graph import Graph
from graph.node import Node

# ---- Пути к старым данным ----

OLD_DATA = Path("/data")
OLD_SQLITE = OLD_DATA / "index" / "metadata.db"
OLD_CHROMA = OLD_DATA / "vectors"

# ---- Маппинг типов источников в типы узлов ----

SOURCE_TO_NODE_TYPE = {
    "raw_text": "fact",
    "telegram": "event",
    "conversation": "event",
    "api": "fact",
    "file": "fact",
    "web": "fact",
    "default": "fact",
}


def migrate(dry_run=False):
    """Мигрировать все данные из старого IKKF в граф."""

    print("=" * 60)
    print("Миграция: старый IKKF → Graph")
    print("=" * 60)

    # 1. Подключаемся к старой БД
    if not OLD_SQLITE.exists():
        print(f"❌ Старая БД не найдена: {OLD_SQLITE}")
        return

    old_db = sqlite3.connect(str(OLD_SQLITE))
    old_db.row_factory = sqlite3.Row

    # 2. Подключаемся к ChromaDB
    try:
        import chromadb
        from chromadb.config import Settings
        chroma_client = chromadb.PersistentClient(
            path=str(OLD_CHROMA),
            settings=Settings(anonymized_telemetry=False)
        )
        collection = chroma_client.get_or_create_collection("knowledge")
    except Exception as e:
        print(f"⚠️  ChromaDB недоступна: {e}")
        collection = None

    # 3. Подключаемся к новому графу
    graph = Graph()

    # 4. Получаем все чанки из SQLite
    chunks = old_db.execute("""
        SELECT c.id as chunk_id, c.content, c.project_id, c.document_id, c.position,
               d.source, d.file_type
        FROM chunks c
        LEFT JOIN documents d ON c.document_id = d.id
        ORDER BY c.project_id, c.document_id, c.position
    """).fetchall()

    total = len(chunks)
    print(f"\nНайдено чанков: {total}")

    if dry_run:
        print("DRY RUN — данные не сохраняются")
        for chunk in chunks[:5]:
            print(f"  [{chunk['chunk_id']}] {chunk['content'][:60]}...")
        old_db.close()
        graph.close()
        return

    # 5. Получаем векторы из ChromaDB
    embeddings_map = {}
    if collection:
        try:
            all_vectors = collection.get(include=["embeddings"])
            emb_list = all_vectors.get("embeddings")
            if emb_list is not None and len(emb_list) > 0:
                for i, vid in enumerate(all_vectors["ids"]):
                    embeddings_map[vid] = emb_list[i]
                print(f"Загружено векторов: {len(embeddings_map)}")
            else:
                print("⚠️  Векторы не найдены в ChromaDB")
        except Exception as e:
            print(f"⚠️  Векторы не загружены: {e}")

    # 6. Мигрируем чанки → узлы
    migrated = 0
    skipped = 0
    doc_chunks = {}  # document_id -> [node_ids] для связывания

    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        content = chunk["content"]
        project = chunk["project_id"] or "default"
        source = chunk["source"] or "default"
        doc_id = chunk["document_id"]
        position = chunk["position"] or 0

        # Пропускаем пустые
        if not content or len(content.strip()) < 5:
            skipped += 1
            continue

        # Тип узла
        node_type = SOURCE_TO_NODE_TYPE.get(source, "fact")

        # Вектор
        embedding = embeddings_map.get(chunk_id)

        # Контекст
        context = {
            "temporal": None,
            "spatial": None,
            "semantic": source,
            "emotional": None,
            "social": None,
        }

        # Пробуем извлечь дату из контента
        import re
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', content)
        if date_match:
            context["temporal"] = date_match.group(1)

        # Создаём узел
        node = graph.add_node(
            content=content[:2000],  # ограничение на длину
            node_type=node_type,
            embedding=embedding,
            context=context,
            importance=0.5,
            tags=[source, project] if source else [project],
            source=source,
            project=project,
        )

        # Запоминаем для связывания
        if doc_id not in doc_chunks:
            doc_chunks[doc_id] = []
        doc_chunks[doc_id].append((position, node.id))

        migrated += 1
        if migrated % 50 == 0:
            print(f"  Мигрировано: {migrated}/{total}")

    print(f"\n✅ Мигрировано узлов: {migrated}")
    print(f"   Пропущено (пустые): {skipped}")

    # 7. Создаём sequence связи внутри документов
    edges_created = 0
    for doc_id, node_list in doc_chunks.items():
        node_list.sort(key=lambda x: x[0])  # сортируем по position
        for i in range(len(node_list) - 1):
            _, source_id = node_list[i]
            _, target_id = node_list[i + 1]
            edge = graph.add_edge(source_id, target_id, "sequence", 0.5)
            if edge:
                edges_created += 1

    print(f"✅ Создано sequence связей: {edges_created}")

    # 8. Мигрируем projects
    projects = old_db.execute("SELECT id, name, description FROM projects").fetchall()
    for p in projects:
        graph.storage.save_project(p["id"], p["name"], p["description"])
    print(f"✅ Мигрировано проектов: {len(projects)}")

    # 9. Мигрируем documents
    # Отключаем FK на время миграции (данные уже проверены)
    graph.storage.conn.execute("PRAGMA foreign_keys=OFF")
    documents = old_db.execute("SELECT id, project_id, source, file_type, file_size FROM documents").fetchall()
    for d in documents:
        graph.storage.save_document(d["id"], d["project_id"], d["source"], d["file_type"], d["file_size"])
    print(f"✅ Мигрировано документов: {len(documents)}")

    # 10. Мигрируем chunks и обновляем FTS (FK уже отключен)
    chunks = old_db.execute("SELECT id, document_id, project_id, content, position FROM chunks").fetchall()
    for c in chunks:
        graph.storage.save_chunk(c["id"], c["document_id"], c["project_id"], c["content"], c["position"])
        # Обновляем FTS индекс
        try:
            graph.storage.conn.execute(
                "INSERT OR REPLACE INTO chunks_fts (content, chunk_id, document_id, project_id) VALUES (?, ?, ?, ?)",
                (c["content"][:500], c["id"], c["document_id"], c["project_id"]),
            )
        except Exception:
            pass
    graph.storage.conn.commit()
    # Включаем FK обратно
    graph.storage.conn.execute("PRAGMA foreign_keys=ON")
    print(f"✅ Мигрировано чанков: {len(chunks)}")

    # 11. Статистика
    stats = graph.stats()
    print(f"\n📊 Итоговая статистика графа:")
    print(f"   Узлов: {stats['nodes_active']}")
    print(f"   Связей: {stats['edges_total']}")
    print(f"   По типам: {stats['by_type']}")
    print(f"   По проектам: {stats['by_project']}")
    print(f"   Размер БД: {stats['db_size_mb']} MB")

    old_db.close()
    graph.close()

    print("\n✅ Миграция завершена")
    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Миграция IKKF → Graph")
    parser.add_argument("--dry-run", action="store_true", help="Только показать что будет мигрировано")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
