"""中国移动官网新闻采集器。"""

import logging
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from comm_tracker.collectors.base import BaseCollector, ParsedItem, RawItem
from comm_tracker.models.base import SourceType
from comm_tracker.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

BASE_URL = "https://www.chinamobile.com"

class ChinaMobileNewsCollector(BaseCollector):
    """中国移动官网新闻采集器。"""

    collector_name = "cmcc_news"
    source_type = SourceType.OFFICIAL
    supported_manufacturers = ["china_mobile"]
    needs_js = False

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None, "HttpClient 未初始化"
        items: list[RawItem] = []
        try:
            html = await self.client.get_text(f"{BASE_URL}/cn/about/news/")
            soup = BeautifulSoup(html, "lxml")
            for a in soup.select("a[href]"):
                href = a.get("href")
                # 简单启发式：包含新闻且以 html 结尾
                if href and "news" in href and href.endswith(".html"):
                    title = a.get_text(strip=True)
                    if len(title) > 5:
                        url = urljoin(BASE_URL, href)
                        items.append(RawItem(url=url, content=title, metadata={"title": title}))
                        
            # 去重
            seen = set()
            unique_items = []
            for item in items:
                if item.url not in seen:
                    seen.add(item.url)
                    unique_items.append(item)
            logger.info("中国移动新闻列表页提取到 %d 条", len(unique_items))
            return unique_items
        except Exception:
            logger.exception("中国移动新闻采集失败")
        return []

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=raw.content,
                author="中国移动",
                extra_metadata={"source": "cmcc_official"},
                category="industry_news",
            )
        ]
