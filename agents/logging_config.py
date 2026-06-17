"""
JSON logging configuration for Agent Smith.
Uses structlog for structured JSON output.
"""
import logging
import sys
import json
from datetime import datetime

def setup_json_logging(level="INFO"):
    """Configure JSON logging for the application."""
    # Remove existing handlers
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)

    # JSON formatter
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_entry, ensure_ascii=False)

    # Console handler with JSON
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    return root

def get_logger(name):
    """Get a logger with the given name."""
    return logging.getLogger(name)
