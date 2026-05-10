"""巨潮资讯 (cninfo.com.cn) 财经公告采集器。

巨潮资讯是证监会指定信息披露网站，用于抓取上市公司财报公告。
API: https://webapi.cninfo.com.cn/api-sys-backend/fulltext/search/full
"""

import json
import logging
import re
from datetime import datetime

from comm_tracker.collectors.base import BaseCollector, ParsedItem, RawItem
from comm_tracker.models.base import SourceType
from comm_tracker.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

# 股票代码 → 厂家编码映射
STOCK_MAPPING: dict[str, str] = {
    "000063": "zte",  # 中兴通讯 A 股
    "0763": "zte",    # 中兴通讯 H 股
}

# 搜索公告的 API
ANNOUNCE_URL = "https://webapi.cninfo.com.cn/api-sys-backend/fulltext/search/full"

# 财报相关公告类别
FINANCE_CATEGORIES = ["年度报告", "半年度报告", "季度报告", "业绩预告", "业绩快报"]


class CninfoCollector(BaseCollector):
    """巨潮资讯财经公告采集器。

    抓取上市公司（目前仅中兴通讯）的财务报告公告。
    """

    collector_name = "cninfo_finance"
    source_type = SourceType.FINANCE
    supported_manufacturers = ["zte"]
    needs_js = False

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None

        # 查找对应的股票代码
        stock_codes = [code for code, mfr in STOCK_MAPPING.items() if mfr == manufacturer]
        if not stock_codes:
            return []

        items: list[RawItem] = []
        for stock_code in stock_codes:
            for category in FINANCE_CATEGORIES:
                try:
                    params = {
                        "scode": stock_code,
                        "keyword": category,
                        "pageNum": 1,
                        "pageSize": 10,
                    }
                    data = await self.client.get_json(ANNOUNCE_URL, params=params)
                    page_items = self._parse_announcements(data, stock_code, since)
                    items.extend(page_items)
                except Exception:
                    logger.exception("巨潮资讯采集失败 (股票: %s, 类别: %s)", stock_code, category)

        logger.info("巨潮资讯采集到 %d 条 (厂家: %s)", len(items), manufacturer)
        return items

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=raw.content,
                published_at=raw.published_at,
                author=raw.metadata.get("company", ""),
                extra_metadata={
                    "source": "cninfo_finance",
                    "announcement_type": raw.metadata.get("announcement_type", ""),
                    "stock_code": raw.metadata.get("stock_code", ""),
                    "report_period": raw.metadata.get("report_period", ""),
                },
                category="market_finance",
            )
        ]

    def _parse_announcements(
        self, data: dict | list, stock_code: str, since: datetime | None = None
    ) -> list[RawItem]:
        """解析公告 API 响应。"""
        items: list[RawItem] = []

        records = data if isinstance(data, list) else data.get("data", data.get("announcements", []))
        if not isinstance(records, list):
            return items

        for record in records:
            title = record.get("title", record.get("announcementTitle", ""))
            if not title:
                continue

            # 过滤非财报类公告
            if not any(cat in title for cat in FINANCE_CATEGORIES):
                continue

            # 提取公告日期
            published_at = None
            date_str = record.get("announcementTime", record.get("pubDate", ""))
            if date_str:
                try:
                    # 时间戳（毫秒）
                    if isinstance(date_str, (int, float)):
                        published_at = datetime.fromtimestamp(date_str / 1000)
                    else:
                        published_at = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
                except (ValueError, OSError):
                    pass

            if since and published_at and published_at < since:
                continue

            # 构建公告 URL
            adj_url = record.get("adjunctUrl", record.get("pdfUrl", ""))
            if adj_url:
                full_url = f"https://static.cninfo.com.cn/{adj_url}"
            else:
                full_url = record.get("url", f"https://www.cninfo.com.cn")

            # 提取报告期
            report_period = ""
            period_match = re.search(r"(\d{4})[年]?(?:半年度|年度|第[一二三四]季度|H1|Q[1-4])", title)
            if period_match:
                report_period = period_match.group(0)

            company = record.get("companyName", record.get("secName", ""))

            items.append(
                RawItem(
                    url=full_url,
                    content=title,
                    metadata={
                        "title": title,
                        "company": company,
                        "stock_code": stock_code,
                        "announcement_type": record.get("announcementType", ""),
                        "report_period": report_period,
                    },
                    published_at=published_at,
                )
            )

        return items
