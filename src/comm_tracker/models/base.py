"""基础枚举和混入类。"""

import enum
from datetime import datetime

from sqlmodel import Field


class SourceType(str, enum.Enum):
    """数据源类型。"""

    OFFICIAL = "official"
    NEWS = "news"
    SOCIAL = "social"
    PATENT = "patent"
    FINANCE = "finance"


class ArticleCategory(str, enum.Enum):
    """文章/资讯分类。"""

    PRODUCT_RELEASE = "product_release"
    TECH_DYNAMIC = "tech_dynamic"
    MARKET_FINANCE = "market_finance"
    INDUSTRY_NEWS = "industry_news"
    PATENT_FILING = "patent_filing"
    STANDARD_CONTRIBUTION = "standard_contribution"


class FinancialReportType(str, enum.Enum):
    """财务报告类型。"""

    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"


class TimestampMixin:
    """通用时间戳字段。"""

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
