"""IKKF Graph — Граф знаний для AI-агентов"""

try:
    from .node import Node, Edge, NODE_TYPES, EDGE_TYPES, CONTEXT_DIMS
    from .storage import Storage
    from .graph import Graph
except (ImportError, ValueError):
    from node import Node, Edge, NODE_TYPES, EDGE_TYPES, CONTEXT_DIMS
    from storage import Storage
    from graph import Graph

__version__ = "2.0.0"
__all__ = ["Node", "Edge", "Storage", "Graph", "NODE_TYPES", "EDGE_TYPES", "CONTEXT_DIMS"]
