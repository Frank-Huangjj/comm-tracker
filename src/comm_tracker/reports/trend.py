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

        # 字典映射：分类的中文名称
        CATEGORY_ZH = {
            "product_release": "产品发布",
            "tech_dynamic": "技术动态",
            "market_finance": "市场财务",
            "industry_news": "行业新闻",
            "patent_filing": "专利布局",
            "standard_contribution": "标准贡献",
        }

        # 3. 分类分布
        category_rows = self.session.exec(
            select(Article.category, func.count(Article.id))
            .where(Article.collected_at >= start_date, Article.collected_at <= end_date)
            .group_by(Article.category)
            .order_by(func.count(Article.id).desc())
        ).all()
        categories = {
            CATEGORY_ZH.get(cat.value if hasattr(cat, "value") else str(cat), str(cat)): cnt
            for cat, cnt in category_rows
        }

        # 字典映射：厂家的简称
        MFR_SHORT_NAMES = {
            "华为技术有限公司": "华为",
            "中兴通讯股份有限公司": "中兴",
            "爱立信（中国）通信有限公司": "爱立信",
            "诺基亚通信系统（北京）有限公司": "诺基亚",
            "三星电子株式会社": "三星",
            "中国移动通信集团有限公司": "中国移动",
            "中国电信集团有限公司": "中国电信",
            "中国联合网络通信集团有限公司": "中国联通",
            "全球移动通信系统协会": "GSMA",
            "电信管理论坛": "TM Forum",
        }

        # 4. 厂家活跃度
        mfr_rows = self.session.exec(
            select(Manufacturer.name_zh, func.count(Article.id))
            .join(Article, Article.manufacturer_id == Manufacturer.id)
            .where(Article.collected_at >= start_date, Article.collected_at <= end_date)
            .group_by(Manufacturer.name_zh)
            .order_by(func.count(Article.id).desc())
        ).all()
        manufacturers = {MFR_SHORT_NAMES.get(name, name): cnt for name, cnt in mfr_rows}

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

        # 7. 热点关键词 (结合标题与摘要，使用白皮书专业词库)
        articles_data = self.session.exec(
            select(Article.title, Article.summary)
            .where(Article.collected_at >= start_date, Article.collected_at <= end_date)
        ).all()
        hot_keywords = self._extract_hot_keywords(articles_data)

        # 8. 摘要覆盖率
        with_summary = self.session.exec(
            select(func.count(Article.id))
            .where(
                Article.collected_at >= start_date,
                Article.collected_at <= end_date,
                Article.summary.is_not(None),
            )
        ).one()

        # 9. 最新高价值动态 (白皮书可用素材)
        latest_rows = self.session.exec(
            select(Article, Manufacturer.name_zh)
            .outerjoin(Manufacturer, Article.manufacturer_id == Manufacturer.id)
            .where(
                Article.collected_at >= start_date, 
                Article.collected_at <= end_date,
                Article.summary.is_not(None),
                Article.summary != ''
            )
            .order_by(Article.published_at.desc(), Article.collected_at.desc())
            .limit(20)
        ).all()
        
        latest_articles = [
            {
                "发布时间": art.published_at.strftime("%Y-%m-%d") if art.published_at else art.collected_at.strftime("%Y-%m-%d"),
                "厂家": MFR_SHORT_NAMES.get(mfr_name, mfr_name) if mfr_name else "未知",
                "标题": art.title,
                "分类": CATEGORY_ZH.get(art.category.value if hasattr(art.category, "value") else str(art.category), "未知") if art.category else "未知",
                "摘要": art.summary or "",
                "链接": art.original_url
            }
            for art, mfr_name in latest_rows
        ]

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
            "latest_articles": latest_articles,
        }

        logger.info(
            "趋势报告生成完成: %s ~ %s, 共 %d 条文章",
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            total,
        )

        return report

    def _extract_hot_keywords(self, data: list[tuple[str, str]], top_n: int = 15) -> list[tuple[str, int]]:
        """基于白皮书专属词库，从标题和摘要中精准提取核心技术词汇。"""
        # 白皮书强相关的核心技术与行业热词
        domain_keywords = {
            "自智网络", "智能体", "大模型", "算力", "智算", "数智化",
            "5G-A", "6G", "全光网", "数字孪生", "算网融合",
            "人工智能", "AI", "通感一体", "星地融合", "卫星通信",
            "边缘计算", "低空经济", "网络智能化", "算力网络",
            "AIDC", "Token", "内生智能", "云原生", "物联网",
            "数字化转型", "意图驱动", "绿色低碳", "专网", "大语言模型"
        }

        counter = Counter()
        for title, summary in data:
            text = ((title or "") + " " + (summary or "")).lower()
            for kw in domain_keywords:
                if kw.lower() in text:
                    counter[kw] += 1

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
