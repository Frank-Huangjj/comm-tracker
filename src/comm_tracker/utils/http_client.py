"""统一 HTTP 客户端——封装 httpx 和 Playwright。"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from comm_tracker.collectors.middleware import RateLimiter, RetryHandler, UserAgentRotator

logger = logging.getLogger(__name__)


class HttpClient:
    """统一的 HTTP 客户端，自动在 httpx 和 Playwright 之间路由。

    用法:
        async with HttpClient() as client:
            html = await client.get_text("https://example.com")
            # 需要 JS 渲染时：
            html = await client.get_page("https://spa-site.com")
    """

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        ua_rotator: UserAgentRotator | None = None,
        retry_handler: RetryHandler | None = None,
    ):
        self.rate_limiter = rate_limiter or RateLimiter()
        self.ua_rotator = ua_rotator or UserAgentRotator()
        self.retry_handler = retry_handler or RetryHandler()
        self._httpx: httpx.AsyncClient | None = None
        self._pw = None
        self._browser: Browser | None = None
        self._contexts: list[BrowserContext] = []

    async def __aenter__(self) -> "HttpClient":
        self._httpx = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
            headers=self.ua_rotator.get_headers(),
            http2=True,
            verify=False,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        # 关闭 Playwright 上下文和浏览器
        for ctx in self._contexts:
            await ctx.close()
        self._contexts.clear()
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        if self._httpx:
            await self._httpx.aclose()
            self._httpx = None

    async def get_text(self, url: str, encoding: str | None = None, **kwargs) -> str:
        """通过 httpx 获取页面文本（不需要 JS 渲染的页面）。

        Args:
            url: 请求 URL
            encoding: 强制指定响应编码（如 "gbk", "gb2312"），None 则自动检测
        """
        await self.rate_limiter.acquire()
        headers = self.ua_rotator.get_headers()

        async def _fetch() -> str:
            assert self._httpx is not None
            resp = await self._httpx.get(url, headers=headers, **kwargs)
            resp.raise_for_status()
            if encoding:
                resp.encoding = encoding
            return resp.text

        return await self.retry_handler.execute(_fetch)

    async def get_json(self, url: str, **kwargs) -> dict | list:
        """通过 httpx 获取 JSON 响应。"""
        await self.rate_limiter.acquire()
        headers = self.ua_rotator.get_headers()
        headers["Accept"] = "application/json"

        async def _fetch() -> dict | list:
            assert self._httpx is not None
            resp = await self._httpx.get(url, headers=headers, **kwargs)
            resp.raise_for_status()
            return resp.json()

        return await self.retry_handler.execute(_fetch)

    async def get_page(self, url: str, wait_for: str = "networkidle", timeout: int = 30000) -> str:
        """通过 Playwright 渲染页面并返回 HTML（用于 SPA 页面）。"""
        await self.rate_limiter.acquire()
        page = await self._get_page()

        await page.goto(url, wait_until=wait_for, timeout=timeout)
        content = await page.content()
        return content

    @asynccontextmanager
    async def playwright_page(self) -> AsyncGenerator[Page, None]:
        """获取 Playwright Page 对象用于复杂交互。"""
        page = await self._get_page()
        try:
            yield page
        finally:
            await page.close()

    async def _ensure_browser(self) -> Browser:
        if self._browser is None:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
        return self._browser

    async def _get_page(self) -> Page:
        browser = await self._ensure_browser()
        context = await browser.new_context(
            user_agent=self.ua_rotator.get(),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        self._contexts.append(context)
        return await context.new_page()
