"""处理管道编排器。"""

import logging

from sqlmodel import Session

from comm_tracker.collectors.base import ParsedItem
from comm_tracker.llm.client import LLMClient
from comm_tracker.pipeline.cleaner import Cleaner
from comm_tracker.pipeline.deduplicator import Deduplicator
from comm_tracker.pipeline.classifier import KeywordClassifier, LLMClassifier
from comm_tracker.pipeline.summarizer import Summarizer

logger = logging.getLogger(__name__)


class Pipeline:
    """数据处理管道：按顺序执行各处理器。

    流程：Cleaner → Deduplicator → Classifier → Summarizer

    enable_llm=True 时使用 LLM 增强分类器 + 摘要生成；
    否则仅使用关键词分类器。
    """

    def __init__(self, enable_llm: bool = False, session: Session | None = None) -> None:
        self.cleaner = Cleaner()
        self.deduplicator = Deduplicator()
        self._enable_llm = enable_llm
        self._session = session
        # 无 LLM 时使用纯关键词分类器
        self.classifier = KeywordClassifier()

    async def process(self, items: list[ParsedItem]) -> list[ParsedItem]:
        """对一组数据项执行完整处理管道。"""
        # 1. 清洗
        cleaned: list[ParsedItem] = []
        for item in items:
            try:
                cleaned.append(self.cleaner.process(item))
            except Exception:
                logger.exception("清洗失败: %s", item.original_url)

        # 2. 去重
        deduped = self.deduplicator.process(cleaned)

        if not deduped:
            return deduped

        # 3 & 4: LLM 增强模式（分类 + 摘要共享同一个 client）
        if self._enable_llm:
            deduped = await self._run_llm_stages(deduped)
        else:
            self.classifier.process(deduped)

        return deduped

    async def _run_llm_stages(self, items: list[ParsedItem]) -> list[ParsedItem]:
        """LLM 增强阶段：分类 + 摘要（共享 LLM client 实例）。"""
        async with LLMClient(session=self._session) as client:
            # 3. LLM 增强分类
            llm_classifier = LLMClassifier(client)
            items = await llm_classifier.process(items)

            # 4. LLM 摘要生成
            summarizer = Summarizer(client)
            items = await summarizer.process(items)

        return items
