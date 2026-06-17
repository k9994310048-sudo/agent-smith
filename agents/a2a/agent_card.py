"""
Agent Card — Описание возможностей агента в стандарте A2A.
"""
import json
from typing import List, Dict

class AgentCard:
    def __init__(self, name: str, description: str, version: str = "1.0.0"):
        self.name = name
        self.description = description
        self.version = version
        self.capabilities = {
            "tool_calling": True,
            "memory": "ikkf_graph",
            "reasoning": "cot_react"
        }
        self.skills: List[Dict] = []

    def add_skill(self, name: str, description: str):
        self.skills.append({"name": name, "description": description})

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": self.capabilities,
            "skills": self.skills
        }

    def __str__(self):
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
