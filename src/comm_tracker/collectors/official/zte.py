"""中兴官网新闻采集器。

中兴新闻页 (https://www.zte.com.cn/china/about/news.html) 为服务端渲染。
DOM: ol > a[href*="/news/202"]，日期在文本末尾（格式 YYYY-MM-DD）。
URL 格式: /content/.../about/news/{YYYYMMDD}{C1|C2}.html
"""

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from comm_tracker.collectors.base import BaseCollector, ParsedItem, RawItem
from comm_tracker.models.base import SourceType
from comm_tracker.utils.http_client import HttpClient
from comm_tracker.utils.text import parse_chinese_date

logger = logging.getLogger(__name__)

ZTE_BASE = "https://www.zte.com.cn"


class ZTENewsCollector(BaseCollector):
    """中兴官网新闻采集器。"""

    collector_name = "zte_news"
    source_type = SourceType.OFFICIAL
    supported_manufacturers = ["zte"]
    needs_js = False

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None
        items: list[RawItem] = []
        try:
            html = await self.client.get_text(f"{ZTE_BASE}/china/about/news.html")
            items.extend(self._parse_list_page(html))
        except Exception:
            logger.exception("中兴新闻列表页采集失败")
        return items

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=raw.content,
                published_at=raw.published_at,
                author="中兴",
                extra_metadata={"source": "zte_official"},
                category="industry_news",
            )
        ]

    def _parse_list_page(self, html: str) -> list[RawItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[RawItem] = []

        for a_tag in soup.select("a[href*='/news/202']"):
            href = a_tag.get("href", "")
            if not href:
                continue

            url = urljoin(ZTE_BASE, href)
            full_text = a_tag.get_text(separator=" ", strip=True)

            # 提取末尾日期 (YYYY-MM-DD)
            published_at = None
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", full_text)
            if date_match:
                published_at = parse_chinese_date(date_match.group(1))

            # 去掉日期得到标题
            title = re.sub(r"\s*\d{4}-\d{2}-\d{2}$", "", full_text).strip()
            if not title or len(title) < 5:
                continue

            items.append(
                RawItem(
                    url=url,
                    content=title,
                    metadata={"from_list": True, "title": title},
                    published_at=published_at,
                )
            )

        logger.info("中兴新闻列表页提取到 %d 条", len(items))
        return items
