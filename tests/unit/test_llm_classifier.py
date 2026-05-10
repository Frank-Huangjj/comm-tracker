"""LLM 增强分类器单元测试。"""

import json

import pytest

from comm_tracker.collectors.base import ParsedItem
from comm_tracker.pipeline.classifier import KeywordClassifier, LLMClassifier


def _make_item(title: str = "测试标题", content: str = "测试内容") -> ParsedItem:
    return ParsedItem(
        title=title,
        original_url="https://example.com/test",
        content_raw=content,
        content_clean=content,
    )


class FakeLLMClient:
    """测试用 LLM 客户端 mock。"""

    def __init__(self, responses: list[dict] | None = None, *, configured: bool = True):
        self._responses = responses or [{"category": "product_release"}]
        self._call_index = 0
        self._configured = configured
        self._daily_used = 0
        self._max_daily_tokens = 100000

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def chat_json(self, prompt: str, system: str = "", max_tokens: int = 1000, operation: str = "chat") -> dict:
        if self._call_index >= len(self._responses):
            raise Exception("预算耗尽")
        resp = self._responses[self._call_index]
        self._call_index += 1
        self._daily_used += 50
        return resp

    def get_daily_usage(self):
        return self._daily_used, self._max_daily_tokens


# --- KeywordClassifier 测试 ---

def test_keyword_classifier_product_release():
    items = [_make_item(title="华为发布新一代5G基站")]
    result = KeywordClassifier().process(items)
    assert result[0].category == "product_release"


def test_keyword_classifier_tech_dynamic():
    items = [_make_item(title="3GPP RAN 会议新进展")]
    result = KeywordClassifier().process(items)
    assert result[0].category == "tech_dynamic"


def test_keyword_classifier_market_finance():
    items = [_make_item(title="中兴年报显示营收增长")]
    result = KeywordClassifier().process(items)
    assert result[0].category == "market_finance"


def test_keyword_classifier_default_industry_news():
    items = [_make_item(title="通信行业年度总结")]
    result = KeywordClassifier().process(items)
    assert result[0].category == "industry_news"


# --- LLMClassifier 测试 ---

@pytest.mark.asyncio
async def test_llm_classifier_keyword_hits_no_llm_call():
    """关键词命中时不调用 LLM。"""
    client = FakeLLMClient(responses=[{"category": "should_not_be_called"}])
    classifier = LLMClassifier(client)

    items = [_make_item(title="华为发布新品5G设备")]
    result = await classifier.process(items)

    assert result[0].category == "product_release"
    # LLM 不应被调用（call_index 保持 0）


@pytest.mark.asyncio
async def test_llm_classifier_fallback_to_llm():
    """关键词未命中时调用 LLM。"""
    client = FakeLLMClient(responses=[{"category": "tech_dynamic"}])
    classifier = LLMClassifier(client)

    items = [_make_item(title="光传输网络技术取得突破性进展")]
    result = await classifier.process(items)

    assert result[0].category == "tech_dynamic"


@pytest.mark.asyncio
async def test_llm_classifier_invalid_category_falls_back():
    """LLM 返回无效分类时退回默认。"""
    client = FakeLLMClient(responses=[{"category": "invalid_category"}])
    classifier = LLMClassifier(client)

    items = [_make_item(title="行业新闻速递")]
    result = await classifier.process(items)

    assert result[0].category == "industry_news"


@pytest.mark.asyncio
async def test_llm_classifier_not_configured():
    """LLM 未配置时退回纯关键词分类。"""
    client = FakeLLMClient(configured=False)
    classifier = LLMClassifier(client)

    items = [_make_item(title="通信行业周报")]
    result = await classifier.process(items)

    assert result[0].category == "industry_news"


@pytest.mark.asyncio
async def test_llm_classifier_mixed_items():
    """混合条目：部分关键词命中，部分需要 LLM。"""
    client = FakeLLMClient(responses=[
        {"category": "tech_dynamic"},
        {"category": "market_finance"},
    ])
    classifier = LLMClassifier(client)

    items = [
        _make_item(title="华为发布新款基站"),           # 关键词命中: product_release
        _make_item(title="光子芯片技术取得重大突破"),    # LLM: tech_dynamic
        _make_item(title="行业季度分析报告"),            # LLM: market_finance
    ]
    result = await classifier.process(items)

    assert result[0].category == "product_release"  # 关键词
    assert result[1].category == "tech_dynamic"      # LLM
    assert result[2].category == "market_finance"     # LLM


@pytest.mark.asyncio
async def test_llm_classifier_budget_exhausted():
    """Token 预算耗尽时后续条目使用默认分类。"""
    # 只有一条 LLM 响应，第二次会抛异常
    client = FakeLLMClient(responses=[{"category": "product_release"}])
    # 修改使第二次调用抛出 TokenBudgetExhausted
    from comm_tracker.llm.client import TokenBudgetExhausted

    original_chat_json = client.chat_json
    call_count = 0

    async def mock_chat_json(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise TokenBudgetExhausted("预算耗尽")
        return await original_chat_json(*args, **kwargs)

    client.chat_json = mock_chat_json
    classifier = LLMClassifier(client)

    items = [
        _make_item(title="未知类型文章A"),
        _make_item(title="未知类型文章B"),
    ]
    result = await classifier.process(items)

    assert result[0].category == "product_release"   # 第一条 LLM 成功
    assert result[1].category == "industry_news"      # 第二条预算耗尽，退回默认
