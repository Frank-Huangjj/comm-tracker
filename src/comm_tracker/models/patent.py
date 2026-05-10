"""专利记录模型。"""

from datetime import date

from sqlmodel import Field, SQLModel


class PatentRecord(SQLModel, table=True):
    __tablename__ = "patent_records"

    id: int | None = Field(default=None, primary_key=True)
    manufacturer_id: int = Field(foreign_key="manufacturers.id", index=True)
    patent_number: str = Field(unique=True, index=True, description="专利号")
    title: str = Field(description="专利标题")
    filing_date: date | None = Field(default=None, description="申请日期")
    publication_date: date | None = Field(default=None, description="公布日期")
    abstract: str = Field(default="", description="摘要")
    patent_type: str = Field(default="", description="类型：发明/实用新型/外观设计")
    status: str = Field(default="", description="专利状态")
    ipc_classification: str = Field(default="", description="IPC 分类号")
    extra_metadata: str = Field(default="{}")
