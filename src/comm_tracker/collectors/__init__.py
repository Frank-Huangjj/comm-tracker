"""采集器框架。"""

from comm_tracker.collectors.base import BaseCollector, ParsedItem, RawItem
from comm_tracker.collectors.registry import register, get_collector, list_collectors

__all__ = ["BaseCollector", "ParsedItem", "RawItem", "register", "get_collector", "list_collectors"]
