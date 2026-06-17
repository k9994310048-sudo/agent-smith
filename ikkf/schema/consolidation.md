# Consolidation System — "Сон" для AI

## Принцип
Как мозг консолидирует память во сне — AI ночью перерабатывает знания.

## Что делает консолидация

1. **Объединение дубликатов** — находит похожие узлы и объединяет
2. **Укрепление связей** — усиливает часто используемые связи
3. **Ослабление забытых** — убирает редко используемые связи
4. **Создание абстракций** — группирует конкретные факты в концепции
5. **Архивация** — переносит редкие узлы в холодное хранилище

## Алгоритм

```python
def consolidate():
    """Основной цикл консолидации. Запускается ночью."""
    
    # 1. Находим дубликаты
    duplicates = find_duplicate_nodes(threshold=0.85)
    for group in duplicates:
        merge_nodes(group)
    
    # 2. Укрепляем связи
    hot_paths = get_frequently_accessed_paths()
    for path in hot_paths:
        strengthen_edges(path)
    
    # 3. Ослабляем забытые
    cold_nodes = get_rarely_accessed(days=30)
    for node in cold_nodes:
        weaken_edges(node)
    
    # 4. Создаём абстракции
    clusters = cluster_similar_nodes()
    for cluster in clusters:
        create_abstract_node(cluster)
    
    # 5. Архивируем
    archive_old_nodes(days=90)


def find_duplicate_nodes(threshold=0.85):
    """Находит узлы с высокой семантической похожестью"""
    nodes = get_all_nodes()
    duplicates = []
    
    for i, node_a in enumerate(nodes):
        for node_b in nodes[i+1:]:
            similarity = cosine_similarity(
                node_a.embedding, 
                node_b.embedding
            )
            if similarity > threshold:
                duplicates.append((node_a, node_b, similarity))
    
    return duplicates


def merge_nodes(group):
    """Объединяет группу похожих узлов в один"""
    # Берём самый старый узел как основной
    main = min(group, key=lambda n: n.context.created)
    
    # Собираем все связи от всех узлов
    all_edges = set()
    for node in group:
        all_edges.update(get_edges(node))
    
    # Объединяем контент
    contents = [n.content for n in group]
    main.content = merge_contents(contents)
    main.context.usage_count = sum(n.context.usage_count for n in group)
    
    # Трансферим связи
    for edge in all_edges:
        if edge.source in [n.id for n in group]:
            edge.source = main.id
        if edge.target in [n.id for n in group]:
            edge.target = main.id
    
    # Удаляем дубликаты
    for node in group:
        if node.id != main.id:
            delete_node(node.id)


def strengthen_edges(path):
    """Усиливает связи по часто используемым путям"""
    for edge in path.edges:
        edge.weight = min(1.0, edge.weight * 1.1)


def weaken_edges(node):
    """Ослабляет связи к редко используемым узлам"""
    for edge in get_edges(node):
        edge.weight *= 0.9


def create_abstract_node(cluster):
    """Создаёт абстрактный узел из кластера похожих"""
    # Общие темы кластера
    common_tags = set.intersection(*[set(n.tags) for n in cluster])
    
    # Создаём абстрактный узел
    abstract = Node(
        type="concept",
        content=f"Concept: {', '.join(common_tags)}",
        tags=list(common_tags),
        metadata=Metadata(
            importance=0.5,
            abstract=True
        )
    )
    
    # Связываем все узлы кластера с абстракцией
    for node in cluster:
        create_edge(node, abstract, "instance_of", weight=0.8)
    
    save_node(abstract)


def archive_old_nodes(days=90):
    """Переносит старые неиспользуемые узлы в архив"""
    cutoff = now() - timedelta(days=days)
    
    old_nodes = db.execute(
        "SELECT * FROM nodes WHERE last_accessed < ? AND usage_count < 3",
        (cutoff,)
    ).fetchall()
    
    for row in old_nodes:
        node = Node.from_row(row)
        # Сохраняем в файл
        archive_path = f"/data/graph/archive/{node.context.temporal_group}/{node.id}.json"
        Path(archive_path).parent.mkdir(parents=True, exist_ok=True)
        with open(archive_path, 'w') as f:
            json.dump(node.to_dict(), f)
        
        # Удаляем из основной базы
        db.execute("DELETE FROM nodes WHERE id = ?", (node.id,))
    
    db.commit()
```

## Расписание

```bash
# Каждую ночь в 3:00
0 3 * * * cd /root/projects/i-know-kung-fu && python3 graph/consolidate.py >> /var/log/consolidate.log 2>&1
```

## Мониторинг

```python
def consolidation_report():
    """Отчёт о консолидации"""
    stats = {
        "nodes_before": count_nodes_before,
        "nodes_after": count_nodes_after,
        "duplicates_merged": len(merged),
        "edges_strengthened": len(strengthened),
        "edges_weakened": len(weakened),
        "abstracts_created": len(abstracts),
        "archived": len(archived),
        "duration_seconds": elapsed
    }
    
    logger.info(f"Consolidation report: {stats}")
    return stats
```
