"""产品发布模型。"""

from datetime import date

from sqlmodel import Field, SQLModel


class ProductRelease(SQLModel, table=True):
    __tablename__ = "product_releases"

    id: int | None = Field(default=None, primary_key=True)
    manufacturer_id: int = Field(foreign_key="manufacturers.id", index=True)
    article_id: int | None = Field(default=None, foreign_key="articles.id")
    product_name: str = Field(description="产品名称")
    product_category: str = Field(description="产品类别，如'无线接入''光网络''核心网'")
    description: str = Field(default="")
    release_date: date | None = Field(default=None)
    key_specs: str = Field(default="{}", description="关键规格 JSON")
