"""三星电子新闻采集器——基于 RSS Feed。

Samsung Newsroom 的页面需要 JS 渲染且加载缓慢，
但其 RSS Feed (https://news.samsung.com/global/feed) 稳定可用，
包含标题、链接、发布日期、分类等完整信息。
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime

from dateutil import parser as date_parser

from comm_tracker.collectors.base import BaseCollector, ParsedItem, RawItem
from comm_tracker.models.base import SourceType
from comm_tracker.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

RSS_URL = "https://news.samsung.com/global/feed"
MAX_ITEMS = 20


class SamsungNewsCollector(BaseCollector):
    """三星电子新闻采集器（RSS Feed）。"""

    collector_name = "samsung_news"
    source_type = SourceType.OFFICIAL
    supported_manufacturers = ["samsung"]
    needs_js = False

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None
        items: list[RawItem] = []
        try:
            xml_text = await self.client.get_text(RSS_URL)
            items.extend(self._parse_rss(xml_text, since))
        except Exception:
            logger.exception("三星 RSS feed 采集失败")
        return items

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=raw.content,
                published_at=raw.published_at,
                author="Samsung",
                tags=raw.metadata.get("tags", []),
                extra_metadata={"source": "samsung_rss"},
                category="industry_news",
            )
        ]

    def _parse_rss(self, xml_text: str, since: datetime | None = None) -> list[RawItem]:
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            return []

        items: list[RawItem] = []
        for item in channel.findall("item")[:MAX_ITEMS]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date_str = item.findtext("pubDate", "")

            if not title or not link:
                continue

            published_at = None
            if pub_date_str:
                try:
                    parsed = date_parser.parse(pub_date_str)
                    # 统一转换为 naive datetime（去掉时区信息）
                    published_at = parsed.replace(tzinfo=None)
                except (ValueError, TypeError):
                    pass

            # 增量过滤
            if since and published_at and published_at <= since:
                continue

            # 提取分类标签
            tags = [cat.text for cat in item.findall("category") if cat.text]

            items.append(
                RawItem(
                    url=link,
                    content=title,
                    metadata={"from_list": True, "title": title, "tags": tags},
                    published_at=published_at,
                )
            )

        logger.info("三星 RSS feed 提取到 %d 条", len(items))
        return items
