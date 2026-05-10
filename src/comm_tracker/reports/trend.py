"""趋势报告生成器——基于已采集数据生成周度/月度分析报告。"""

import json
import logging
from datetime import datetime, timedelta
from collections import Counter

from sqlalchemy import func
from sqlmodel import Session, select

from comm_tracker.models import Article, Manufacturer
from comm_tracker.models.base import ArticleCategory

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """趋势数据分析器。

    从数据库中提取指定时间范围内的统计数据，
    生成结构化的趋势报告。
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def generate_report(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        period: str = "weekly",
    ) -> dict:
        """生成趋势报告。

        Args:
            start_date: 起始日期（默认 7 天前）
            end_date: 结束日期（默认现在）
            period: 报告周期 "weekly" 或 "monthly"

        Returns:
            结构化报告字典
        """
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            if period == "monthly":
                start_date = end_date - timedelta(days=30)
            else:
                start_date = end_date - timedelta(days=7)

        # 基础查询：时间范围内的文章
        base_query = select(Article).where(
            Article.collected_at >= start_date,
            Article.collected_at <= end_date,
        )

        # 1. 总览
        total = self.session.exec(
            select(func.count(Article.id)).where(
                Article.collected_at >= start_date,
                Article.collected_at <= end_date,
            )
        ).one()

        # 2. 上一周期对比
        prev_start = start_date - (end_date - start_date)
        prev_total = self.session.exec(
            select(func.count(Article.id)).where(
                Article.collected_at >= prev_start,
                Article.collected_at < start_date,
            )
        ).one()
        change_pct = ((total - prev_total) / prev_total * 100) if prev_total > 0 else 0

        # 3. 分类分布
        category_rows = self.session.exec(
            select(Article.category, func.count(Article.id))
            .where(Article.collected_at >= start_date, Article.collected_at <= end_date)
            .group_by(Article.category)
            .order_by(func.count(Article.id).desc())
        ).all()
        categories = {
            (cat.value if hasattr(cat, "value") else str(cat)): cnt
            for cat, cnt in category_rows
        }

        # 4. 厂家活跃度
        mfr_rows = self.session.exec(
            select(Manufacturer.name_zh, func.count(Article.id))
            .join(Article, Article.manufacturer_id == Manufacturer.id)
            .where(Article.collected_at >= start_date, Article.collected_at <= end_date)
            .group_by(Manufacturer.name_zh)
            .order_by(func.count(Article.id).desc())
        ).all()
        manufacturers = {name: cnt for name, cnt in mfr_rows}

        # 5. 数据源分布
        source_rows = self.session.exec(
            select(Article.source_name, func.count(Article.id))
            .where(Article.collected_at >= start_date, Article.collected_at <= end_date)
            .group_by(Article.source_name)
            .order_by(func.count(Article.id).desc())
        ).all()
        sources = {name: cnt for name, cnt in source_rows}

        # 6. 日趋势
        daily_rows = self.session.exec(
            select(func.date(Article.collected_at), func.count(Article.id))
            .where(Article.collected_at >= start_date, Article.collected_at <= end_date)
            .group_by(func.date(Article.collected_at))
            .order_by(func.date(Article.collected_at))
        ).all()
        daily_trend = {str(day): cnt for day, cnt in daily_rows}

        # 7. 热点标题关键词
        articles = self.session.exec(
            select(Article.title)
            .where(Article.collected_at >= start_date, Article.collected_at <= end_date)
        ).all()
        hot_keywords = self._extract_hot_keywords(articles)

        # 8. 摘要覆盖率
        with_summary = self.session.exec(
            select(func.count(Article.id))
            .where(
                Article.collected_at >= start_date,
                Article.collected_at <= end_date,
                Article.summary.is_not(None),
            )
        ).one()

        report = {
            "period": period,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "overview": {
                "total_articles": total,
                "prev_period_total": prev_total,
                "change_percent": round(change_pct, 1),
                "summary_coverage": round(with_summary / total * 100, 1) if total > 0 else 0,
            },
            "categories": categories,
            "manufacturers": manufacturers,
            "sources": sources,
            "daily_trend": daily_trend,
            "hot_keywords": hot_keywords,
        }

        logger.info(
            "趋势报告生成完成: %s ~ %s, 共 %d 条文章",
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            total,
        )

        return report

    def _extract_hot_keywords(self, titles: list[str], top_n: int = 20) -> list[tuple[str, int]]:
        """从标题中提取热点关键词。"""
        import jieba

        # 通信行业相关停用词
        stopwords = {
            "的", "了", "在", "是", "和", "与", "为", "中", "等", "将",
            "将", "被", "以", "从", "对", "上", "下", "有", "其", "到",
            "也", "可", "年", "月", "日", "新", "最", "不", "一", "大",
        }

        counter = Counter()
        for title in titles:
            words = jieba.cut(title)
            for w in words:
                w = w.strip()
                if len(w) >= 2 and w not in stopwords:
                    counter[w] += 1

        return counter.most_common(top_n)

    def format_report_text(self, report: dict) -> str:
        """将结构化报告格式化为可读文本。"""
        lines = []
        overview = report["overview"]

        lines.append(f"# 通信行业{'周' if report['period'] == 'weekly' else '月'}度趋势报告")
        lines.append(f"报告期间: {report['start_date']} ~ {report['end_date']}")
        lines.append("")

        # 总览
        lines.append("## 总览")
        lines.append(f"- 本期文章数: {overview['total_articles']}")
        change = overview["change_percent"]
        arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
        lines.append(f"- 环比变化: {arrow} {abs(change):.1f}%")
        lines.append(f"- 摘要覆盖率: {overview['summary_coverage']:.1f}%")
        lines.append("")

        # 厂家活跃度
        if report["manufacturers"]:
            lines.append("## 厂家活跃度")
            for name, cnt in report["manufacturers"].items():
                lines.append(f"- {name}: {cnt} 条")
            lines.append("")

        # 分类分布
        if report["categories"]:
            lines.append("## 分类分布")
            for cat, cnt in report["categories"].items():
                lines.append(f"- {cat}: {cnt} 条")
            lines.append("")

        # 数据源
        if report["sources"]:
            lines.append("## 数据源")
            for name, cnt in report["sources"].items():
                lines.append(f"- {name}: {cnt} 条")
            lines.append("")

        # 日趋势
        if report["daily_trend"]:
            lines.append("## 日采集趋势")
            for day, cnt in sorted(report["daily_trend"].items()):
                bar = "█" * min(cnt, 30)
                lines.append(f"- {day}: {bar} {cnt}")
            lines.append("")

        # 热点关键词
        if report["hot_keywords"]:
            lines.append("## 热点关键词 TOP 15")
            for kw, cnt in report["hot_keywords"][:15]:
                lines.append(f"- {kw}: {cnt} 次")
            lines.append("")

        return "\n".join(lines)
