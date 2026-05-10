"""华为官网新闻采集器。

华为新闻中心 (https://www.huawei.com/cn/news) 新闻内容由 JS 动态加载，
需用 Playwright 渲染后提取。
DOM 结构: a.c-box[href*="/cn/news/"] 卡片，日期嵌入文本中。
URL 格式: /cn/news/{year}/{month}/{slug}
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

HUAWEI_BASE = "https://www.huawei.com"


class HuaweiNewsCollector(BaseCollector):
    """华为官网新闻采集器。"""

    collector_name = "huawei_news"
    source_type = SourceType.OFFICIAL
    supported_manufacturers = ["huawei"]
    needs_js = True

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        """用 Playwright 渲染华为新闻列表页。"""
        assert self.client is not None, "HttpClient 未初始化"

        items: list[RawItem] = []
        try:
            async with self.client.playwright_page() as page:
                await page.goto(
                    f"{HUAWEI_BASE}/cn/news",
                    wait_until="domcontentloaded",
                    timeout=90000,
                )
                # 等待新闻卡片出现
                await page.wait_for_selector("a.c-box[href*='/cn/news/']", timeout=30000)
                await page.wait_for_timeout(2000)

                html = await page.content()
                items.extend(self._parse_list_page(html))
        except Exception:
            logger.exception("华为新闻列表页采集失败")

        return items

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        """解析新闻条目。"""
        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=raw.content,
                content_clean="",
                published_at=raw.published_at,
                author="华为",
                extra_metadata={"source": "huawei_official"},
                category="industry_news",
            )
        ]

    def _parse_list_page(self, html: str) -> list[RawItem]:
        """从列表页提取新闻条目。

        DOM 结构:
          <a href="//www.huawei.com/cn/news/2026/4/solar-jazzworld" class="c-box">
            ...图片...
            ...标题文本...
            2026年04月03日
          </a>
        """
        soup = BeautifulSoup(html, "lxml")
        items: list[RawItem] = []

        for card in soup.select("a.c-box[href*='/cn/news/']"):
            href = card.get("href", "")
            if not href:
                continue

            url = href if href.startswith("http") else urljoin(HUAWEI_BASE, href)
            if not re.search(r"/cn/news/\d{4}/\d{1,2}/", url):
                continue

            full_text = card.get_text(separator=" ", strip=True)

            # 提取日期
            published_at = None
            date_match = re.search(r"(\d{4}年\d{1,2}月\d{1,2}日)", full_text)
            if date_match:
                published_at = parse_chinese_date(date_match.group(0))

            # 去掉日期得到标题
            title = re.sub(r"\d{4}年\d{1,2}月\d{1,2}日", "", full_text).strip()
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

        # 去重
        seen: set[str] = set()
        unique: list[RawItem] = []
        for item in items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)

        logger.info("华为新闻列表页提取到 %d 条", len(unique))
        return unique
