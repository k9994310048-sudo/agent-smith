"""
IKKF Bridge v3.1 — Direct & Lean.
Disabled all heavy background operations for AGI stability.
"""
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("ikkf-bridge")

class IKKFBridge:
    def __init__(self, local_graph=None):
        self.graph = local_graph

    def health(self) -> bool:
        return self.graph is not None

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        if not self.graph: return []
        
        # Check cache first
        cached = self.graph.check_cache(query)
        if cached:
            return [{"node": {"content": cached}, "type": "cached"}]

        # Normal search
        seeds = self.graph.search_text(query, limit=limit)
        return [{"node": n.to_dict(), "type": "seed"} for n in seeds]

    def store(self, content: str, node_type: str = "fact", importance: float = 0.5):
        if self.graph:
            # FORCE auto_embed=False to prevent RAM spikes on 4GB systems
            return self.graph.add_node(
                content=content,
                node_type=node_type,
                importance=importance,
                auto_embed=False,
                auto_link=False
            )

    def stats(self) -> Dict:
        return self.graph.stats() if self.graph else {}
