"""核心文章实体模型。"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from comm_tracker.models.base import ArticleCategory, SourceType


class Article(SQLModel, table=True):
    __tablename__ = "articles"

    id: int | None = Field(default=None, primary_key=True)
    manufacturer_id: int = Field(foreign_key="manufacturers.id", index=True)
    source_type: SourceType = Field(description="数据源类型")
    source_name: str = Field(description="采集器名称，如'huawei_news'")
    category: ArticleCategory | None = Field(default=None, description="文章分类")
    title: str = Field(description="标题")
    original_url: str = Field(unique=True, index=True, description="原始 URL")
    content_raw: str = Field(default="", description="原始 HTML/文本")
    content_clean: str = Field(default="", description="清洗后纯文本")
    summary: str | None = Field(default=None, description="LLM 生成的摘要")
    published_at: datetime | None = Field(default=None, index=True, description="发布时间")
    collected_at: datetime = Field(default_factory=datetime.now, description="采集时间")
    author: str | None = Field(default=None)
    tags: str = Field(default="[]", description="标签 JSON 数组")
    extra_metadata: str = Field(default="{}", description="来源特定元数据 JSON")
