"""厂家信息模型。"""

from sqlmodel import Field, SQLModel


class Manufacturer(SQLModel, table=True):
    __tablename__ = "manufacturers"

    id: int | None = Field(default=None, primary_key=True)
    name_zh: str = Field(description="中文名称，如'华为技术有限公司'")
    name_en: str = Field(description="英文名称，如'Huawei Technologies'")
    short_code: str = Field(unique=True, index=True, description="短编码，如'huawei'")
    stock_codes: str = Field(default="[]", description="股票代码 JSON 数组")
    official_url: str = Field(default="", description="官网地址")
    news_url: str = Field(default="", description="新闻页地址")
    active: bool = Field(default=True)
    created_at: str = ""
    updated_at: str = ""
