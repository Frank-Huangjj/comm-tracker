"""探测华为新闻页面的实际 DOM 结构，用于调试采集器选择器。"""

import asyncio
import json

from playwright.async_api import async_playwright


async def explore():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080}, locale="zh-CN")

        print("=== 访问华为新闻中心 ===")
        await page.goto("https://www.huawei.com/cn/news", wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(5000)

        title = await page.title()
        print(f"页面标题: {title}")
        print(f"URL: {page.url}")

        # 探测页面中的链接
        print("\n=== 页面中所有含 /news 的链接 ===")
        links = await page.eval_on_selector_all("a[href*='news']", """els => els.map(el => ({
            href: el.href,
            text: el.textContent.trim().substring(0, 80),
            tag: el.tagName,
            className: el.className.substring(0, 60)
        }))""")
        for link in links[:20]:
            print(f"  {link}")

        # 探测可能的新闻卡片容器
        print("\n=== 探测常见新闻卡片 class ===")
        card_selectors = [
            "[class*='news-item']", "[class*='newsItem']", "[class*='card']",
            "[class*='article']", "[class*='list-item']", "[class*='story']",
            "article", ".item", ".swiper-slide",
        ]
        for sel in card_selectors:
            count = await page.locator(sel).count()
            if count > 0:
                print(f"  {sel}: {count} 个")
                # 取第一个的 HTML 结构
                html = await page.locator(sel).first.evaluate("el => el.outerHTML.substring(0, 500)")
                print(f"    样例: {html[:300]}")

        # 拦截网络请求，查看是否有 JSON API
        print("\n=== 查找可能的 API 请求 ===")

        api_responses: list[dict] = []

        async def handle_response(response):
            url = response.url
            if any(kw in url.lower() for kw in ["api", "json", "ajax", "graphql", "search"]):
                ct = response.headers.get("content-type", "")
                if "json" in ct or "javascript" in ct:
                    api_responses.append({"url": url, "status": response.status, "content_type": ct})

        page.on("response", handle_response)

        # 重新加载页面以捕获请求
        await page.reload(wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(3000)

        for r in api_responses:
            print(f"  [{r['status']}] {r['url'][:120]}")

        # 保存页面 HTML 以供分析
        html = await page.content()
        with open("data/cache/huawei_news_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n页面 HTML 已保存到 data/cache/huawei_news_page.html ({len(html)} bytes)")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(explore())
