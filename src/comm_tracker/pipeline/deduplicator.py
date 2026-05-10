"""去重处理器。

策略：
1. URL 精确去重（已由 Repository 层保证）
2. 标题相似度去重——基于 jieba 分词后的 Jaccard 相似度
   适用于中英文混合的通信行业新闻标题。
"""

import logging
from difflib import SequenceMatcher

import jieba

from comm_tracker.collectors.base import ParsedItem

logger = logging.getLogger(__name__)

# 标题相似度阈值（0-1），超过此值视为重复
TITLE_SIMILARITY_THRESHOLD = 0.8


class Deduplicator:
    """基于标题相似度的去重。

    使用 jieba 分词后计算词集合的 Jaccard 相似度 + SequenceMatcher 比对，
    任一维度超过阈值即判定为近似重复。
    """

    def __init__(self, existing_titles: list[str] | None = None):
        self._title_words_list: list[set[str]] = []
        self._raw_titles: list[str] = []
        if existing_titles:
            for t in existing_titles:
                self._add_title(t)

    def _add_title(self, title: str) -> None:
        words = set(jieba.cut(title))
        # 过滤单字符停用词
        words = {w for w in words if len(w) > 1}
        self._title_words_list.append(words)
        self._raw_titles.append(title)

    def is_duplicate(self, item: ParsedItem) -> bool:
        """判断标题是否与已有条目近似重复。"""
        title = item.title
        if not title.strip():
            return False

        new_words = {w for w in jieba.cut(title) if len(w) > 1}

        for i, existing_words in enumerate(self._title_words_list):
            # Jaccard 相似度
            if new_words and existing_words:
                intersection = new_words & existing_words
                union = new_words | existing_words
                jaccard = len(intersection) / len(union)
                if jaccard > TITLE_SIMILARITY_THRESHOLD:
                    return True

            # SequenceMatcher 比对（兜底）
            ratio = SequenceMatcher(None, title, self._raw_titles[i]).ratio()
            if ratio > 0.9:
                return True

        self._add_title(title)
        return False

    def process(self, items: list[ParsedItem]) -> list[ParsedItem]:
        """过滤近似重复项。"""
        results: list[ParsedItem] = []
        dup_count = 0
        for item in items:
            if self.is_duplicate(item):
                dup_count += 1
                logger.debug("近似重复，跳过: %s", item.title[:50])
            else:
                results.append(item)

        if dup_count > 0:
            logger.info("去重: 过滤 %d 条近似重复，保留 %d 条", dup_count, len(results))
        return results
