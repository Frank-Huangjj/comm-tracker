"""诺基亚官网新闻采集器。

诺基亚新闻页 (https://www.nokia.com/about-us/newsroom/press-and-media/) 为服务端渲染。
DOM: div.grid-item > a[href*="nokia.com/newsroom/..."]，标题在链接文本中。
"""

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from comm_tracker.collectors.base import BaseCollector, ParsedItem, RawItem
from comm_tracker.models.base import SourceType
from comm_tracker.utils.http_client import HttpClient

logger = logging.getLogger(__name__)


class NokiaNewsCollector(BaseCollector):
    """诺基亚官网新闻采集器。"""

    collector_name = "nokia_news"
    source_type = SourceType.OFFICIAL
    supported_manufacturers = ["nokia"]
    needs_js = False

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None
        items: list[RawItem] = []
        try:
            html = await self.client.get_text(
                "https://www.nokia.com/about-us/newsroom/press-and-media/"
            )
            items.extend(self._parse_list_page(html))
        except Exception:
            logger.exception("诺基亚新闻列表页采集失败")
        return items

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=raw.content,
                published_at=raw.published_at,
                author="Nokia",
                extra_metadata={"source": "nokia_official"},
                category="industry_news",
            )
        ]

    def _parse_list_page(self, html: str) -> list[RawItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[RawItem] = []
        seen: set[str] = set()

        for a_tag in soup.select("div.grid-item a[href*='nokia.com/newsroom/']"):
            href = a_tag.get("href", "")
            if not href or len(href) < 40:
                continue
            if href in seen:
                continue
            seen.add(href)

            title = a_tag.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            items.append(
                RawItem(
                    url=href,
                    content=title,
                    metadata={"from_list": True, "title": title},
                    published_at=None,  # 列表页无日期，后续可从详情页提取
                )
            )

        logger.info("诺基亚新闻列表页提取到 %d 条", len(items))
        return items
