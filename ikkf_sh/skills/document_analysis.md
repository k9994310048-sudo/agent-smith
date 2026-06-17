---
name: document_analysis
version: 1.0.0
tags: analysis, documents
performance: 0.00
usage: 0
updated: 2026-06-13T02:30:27.993141
hash: daba4c5f
---

# Document Analysis

## Описание
Анализ документов (PDF, DOCX, TXT) и извлечение ключевой информации.

## Алгоритм
1. Определить тип документа
2. Извлечь текст (pymupdf / marker-pdf)
3. Выделить ключевые сущности, факты, связи
4. Сохранить в IKKF как узлы графа
5. Вернуть summary + key facts
