"""爱立信官网新闻采集器。

爱立信新闻页 (https://www.ericsson.com/en/press-releases) 需 JS 渲染，有反爬保护。
使用 Playwright 访问，新闻链接格式: /en/press-releases/{year}/{month}/{slug}
日期可从 URL 路径中提取。
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

ERICSSON_BASE = "https://www.ericsson.com"


class EricssonNewsCollector(BaseCollector):
    """爱立信官网新闻采集器。"""

    collector_name = "ericsson_news"
    source_type = SourceType.OFFICIAL
    supported_manufacturers = ["ericsson"]
    needs_js = True

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None
        items: list[RawItem] = []
        try:
            async with self.client.playwright_page() as page:
                await page.goto(
                    f"{ERICSSON_BASE}/en/press-releases",
                    wait_until="load",
                    timeout=90000,
                )
                await page.wait_for_timeout(8000)
                html = await page.content()
                items.extend(self._parse_list_page(html))
        except Exception:
            logger.exception("爱立信新闻列表页采集失败")
        return items

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=raw.content,
                published_at=raw.published_at,
                author="Ericsson",
                extra_metadata={"source": "ericsson_official"},
                category="industry_news",
            )
        ]

    def _parse_list_page(self, html: str) -> list[RawItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[RawItem] = []
        seen: set[str] = set()

        for a_tag in soup.select("a[href*='/press-releases/']"):
            href = a_tag.get("href", "")
            if not href:
                continue

            url = href if href.startswith("http") else urljoin(ERICSSON_BASE, href)
            # 只保留含年月的详情链接
            if not re.search(r"/press-releases/\d{4}/\d{1,2}/", url):
                continue
            # 排除非英文页面
            if "/sv/" in url:
                continue

            # 先提取标题，跳过无文本的图片链接
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            # URL 去重（在确认有标题之后）
            if url in seen:
                continue
            seen.add(url)

            # 从 URL 路径提取日期
            published_at = None
            date_match = re.search(r"/press-releases/(\d{4})/(\d{1,2})/", url)
            if date_match:
                published_at = datetime(int(date_match.group(1)), int(date_match.group(2)), 1)

            items.append(
                RawItem(
                    url=url,
                    content=title,
                    metadata={"from_list": True, "title": title},
                    published_at=published_at,
                )
            )

        logger.info("爱立信新闻列表页提取到 %d 条", len(items))
        return items
