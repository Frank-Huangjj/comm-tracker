"""HTML 清洗处理器。"""

import re

from bs4 import BeautifulSoup

from comm_tracker.collectors.base import ParsedItem


class Cleaner:
    """清洗 HTML 内容为纯文本。"""

    # 移除的标签（导航、脚本等）
    REMOVE_TAGS = {"script", "style", "nav", "footer", "header", "noscript"}

    def process(self, item: ParsedItem) -> ParsedItem:
        """清洗 content_raw 中的 HTML，输出到 content_clean。"""
        if not item.content_raw:
            item.content_clean = ""
            return item

        # 如果已经是纯文本（没有 HTML 标签），直接清洗
        if "<" not in item.content_raw:
            item.content_clean = self._normalize_whitespace(item.content_raw)
            return item

        soup = BeautifulSoup(item.content_raw, "lxml")

        # 移除无用标签
        for tag in soup.find_all(self.REMOVE_TAGS):
            tag.decompose()

        # 获取文本
        text = soup.get_text(separator="\n")

        item.content_clean = self._normalize_whitespace(text)
        return item

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """标准化空白字符。"""
        # 去除行首行尾空白
        lines = [line.strip() for line in text.split("\n")]
        # 移除空行
        lines = [line for line in lines if line]
        return "\n".join(lines)
