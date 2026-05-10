"""中文文本处理工具：分词、日期解析。"""

import re
from datetime import datetime

import jieba
from dateutil import parser as date_parser


def segment(text: str) -> list[str]:
    """用 jieba 分词，返回词列表。"""
    return list(jieba.cut(text))


def clean_text(html_or_text: str) -> str:
    """去除多余空白，标准化文本。"""
    text = re.sub(r"\s+", " ", html_or_text).strip()
    return text


def parse_chinese_date(date_str: str) -> datetime | None:
    """解析中文格式的日期字符串。

    支持格式：
      - 2026年3月27日
      - 2026-03-27
      - 2026.03.27
      - 2026年03月
    """
    if not date_str:
        return None

    # 中文日期格式
    cn_match = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", date_str)
    if cn_match:
        return datetime(int(cn_match.group(1)), int(cn_match.group(2)), int(cn_match.group(3)))

    cn_month_match = re.match(r"(\d{4})年(\d{1,2})月", date_str)
    if cn_month_match:
        return datetime(int(cn_month_match.group(1)), int(cn_month_match.group(2)), 1)

    try:
        return date_parser.parse(date_str)
    except (ValueError, TypeError):
        return None
