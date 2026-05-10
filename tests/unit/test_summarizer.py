"""Summarizer 管线组件单元测试。"""

import pytest

from comm_tracker.collectors.base import ParsedItem
from comm_tracker.llm.client import LLMClient, TokenBudgetExhausted
from comm_tracker.pipeline.summarizer import Summarizer


def _make_item(title: str = "测试标题", content: str = "测试内容", summary: str | None = None) -> ParsedItem:
    return ParsedItem(
        title=title,
        original_url="https://example.com/test",
        content_raw=content,
        content_clean=content,
        summary=summary,
    )


class FakeLLMClient:
    """用于测试的 LLM 客户端 mock。"""

    def __init__(self, responses: list[str] | None = None, *, configured: bool = True):
        self._responses = responses or ["这是测试摘要"]
        self._call_index = 0
        self._configured = configured
        self._daily_used = 0
        self._max_daily_tokens = 100000

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def chat(self, prompt: str, system: str = "", max_tokens: int = 1000, operation: str = "chat") -> str:
        if self._call_index >= len(self._responses):
            raise TokenBudgetExhausted("预算耗尽")
        resp = self._responses[self._call_index]
        self._call_index += 1
        self._daily_used += 100
        return resp

    def get_daily_usage(self):
        return self._daily_used, self._max_daily_tokens


@pytest.mark.asyncio
async def test_summarizer_basic():
    """基本摘要生成。"""
    client = FakeLLMClient(responses=["华为发布新一代5G基站，性能提升30%。"])
    summarizer = Summarizer(client)

    items = [_make_item(content="华为发布了新一代5G基站产品")]
    result = await summarizer.process(items)

    assert len(result) == 1
    assert result[0].summary == "华为发布新一代5G基站，性能提升30%。"


@pytest.mark.asyncio
async def test_summarizer_skip_existing():
    """跳过已有摘要的条目。"""
    client = FakeLLMClient(responses=["新摘要"])
    summarizer = Summarizer(client)

    items = [_make_item(summary="已有摘要")]
    result = await summarizer.process(items)

    assert result[0].summary == "已有摘要"
    # 不应调用 LLM


@pytest.mark.asyncio
async def test_summarizer_empty_content():
    """空内容跳过摘要。"""
    client = FakeLLMClient(responses=["摘要"])
    summarizer = Summarizer(client)

    items = [_make_item(content="")]
    result = await summarizer.process(items)

    assert result[0].summary is None


@pytest.mark.asyncio
async def test_summarizer_budget_exhausted():
    """Token 预算耗尽时优雅降级。"""
    client = FakeLLMClient(responses=["第一条摘要"])
    # 第一次调用返回摘要，第二次抛出预算耗尽
    summarizer = Summarizer(client)

    items = [
        _make_item(title="文章1", content="内容1"),
        _make_item(title="文章2", content="内容2"),
    ]
    result = await summarizer.process(items)

    assert result[0].summary == "第一条摘要"
    assert result[1].summary is None  # 预算耗尽，跳过


@pytest.mark.asyncio
async def test_summarizer_llm_returns_empty():
    """LLM 返回空字符串时摘要为 None。"""
    client = FakeLLMClient(responses=[""])
    summarizer = Summarizer(client)

    items = [_make_item(content="测试内容")]
    result = await summarizer.process(items)

    assert result[0].summary is None


@pytest.mark.asyncio
async def test_summarizer_not_configured():
    """LLM 未配置时跳过摘要生成。"""
    client = FakeLLMClient(configured=False)
    summarizer = Summarizer(client)

    items = [_make_item()]
    result = await summarizer.process(items)

    assert result[0].summary is None


@pytest.mark.asyncio
async def test_summarizer_multiple_items():
    """批量处理多个条目。"""
    client = FakeLLMClient(responses=["摘要1", "摘要2", "摘要3"])
    summarizer = Summarizer(client)

    items = [
        _make_item(title="文章1", content="内容1"),
        _make_item(title="文章2", content="内容2"),
        _make_item(title="文章3", content="内容3"),
    ]
    result = await summarizer.process(items)

    assert result[0].summary == "摘要1"
    assert result[1].summary == "摘要2"
    assert result[2].summary == "摘要3"
