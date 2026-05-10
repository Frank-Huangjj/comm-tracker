"""C114 通信论坛采集器。

C114 论坛 (bbs.c114.net) 是通信行业技术讨论社区。
帖子列表页 URL: https://bbs.c114.net/forum-{fid}-{page}.html
主要版块 fid: 11(通信基础), 20(移动通信), 38(通信人物/企业)
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

MANUFACTURER_KEYWORDS: dict[str, list[str]] = {
    "huawei": ["华为", "huawei"],
    "zte": ["中兴", "zte"],
    "ericsson": ["爱立信", "ericsson"],
    "nokia": ["诺基亚", "nokia"],
    "samsung": ["三星", "samsung"],
}

# 论坛版块 fid 列表
FORUM_IDS = [11, 20, 38]

MAX_PAGES = 2

BASE_URL = "https://bbs.c114.net"

# C114 使用 GB2312 编码
ENCODING = "gb2312"


class C114BBSCollector(BaseCollector):
    """C114 论坛帖子采集器。"""

    collector_name = "c114_bbs"
    source_type = SourceType.NEWS
    supported_manufacturers = ["huawei", "zte", "ericsson", "nokia", "samsung"]
    needs_js = False

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None
        items: list[RawItem] = []
        seen_urls: set[str] = set()

        keywords = MANUFACTURER_KEYWORDS.get(manufacturer, [])
        if not keywords:
            return items

        for fid in FORUM_IDS:
            for page in range(1, MAX_PAGES + 1):
                try:
                    url = f"{BASE_URL}/forum-{fid}-{page}.html"
                    html = await self.client.get_text(url, encoding=ENCODING)
                    page_items = self._parse_list_page(html, keywords, since)
                    if not page_items:
                        break
                    for item in page_items:
                        if item.url not in seen_urls:
                            seen_urls.add(item.url)
                            items.append(item)
                except Exception:
                    logger.exception("C114 论坛版块 %d 第 %d 页采集失败", fid, page)

        logger.info("C114 论坛采集到 %d 条 (厂家: %s)", len(items), manufacturer)
        return items

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        content = raw.content

        if raw.metadata.get("from_list") and self.client:
            try:
                detail_html = await self.client.get_text(raw.url, encoding=ENCODING)
                content = self._extract_detail(detail_html)
            except Exception:
                logger.exception("C114 论坛帖子详情采集失败: %s", raw.url)
                content = raw.metadata.get("title", "")

        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=content,
                published_at=raw.published_at,
                author=raw.metadata.get("author"),
                extra_metadata={"source": "c114_bbs", "fid": raw.metadata.get("fid", "")},
            )
        ]

    def _parse_list_page(
        self, html: str, keywords: list[str], since: datetime | None = None
    ) -> list[RawItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[RawItem] = []

        # Discuz 论坛帖子链接格式: thread-{tid}-{page}-{lastpage}.html
        for a_tag in soup.select("a[href*='thread-']"):
            href = a_tag.get("href", "")
            title = a_tag.get_text(strip=True)

            if not href or not title or len(title) < 6:
                continue

            # 关键词过滤
            text_lower = title.lower()
            if not any(kw.lower() in text_lower for kw in keywords):
                continue

            full_url = urljoin(BASE_URL, href)

            # 尝试提取日期
            published_at = None
            parent = a_tag.parent
            if parent:
                date_match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", parent.get_text())
                if date_match:
                    try:
                        published_at = datetime(
                            int(date_match.group(1)),
                            int(date_match.group(2)),
                            int(date_match.group(3)),
                        )
                    except ValueError:
                        pass

            if since and published_at and published_at < since:
                continue

            items.append(
                RawItem(
                    url=full_url,
                    content=title,
                    metadata={"from_list": True, "title": title},
                    published_at=published_at,
                )
            )

        return items

    def _extract_detail(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        # Discuz 帖子内容在 .t_f 或 .pcb 中
        content_div = (
            soup.select_one("div.pcb")
            or soup.select_one("td.t_f")
            or soup.select_one("div.postmessage")
        )
        if content_div:
            for tag in content_div.find_all(["script", "style", "iframe"]):
                tag.decompose()
            return str(content_div)
        return html
