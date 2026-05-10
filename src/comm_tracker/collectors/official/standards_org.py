"""行业标准组织新闻采集器 (GSMA & TM Forum)。"""

import logging
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from comm_tracker.collectors.base import BaseCollector, ParsedItem, RawItem
from comm_tracker.models.base import SourceType
from comm_tracker.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

class GSMANewsCollector(BaseCollector):
    collector_name = "gsma_news"
    source_type = SourceType.OFFICIAL
    supported_manufacturers = ["gsma"]
    needs_js = False

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None, "HttpClient 未初始化"
        items: list[RawItem] = []
        try:
            html = await self.client.get_text("https://www.gsma.com/newsroom/")
            soup = BeautifulSoup(html, "lxml")
            for a in soup.select("a[href]"):
                href = a.get("href")
                if href and ("newsroom" in href or "article" in href) and len(href) > 30:
                    title = a.get_text(strip=True)
                    if len(title) > 10:
                        items.append(RawItem(url=href, content=title, metadata={"title": title}))
                        
            seen = set()
            unique_items = []
            for item in items:
                if item.url not in seen:
                    seen.add(item.url)
                    unique_items.append(item)
            logger.info("GSMA 新闻列表页提取到 %d 条", len(unique_items))
            return unique_items
        except Exception:
            logger.exception("GSMA 新闻采集失败")
        return []

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=raw.content,
                author="GSMA",
                extra_metadata={"source": "gsma"},
                category="standard_contribution",
            )
        ]

class TMForumNewsCollector(BaseCollector):
    collector_name = "tmforum_news"
    source_type = SourceType.OFFICIAL
    supported_manufacturers = ["tmforum"]
    needs_js = False

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None, "HttpClient 未初始化"
        items: list[RawItem] = []
        try:
            html = await self.client.get_text("https://inform.tmforum.org/")
            soup = BeautifulSoup(html, "lxml")
            for a in soup.select("a[href]"):
                href = a.get("href")
                if href and href.startswith("https://inform.tmforum.org/") and len(href) > 35:
                    title = a.get_text(strip=True)
                    if len(title) > 10:
                        items.append(RawItem(url=href, content=title, metadata={"title": title}))
                        
            seen = set()
            unique_items = []
            for item in items:
                if item.url not in seen:
                    seen.add(item.url)
                    unique_items.append(item)
            logger.info("TM Forum 新闻列表页提取到 %d 条", len(unique_items))
            return unique_items
        except Exception:
            logger.exception("TM Forum 新闻采集失败")
        return []

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=raw.content,
                author="TM Forum",
                extra_metadata={"source": "tmforum"},
                category="standard_contribution",
            )
        ]
