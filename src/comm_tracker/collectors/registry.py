"""采集器注册中心——自动发现和管理所有采集器。"""

import logging
from typing import Type

from comm_tracker.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

# 全局注册表
_registry: dict[str, Type[BaseCollector]] = {}


def register(cls: Type[BaseCollector]) -> Type[BaseCollector]:
    """注册采集器类。可作为装饰器使用。"""
    name = cls.collector_name
    if not name:
        raise ValueError(f"采集器 {cls.__name__} 缺少 collector_name")
    if name in _registry:
        logger.warning("采集器 '%s' 已注册，将被覆盖", name)
    _registry[name] = cls
    return cls


def get_collector(name: str) -> Type[BaseCollector] | None:
    """按名称获取采集器类。"""
    return _registry.get(name)


def list_collectors() -> dict[str, Type[BaseCollector]]:
    """列出所有已注册的采集器。"""
    return dict(_registry)


def auto_discover() -> None:
    """自动导入并注册所有采集器模块。"""
    import importlib
    from pathlib import Path

    collectors_dir = Path(__file__).parent
    subdirs = ["official", "news", "social", "patents", "finance"]

    for subdir in subdirs:
        pkg_dir = collectors_dir / subdir
        if not pkg_dir.is_dir():
            continue
        for py_file in pkg_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = f"comm_tracker.collectors.{subdir}.{py_file.stem}"
            try:
                mod = importlib.import_module(module_name)
                # 查找模块中的 BaseCollector 子类
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseCollector)
                        and attr is not BaseCollector
                        and attr.collector_name
                    ):
                        register(attr)
            except Exception:
                logger.warning("导入采集器模块失败: %s", module_name, exc_info=True)
