"""
Tool Registry v4.1 — Clean and Modular.
Manages all tools available to Agent Smith.
"""
import logging
import json
from typing import Dict, List, Any, Callable, Optional

logger = logging.getLogger("tool-registry")

class Tool:
    def __init__(self, name: str, description: str, parameters: dict, handler: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Tool] = {}

    def register(self, name: str, description: str, parameters: dict, handler: Callable):
        self.tools[name] = Tool(name, description, parameters, handler)

    def get_schemas(self) -> List[dict]:
        return [tool.to_openai_schema() for tool in self.tools.values()]

    def execute(self, name: str, arguments: dict) -> Any:
        if name not in self.tools:
            return f"Error: Tool '{name}' not found."

        tool = self.tools[name]
        try:
            logger.info(f"🔧 Executing {name}...")
            return tool.handler(**arguments)
        except Exception as e:
            logger.error(f"❌ Error in {name}: {e}")
            return f"Error executing {name}: {str(e)}"

_registry = None

def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools(_registry)
    return _registry

def _register_default_tools(registry: ToolRegistry):
    """Register core tools with strict imports."""
    # 1. Web Search
    from agents.tools.web_search import web_search_tool
    registry.register(**web_search_tool)

    # 2. System Tools (Precision version)
    from agents.tools.system_tools import (
        shell_exec_tool,
        file_read_tool,
        project_overview_tool,
        get_system_stats_tool
    )
    registry.register(**shell_exec_tool)
    registry.register(**file_read_tool)
    registry.register(**project_overview_tool)
    registry.register(**get_system_stats_tool)

    # 3. Media Tools (TTS + Whisper)
    from agents.tools.media_tools import tts_tool, whisper_tool
    registry.register(**tts_tool)
    registry.register(**whisper_tool)
