"""文章分类器——关键词规则 + LLM 增强。"""

import json
import logging
import re

from comm_tracker.collectors.base import ParsedItem
from comm_tracker.llm.client import LLMClient, TokenBudgetExhausted

logger = logging.getLogger(__name__)

# 分类关键词规则：分类 → 关键词列表
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("product_release", ["发布", "新品", "推出", "上市", "首发", "发布新一代", "推出全新", "launch"]),
    ("tech_dynamic", ["专利", "标准", "3GPP", "5G-A", "6G", "白皮书", "技术突破", "创新", "研发", "频谱", "MIMO", "光网络"]),
    ("market_finance", ["营收", "净利润", "年报", "财报", "季度报", "合同", "签约", "中标", "市场份额", "投标"]),
    ("patent_filing", ["专利申请", "发明专利", "知识产权", "IPC分类", "patent"]),
    ("standard_contribution", ["3GPP", "标准化", "标准提案", "TSG", "RAN", "SA", "CT", "Release"]),
]

# 有效分类集合
VALID_CATEGORIES = {
    "product_release", "tech_dynamic", "market_finance",
    "industry_news", "patent_filing", "standard_contribution",
}

# LLM 分类 prompt
LLM_CLASSIFY_SYSTEM = """你是通信行业资讯分类专家。请将以下文章归入最匹配的一个分类。

可选分类：
- product_release: 产品发布、新品上市、设备推出
- tech_dynamic: 技术突破、研发进展、标准与专利动态
- market_finance: 营收财报、市场合作、合同中标
- patent_filing: 专利申请、知识产权
- standard_contribution: 标准化提案、3GPP 贡献
- industry_news: 行业综合新闻（不属于以上任一类别时使用）

只输出 JSON: {"category": "分类名"}"""

LLM_CLASSIFY_USER = """文章标题：{title}

文章内容（摘要）：
{content}

请分类："""

# LLM 分类的最大内容长度
MAX_CLASSIFY_CONTENT = 1000


class KeywordClassifier:
    """基于关键词规则的文章分类器。

    按优先级逐一匹配关键词，首个命中分类生效。
    若无命中则返回 None，由上层决定后续处理。
    """

    def classify(self, item: ParsedItem) -> str | None:
        """返回分类字符串，无命中返回 None。"""
        text = f"{item.title} {item.content_clean or item.content_raw}".lower()

        for category, keywords in CATEGORY_RULES:
            for kw in keywords:
                if re.search(kw, text, re.IGNORECASE):
                    return category

        return None

    def process(self, items: list[ParsedItem]) -> list[ParsedItem]:
        """批量分类（纯关键词，同步）。"""
        stats: dict[str, int] = {}
        for item in items:
            item.category = self.classify(item) or "industry_news"
            stats[item.category] = stats.get(item.category, 0) + 1

        if stats:
            logger.info("关键词分类结果: %s", dict(stats))
        return items


class LLMClassifier:
    """LLM 增强分类器。

    策略：关键词优先，对关键词默认归入 industry_news 的条目
    调用 LLM 进行二次判断，token 预算不足时退回关键词结果。
    """

    def __init__(self, client: LLMClient) -> None:
        self._client = client
        self._keyword = KeywordClassifier()

    async def _classify_with_llm(self, item: ParsedItem) -> str:
        """调用 LLM 对单篇文章分类。"""
        content = (item.content_clean or item.content_raw)[:MAX_CLASSIFY_CONTENT]
        prompt = LLM_CLASSIFY_USER.format(title=item.title, content=content)

        result = await self._client.chat_json(
            prompt=prompt,
            system=LLM_CLASSIFY_SYSTEM,
            max_tokens=100,
            operation="classify",
        )
        category = result.get("category", "")
        if category in VALID_CATEGORIES:
            return category

        logger.warning("LLM 返回无效分类 '%s'，使用默认", category)
        return "industry_news"

    async def process(self, items: list[ParsedItem]) -> list[ParsedItem]:
        """批量分类：关键词优先，LLM 兜底。"""
        if not self._client.is_configured:
            logger.warning("LLM 未配置，仅使用关键词分类")
            return self._keyword.process(items)

        # 第一轮：关键词分类
        kw_stats: dict[str, int] = {}
        llm_candidates: list[tuple[int, ParsedItem]] = []  # (index, item)

        for i, item in enumerate(items):
            kw_result = self._keyword.classify(item)
            if kw_result:
                item.category = kw_result
                kw_stats[kw_result] = kw_stats.get(kw_result, 0) + 1
            else:
                # 关键词未命中，标记为 LLM 候选
                llm_candidates.append((i, item))

        logger.info(
            "关键词分类: %d 条命中, %d 条待 LLM 判断",
            len(items) - len(llm_candidates),
            len(llm_candidates),
        )

        # 第二轮：LLM 分类
        llm_stats: dict[str, int] = {}
        budget_exhausted = False

        for idx, item in llm_candidates:
            if budget_exhausted:
                item.category = "industry_news"
                llm_stats["industry_news"] = llm_stats.get("industry_news", 0) + 1
                continue

            try:
                item.category = await self._classify_with_llm(item)
                llm_stats[item.category] = llm_stats.get(item.category, 0) + 1
            except TokenBudgetExhausted:
                logger.warning("Token 预算耗尽，剩余条目使用默认分类")
                budget_exhausted = True
                item.category = "industry_news"
                llm_stats["industry_news"] = llm_stats.get("industry_news", 0) + 1
            except Exception:
                logger.exception("LLM 分类失败: %s", item.original_url)
                item.category = "industry_news"
                llm_stats["industry_news"] = llm_stats.get("industry_news", 0) + 1

        if llm_stats:
            logger.info("LLM 分类结果: %s", dict(llm_stats))

        return items
