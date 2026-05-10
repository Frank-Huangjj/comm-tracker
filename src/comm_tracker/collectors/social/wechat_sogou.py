"""微信搜狗公众号文章采集器。

通过搜狗微信搜索 (weixin.sogou.com) 搜索通信厂家相关公众号文章。
搜索 URL: https://weixin.sogou.com/weixin?type=2&query={keyword}
"""

import logging
import re
from datetime import datetime
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from comm_tracker.collectors.base import BaseCollector, ParsedItem, RawItem
from comm_tracker.models.base import SourceType
from comm_tracker.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

MANUFACTURER_KEYWORDS: dict[str, list[str]] = {
    "huawei": ["华为", "huawei 通信"],
    "zte": ["中兴通讯", "zte 通信"],
    "ericsson": ["爱立信", "ericsson 通信"],
    "nokia": ["诺基亚", "nokia 通信"],
    "samsung": ["三星网络", "samsung 通信"],
}

BASE_URL = "https://weixin.sogou.com"


class WeChatSogouCollector(BaseCollector):
    """微信搜狗公众号文章采集器。"""

    collector_name = "wechat_sogou"
    source_type = SourceType.SOCIAL
    supported_manufacturers = ["huawei", "zte", "ericsson", "nokia", "samsung"]
    needs_js = False

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None
        items: list[RawItem] = []
        keywords = MANUFACTURER_KEYWORDS.get(manufacturer, [])
        if not keywords:
            return items

        for keyword in keywords[:2]:  # 最多 2 个关键词
            try:
                url = f"{BASE_URL}/weixin?type=2&query={quote(keyword)}&page=1"
                html = await self.client.get_text(url)
                page_items = self._parse_search_page(html, keyword, since)
                items.extend(page_items)
            except Exception:
                logger.exception("微信搜狗搜索 '%s' 采集失败", keyword)

        logger.info("微信搜狗采集到 %d 条 (厂家: %s)", len(items), manufacturer)
        return items

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        content = raw.content

        if raw.metadata.get("from_search") and self.client:
            try:
                detail_html = await self.client.get_text(raw.url)
                content = self._extract_detail(detail_html)
            except Exception:
                logger.exception("微信文章详情采集失败: %s", raw.url)
                content = raw.metadata.get("title", "")

        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=content,
                published_at=raw.published_at,
                author=raw.metadata.get("author"),
                extra_metadata={
                    "source": "wechat_sogou",
                    "account": raw.metadata.get("account", ""),
                },
            )
        ]

    def _parse_search_page(
        self, html: str, keyword: str, since: datetime | None = None
    ) -> list[RawItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[RawItem] = []

        # 搜狗微信搜索结果条目
        for result in soup.select("div.news-box li, div.txt-box"):
            a_tag = result.select_one("h3 a, a[href*='mp.weixin.qq.com']")
            if not a_tag:
                continue

            title = a_tag.get_text(strip=True)
            href = a_tag.get("href", "")
            if not title or not href:
                continue

            # 确保是微信文章链接
            full_url = urljoin(BASE_URL, href)

            # 提取公众号名称
            account = ""
            account_tag = result.select_one("a.account, .s-p .s-p-name")
            if account_tag:
                account = account_tag.get_text(strip=True)

            # 提取日期
            published_at = None
            date_span = result.select_one("span.s2, .s-p span")
            if date_span:
                date_match = re.search(
                    r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", date_span.get_text()
                )
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
                    metadata={
                        "from_search": True,
                        "title": title,
                        "account": account,
                        "search_keyword": keyword,
                    },
                    published_at=published_at,
                )
            )

        return items

    def _extract_detail(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        # 微信公众号文章正文在 js_content 中
        content_div = (
            soup.select_one("div#js_content")
            or soup.select_one("div.rich_media_content")
            or soup.select_one("div.content")
        )
        if content_div:
            for tag in content_div.find_all(["script", "style", "iframe"]):
                tag.decompose()
            return str(content_div)
        return html
