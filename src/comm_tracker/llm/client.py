"""LLM 客户端封装——基于 OpenAI SDK 对接 DeepSeek。"""

import json
import logging
from datetime import date, datetime

from openai import AsyncOpenAI
from sqlmodel import Session, select

from comm_tracker.config import get_llm_config

logger = logging.getLogger(__name__)


class TokenBudgetExhausted(Exception):
    """Token 日预算耗尽。"""


class LLMClient:
    """异步 LLM 客户端，内置 token 用量追踪与持久化。"""

    def __init__(self, session: Session | None = None) -> None:
        config = get_llm_config()
        self._api_key = config["api_key"]
        self._base_url = config["base_url"]
        self._model = config["model"]
        self._max_daily_tokens = config["max_daily_tokens"]
        self._client: AsyncOpenAI | None = None
        self._daily_used: int = 0
        self._daily_date: date | None = None
        self._session = session

    @property
    def is_configured(self) -> bool:
        """API Key 是否已配置。"""
        return bool(self._api_key)

    async def __aenter__(self) -> "LLMClient":
        if self.is_configured:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    def _check_budget(self) -> None:
        today = date.today()
        if self._daily_date != today:
            self._daily_used = self._load_daily_usage(today)
            self._daily_date = today
        if self._daily_used >= self._max_daily_tokens:
            raise TokenBudgetExhausted(
                f"今日 token 用量已达 {self._daily_used}/{self._max_daily_tokens}"
            )

    def _load_daily_usage(self, target_date: date) -> int:
        """从数据库加载指定日期的累计 token 用量。"""
        if not self._session:
            return 0
        try:
            from comm_tracker.models.token_usage import TokenUsage
            rows = self._session.exec(
                select(TokenUsage).where(TokenUsage.usage_date == target_date)
            ).all()
            return sum(r.total_tokens for r in rows)
        except Exception:
            logger.debug("无法加载历史 token 用量，从 0 开始")
            return 0

    def _record_usage(self, prompt_tokens: int, completion_tokens: int, operation: str = "chat") -> None:
        """将 token 用量持久化到数据库。"""
        if not self._session:
            return
        try:
            from comm_tracker.models.token_usage import TokenUsage
            record = TokenUsage(
                usage_date=date.today(),
                model=self._model,
                operation=operation,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
            self._session.add(record)
            self._session.commit()
        except Exception:
            logger.debug("Token 用量持久化失败")

    async def chat(self, prompt: str, system: str = "", max_tokens: int = 1000, operation: str = "chat") -> str:
        """发送聊天请求并返回回复文本。"""
        if not self._client:
            raise RuntimeError("LLM 客户端未初始化或 API Key 未配置")

        self._check_budget()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )

        usage = response.usage
        if usage:
            self._daily_used += usage.total_tokens
            self._record_usage(usage.prompt_tokens, usage.completion_tokens, operation)
            logger.debug(
                "LLM 调用: prompt=%d, completion=%d, daily_total=%d/%d",
                usage.prompt_tokens,
                usage.completion_tokens,
                self._daily_used,
                self._max_daily_tokens,
            )

        content = response.choices[0].message.content
        return content.strip() if content else ""

    async def chat_json(self, prompt: str, system: str = "", max_tokens: int = 1000, operation: str = "chat") -> dict:
        """发送聊天请求并解析 JSON 响应。"""
        raw = await self.chat(prompt, system=system, max_tokens=max_tokens, operation=operation)
        # 尝试提取 JSON 块（可能被 ```json ... ``` 包裹）
        text = raw.strip()
        if text.startswith("```"):
            first_nl = text.index("\n") if "\n" in text else len(text)
            last_tick = text.rfind("```")
            text = text[first_nl + 1 : last_tick].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM 返回非 JSON 格式: %s", raw[:200])
            return {}

    def get_daily_usage(self) -> tuple[int, int]:
        """返回 (已用 token, 每日限额)。"""
        return self._daily_used, self._max_daily_tokens

    def is_within_budget(self) -> bool:
        """是否仍在 token 预算内。"""
        self._check_budget()
        return True
