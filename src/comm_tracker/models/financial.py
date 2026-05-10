"""财务数据模型。"""

from datetime import date
from decimal import Decimal

from sqlmodel import Field, SQLModel

from comm_tracker.models.base import FinancialReportType


class FinancialReport(SQLModel, table=True):
    __tablename__ = "financial_reports"

    id: int | None = Field(default=None, primary_key=True)
    manufacturer_id: int = Field(foreign_key="manufacturers.id", index=True)
    report_type: FinancialReportType = Field(description="报告类型")
    period: str = Field(description="报告期，如'2025-Q4'、'2025-H1'")
    revenue: Decimal | None = Field(default=None, description="营收（亿元）")
    net_profit: Decimal | None = Field(default=None, description="净利润（亿元）")
    rd_expense: Decimal | None = Field(default=None, description="研发费用（亿元）")
    filing_date: date | None = Field(default=None)
    pdf_url: str = Field(default="")
    extra_metrics: str = Field(default="{}", description="其他指标 JSON")
