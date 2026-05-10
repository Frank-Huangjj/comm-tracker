"""基于 LLM 的文章摘要生成器。"""

import logging

from comm_tracker.collectors.base import ParsedItem
from comm_tracker.llm.client import LLMClient, TokenBudgetExhausted

logger = logging.getLogger(__name__)

# 摘要生成的系统提示
SUMMARY_SYSTEM_PROMPT = """你是一位通信行业资讯摘要专家。请为以下通信行业相关的文章生成一段简洁的中文摘要。

要求：
- 摘要长度 80-150 字
- 突出关键信息：产品/技术名称、厂商、核心数据、重要结论
- 语言精练，使用客观陈述
- 如果文章内容不足以生成有意义的摘要，请回复"内容不足，无法生成摘要"
- 只输出摘要文本，不要输出其他内容"""

# 单篇文章摘要的 prompt 模板
SUMMARY_USER_TEMPLATE = """文章标题：{title}

文章内容：
{content}

请生成摘要："""

# 批量摘要的最大内容长度（避免超出 token 限制）
MAX_CONTENT_LENGTH = 2000

# 单次批量处理的并发数
BATCH_CONCURRENCY = 5


class Summarizer:
    """基于 LLM 的文章摘要生成器。

    对已清洗和分类的文章调用 LLM 生成摘要，
    自动跳过已有摘要的条目和预算不足的情况。
    """

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    async def summarize_one(self, item: ParsedItem) -> str | None:
        """为单篇文章生成摘要。"""
        content = (item.content_clean or item.content_raw)[:MAX_CONTENT_LENGTH]
        if not content.strip():
            logger.debug("内容为空，跳过摘要: %s", item.title[:50])
            return None

        prompt = SUMMARY_USER_TEMPLATE.format(
            title=item.title,
            content=content,
        )
        try:
            summary = await self._client.chat(
                prompt=prompt,
                system=SUMMARY_SYSTEM_PROMPT,
                max_tokens=300,
                operation="summarize",
            )
            return summary or None
        except TokenBudgetExhausted:
            raise
        except Exception:
            logger.exception("摘要生成失败: %s", item.original_url)
            return None

    async def process(self, items: list[ParsedItem]) -> list[ParsedItem]:
        """批量为文章生成摘要。

        跳过已有摘要的条目，遇到 token 预算耗尽时停止后续调用。
        """
        if not self._client.is_configured:
            logger.warning("LLM 未配置，跳过摘要生成")
            return items

        # 筛选需要生成摘要的条目
        todo = [item for item in items if item.summary is None]
        if not todo:
            logger.info("所有条目已有摘要，跳过")
            return items

        logger.info("开始生成摘要: %d 条待处理", len(todo))

        success = 0
        skipped = 0
        budget_exhausted = False

        for item in todo:
            if budget_exhausted:
                skipped += 1
                continue

            try:
                summary = await self.summarize_one(item)
                if summary:
                    item.summary = summary
                    success += 1
                else:
                    skipped += 1
            except TokenBudgetExhausted:
                logger.warning("Token 预算耗尽，停止摘要生成，剩余 %d 条跳过", len(todo) - success - skipped)
                budget_exhausted = True
                skipped += 1

        logger.info(
            "摘要生成完成: 成功 %d, 跳过 %d (共 %d 条)",
            success,
            skipped,
            len(todo),
        )

        used, limit = self._client.get_daily_usage()
        logger.info("Token 用量: %d/%d", used, limit)

        return items
