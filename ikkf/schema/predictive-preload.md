# Predictive Preload System

## Принцип
Как мозг предсказывает что понадобится — AI предзагружает связанные узлы графа заранее.

## Алгоритм

### 1. Анализ текущего контекста
```python
def analyze_context(conversation_history, current_query):
    """Извлекает активные темы из разговора"""
    topics = extract_topics(current_query)
    recent_topics = extract_topics(conversation_history[-5:])
    return list(set(topics + recent_topics))
```

### 2. Поиск связанных узлов
```python
def find_related_nodes(active_topics, graph, max_depth=2):
    """BFS по графу от активных тем"""
    related = set()
    queue = [(topic, 0) for topic in active_topics]
    
    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        
        # Находим узлы связанные с текущей темой
        neighbors = graph.neighbors(current)
        for neighbor in neighbors:
            if neighbor not in related:
                related.add(neighbor)
                queue.append((neighbor, depth + 1))
    
    return related
```

### 3. Ранжирование по вероятности использования
```python
def rank_by_probability(related_nodes, context):
    """Оценивает вероятность что узел понадобится"""
    ranked = []
    for node in related_nodes:
        score = 0.0
        
        # Частота использования
        score += node.context.usage_count * 0.3
        
        # Свежесть
        hours_old = (now() - node.context.created).hours
        score += max(0, 1.0 - hours_old / 168) * 0.2  # неделя
        
        # Важность
        score += node.metadata.importance * 0.3
        
        # Связь с текущим контекстом
        common_topics = set(node.tags) & set(context.topics)
        score += len(common_topics) * 0.2
        
        ranked.append((node, score))
    
    return sorted(ranked, key=lambda x: x[1], reverse=True)
```

### 4. Подгрузка в кэш
```python
def preload_to_cache(ranked_nodes, cache, max_items=20):
    """Подгружает топ-N узлов в RAM-кэш"""
    for node, score in ranked_nodes[:max_items]:
        if not cache.contains(node.id):
            cache.put(node.id, node)
            logger.debug(f"Preloaded: {node.id} (score: {score:.2f})")
```

### 5. Фоновый процесс
```python
def predictive_preload_loop():
    """Запускается после каждого сообщения"""
    while True:
        # Ждём нового сообщения
        message = wait_for_message()
        
        # Анализируем контекст
        topics = analyze_context(history, message)
        
        # Находим связанные
        related = find_related_nodes(topics, graph)
        
        # Ранжируем
        ranked = rank_by_probability(related, context)
        
        # Подгружаем
        preload_to_cache(ranked, cache)
        
        # Обновляем счётчики доступа
        update_access_counts(topics)
```

## Структура кэша

```python
class NodeCache:
    def __init__(self, max_size_mb=100):
        self.max_size = max_size_mb * 1024 * 1024
        self.current_size = 0
        self.nodes = {}  # id -> node
        self.access_order = []  # LRU
    
    def put(self, node_id, node):
        node_size = len(node.content.encode('utf-8'))
        
        # Вытесняем если нужно
        while self.current_size + node_size > self.max_size:
            self.evict()
        
        self.nodes[node_id] = node
        self.access_order.append(node_id)
        self.current_size += node_size
    
    def get(self, node_id):
        if node_id in self.nodes:
            # Обновляем LRU
            self.access_order.remove(node_id)
            self.access_order.append(node_id)
            return self.nodes[node_id]
        return None
    
    def evict(self):
        if self.access_order:
            oldest = self.access_order.pop(0)
            node = self.nodes.pop(oldest)
            self.current_size -= len(node.content.encode('utf-8'))
```

## Интеграция с графом

```python
class PredictiveGraph:
    def __init__(self, graph, cache):
        self.graph = graph
        self.cache = cache
        self.preload_queue = Queue()
    
    def query(self, query_text, context):
        # 1. Анализ контекста
        topics = analyze_context(context, query_text)
        
        # 2. Поиск в кэше
        cached_results = []
        for topic in topics:
            node = self.cache.get(topic)
            if node:
                cached_results.append(node)
        
        # 3. Поиск в граф (если не нашли в кэше)
        if not cached_results:
            graph_results = self.graph.search(topics)
            # Подгружаем найденное в кэш
            for node in graph_results:
                self.cache.put(node.id, node)
            cached_results = graph_results
        
        # 4. Запускаем предиктивную подгрузку
        self.preload_queue.put(topics)
        
        return cached_results
```
