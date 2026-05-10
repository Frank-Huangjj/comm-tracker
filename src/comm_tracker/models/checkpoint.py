"""采集检查点模型——增量采集状态追踪。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class CollectionCheckpoint(SQLModel, table=True):
    __tablename__ = "collection_checkpoints"

    id: int | None = Field(default=None, primary_key=True)
    collector_name: str = Field(index=True, description="采集器名称")
    manufacturer_code: str = Field(index=True, description="厂家短编码")
    last_collected_at: datetime | None = Field(default=None, description="最新采集时间戳")
    last_url_or_id: str = Field(default="", description="最后处理的 URL/ID")
    status: str = Field(default="success", description="状态：success/partial_failure/error")
    items_collected: int = Field(default=0)
    error_message: str | None = Field(default=None)
    updated_at: datetime = Field(default_factory=datetime.now)
