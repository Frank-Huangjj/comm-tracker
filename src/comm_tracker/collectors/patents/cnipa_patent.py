"""国家知识产权局 (CNIPA) 专利采集器。

通过 CNIPA 专利查询接口搜索通信厂家专利。
查询 URL: https://pss-system.cponline.cnipa.gov.cn/conventionalSearch
"""

import logging
import re
from datetime import datetime

from comm_tracker.collectors.base import BaseCollector, ParsedItem, RawItem
from comm_tracker.models.base import SourceType
from comm_tracker.utils.http_client import HttpClient

logger = logging.getLogger(__name__)

# 申请人名称映射
APPLICANT_NAMES: dict[str, list[str]] = {
    "huawei": ["华为技术有限公司", "华为终端有限公司"],
    "zte": ["中兴通讯股份有限公司"],
    "ericsson": ["爱立信", "ERICSSON", " Telefonaktiebolaget LM Ericsson"],
    "nokia": ["诺基亚", "NOKIA", "Nokia Technologies Oy"],
    "samsung": ["三星电子", "SAMSUNG", "Samsung Electronics"],
}

# 专利搜索 API
SEARCH_URL = "https://pss-system.cponline.cnipa.gov.cn/conventionalSearch"


class CNIPACollector(BaseCollector):
    """CNIPA 专利采集器。

    通过国家知识产权局查询接口搜索通信厂家最新专利申请。
    注意：CNIPA 网站有较严格的反爬策略，实际使用时可能需要调整请求策略。
    """

    collector_name = "cnipa_patent"
    source_type = SourceType.PATENT
    supported_manufacturers = ["huawei", "zte", "ericsson", "nokia", "samsung"]
    needs_js = False

    def __init__(self, client: HttpClient | None = None):
        self.client = client

    async def collect(self, manufacturer: str, since: datetime | None = None) -> list[RawItem]:
        assert self.client is not None
        items: list[RawItem] = []
        applicants = APPLICANT_NAMES.get(manufacturer, [])
        if not applicants:
            return items

        for applicant in applicants:
            try:
                # 尝试通过 API 查询
                params = {
                    "searchCondition": applicant,
                    "searchType": "applicant",
                }
                data = await self.client.get_json(SEARCH_URL, params=params)
                page_items = self._parse_api_response(data, applicant, since)
                items.extend(page_items)
            except Exception:
                # API 可能不可用，尝试页面解析
                logger.debug("CNIPA API 查询失败，尝试页面解析")
                try:
                    html = await self.client.get_text(SEARCH_URL)
                    page_items = self._parse_html_page(html, applicant, since)
                    items.extend(page_items)
                except Exception:
                    logger.exception("CNIPA 采集失败 (申请人: %s)", applicant)

        logger.info("CNIPA 采集到 %d 条专利 (厂家: %s)", len(items), manufacturer)
        return items

    async def parse(self, raw: RawItem) -> list[ParsedItem]:
        return [
            ParsedItem(
                title=raw.metadata.get("title", ""),
                original_url=raw.url,
                content_raw=raw.content,
                published_at=raw.published_at,
                author=raw.metadata.get("applicant", ""),
                extra_metadata={
                    "source": "cnipa_patent",
                    "patent_number": raw.metadata.get("patent_number", ""),
                    "patent_type": raw.metadata.get("patent_type", ""),
                    "ipc": raw.metadata.get("ipc", ""),
                },
                category="patent_filing",
            )
        ]

    def _parse_api_response(
        self, data: dict | list, applicant: str, since: datetime | None = None
    ) -> list[RawItem]:
        """解析 JSON API 响应。"""
        items: list[RawItem] = []

        records = data if isinstance(data, list) else data.get("data", data.get("records", []))
        if not isinstance(records, list):
            return items

        for record in records:
            patent_number = record.get("patentNumber", record.get("applicationNumber", ""))
            title = record.get("title", record.get("inventionTitle", ""))
            if not patent_number or not title:
                continue

            # 日期
            published_at = None
            for date_field in ["filingDate", "applicationDate", "publishDate", "publicationDate"]:
                date_str = record.get(date_field, "")
                if date_str:
                    try:
                        published_at = datetime.strptime(date_str[:10], "%Y-%m-%d")
                        break
                    except ValueError:
                        pass

            if since and published_at and published_at < since:
                continue

            abstract = record.get("abstract", record.get("summary", ""))
            ipc = record.get("ipcClassification", record.get("ipc", ""))

            items.append(
                RawItem(
                    url=f"https://pss-system.cponline.cnipa.gov.cn/detail?patentNumber={patent_number}",
                    content=abstract or title,
                    metadata={
                        "title": title,
                        "patent_number": patent_number,
                        "applicant": applicant,
                        "patent_type": record.get("type", record.get("patentType", "")),
                        "ipc": ipc,
                    },
                    published_at=published_at,
                )
            )

        return items

    def _parse_html_page(
        self, html: str, applicant: str, since: datetime | None = None
    ) -> list[RawItem]:
        """解析 HTML 页面作为备用方案。"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        items: list[RawItem] = []

        for row in soup.select("tr.patent-item, div.result-item"):
            title_tag = row.select_one("a.patent-title, td.title a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")
            if not title:
                continue

            # 提取专利号
            patent_number = ""
            number_match = re.search(r"CN\d{13}[A-Z]?", title + href)
            if number_match:
                patent_number = number_match.group()

            # 提取日期
            published_at = None
            text = row.get_text()
            date_match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
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
                    url=href or "https://pss-system.cponline.cnipa.gov.cn",
                    content=text,
                    metadata={
                        "title": title,
                        "patent_number": patent_number,
                        "applicant": applicant,
                    },
                    published_at=published_at,
                )
            )

        return items
