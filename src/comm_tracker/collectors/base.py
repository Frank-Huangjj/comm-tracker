"""采集器抽象基类——所有数据源适配器的统一接口。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from comm_tracker.models.base import SourceType
from comm_tracker.models.checkpoint import CollectionCheckpoint


@dataclass
class RawItem:
    """采集到的原始数据项。"""

    url: str
    content: str  # 原始 HTML 或文本
    metadata: dict = field(default_factory=dict)
    published_at: datetime | None = None


@dataclass
class ParsedItem:
    """解析后的结构化数据项。"""

    title: str
    original_url: str
    content_raw: str
    content_clean: str = ""
    published_at: datetime | None = None
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    extra_metadata: dict = field(default_factory=dict)
    category: str | None = None
    summary: str | None = None


class BaseCollector(ABC):
    """所有采集器的基类。

    子类需实现 collect() 和 parse() 方法。
    run() 方法编排完整的 collect → parse → 返回结果 流程。
    """

    collector_name: str = ""
    source_type: SourceType = SourceType.OFFICIAL
    supported_manufacturers: list[str] = []
    needs_js: bool = False  # 是否需要 Playwright 渲染

    @abstractmethod
    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        """从数据源获取原始数据。"""

    @abstractmethod
    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        """将原始数据解析为结构化数据。"""

    async def run(self, manufacturer: str, checkpoint: CollectionCheckpoint | None = None) -> list[ParsedItem]:
        """执行完整采集流程：collect → parse。"""
        since = checkpoint.last_collected_at if checkpoint else None
        raw_items = await self.collect(manufacturer, since)

        results: list[ParsedItem] = []
        for raw in raw_items:
            parsed_list = await self.parse(raw)
            results.extend(parsed_list)

        return results
