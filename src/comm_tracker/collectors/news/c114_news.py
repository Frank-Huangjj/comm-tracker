"""C114 通信行业新闻网采集器。

C114 (www.c114.com.cn) 是国内主要通信行业媒体门户。
新闻列表页 URL: https://www.c114.com.cn/news/{page}.html
文章详情页 DOM: div.article 内容区域。
注意：C114 网站使用 GB2312 编码。
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

# 厂家关键词 → 厂家编码映射（用于识别文章关联厂家）
MANUFACTURER_KEYWORDS: dict[str, list[str]] = {
    "huawei": ["华为", "huawei"],
    "zte": ["中兴", "zte"],
    "ericsson": ["爱立信", "ericsson"],
    "nokia": ["诺基亚", "nokia"],
    "samsung": ["三星", "samsung"],
}

# 最多抓取页数
MAX_PAGES = 3

# 列表页 URL 模板
LIST_URL = "https://www.c114.com.cn/news"

# C114 使用 GB2312 编码
ENCODING = "gb2312"


class C114NewsCollector(BaseCollector):
    """C114 通信行业新闻网采集器。

    按厂家关键词过滤相关新闻，支持增量采集。
    """

    collector_name = "c114_news"
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

        for page in range(1, MAX_PAGES + 1):
            try:
                url = f"{LIST_URL}/{page}.html" if page > 1 else f"{LIST_URL}/"
                html = await self.client.get_text(url, encoding=ENCODING)
                page_items = self._parse_list_page(html, keywords, since)
                if not page_items:
                    break
                for item in page_items:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        items.append(item)
            except Exception:
                logger.exception("C114 列表页 %d 采集失败", page)
                break

        logger.info("C114 采集到 %d 条原始条目 (厂家: %s)", len(items), manufacturer)
        return items

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        content = raw.content

        # 如果是从列表页来的条目，需要抓取详情页获取完整内容
        if raw.metadata.get("from_list") and self.client:
            try:
                detail_html = await self.client.get_text(raw.url, encoding=ENCODING)
                content = self._extract_detail(detail_html)
            except Exception:
                logger.exception("C114 详情页采集失败: %s", raw.url)
                content = raw.metadata.get("title", "")

        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=content,
                published_at=raw.published_at,
                author=raw.metadata.get("author"),
                extra_metadata={"source": "c114_news"},
            )
        ]

    def _parse_list_page(
        self, html: str, keywords: list[str], since: datetime | None = None
    ) -> list[RawItem]:
        """解析列表页，按厂家关键词过滤。"""
        soup = BeautifulSoup(html, "lxml")
        items: list[RawItem] = []

        for a_tag in soup.select("a[href*='/news/']"):
            href = a_tag.get("href", "")
            title = a_tag.get_text(strip=True)

            # 过滤无效链接
            if not href or not title or len(title) < 8:
                continue
            # 过滤非文章链接（导航、分类等）——文章链接含 /数字/a数字.html
            if not re.search(r"/a\d+\.html", href):
                continue

            # 关键词过滤：标题必须包含厂家关键词
            text_lower = title.lower()
            if not any(kw.lower() in text_lower for kw in keywords):
                continue

            # 构建完整 URL
            full_url = urljoin("https://www.c114.com.cn", href)

            # 尝试提取日期
            published_at = self._extract_date(a_tag, soup)

            # 检查增量
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

        logger.debug("C114 列表页提取到 %d 条", len(items))
        return items

    def _extract_detail(self, html: str) -> str:
        """从详情页提取正文内容。"""
        soup = BeautifulSoup(html, "lxml")

        # C114 文章正文通常在 .article 或 #article_content 中
        article_div = (
            soup.select_one("div.article")
            or soup.select_one("div#article_content")
            or soup.select_one("div.content")
        )

        if article_div:
            # 移除广告和无关元素
            for tag in article_div.find_all(["script", "style", "iframe"]):
                tag.decompose()
            return str(article_div)

        return html

    def _extract_date(self, a_tag, soup) -> datetime | None:
        """尝试从列表页提取发布日期。"""
        # 查找相邻的日期文本
        parent = a_tag.parent
        if parent:
            text = parent.get_text()
            # 匹配常见日期格式: 2024-01-15 或 2024/01/15
            match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
            if match:
                try:
                    return datetime(
                        int(match.group(1)),
                        int(match.group(2)),
                        int(match.group(3)),
                    )
                except ValueError:
                    pass
        return None
