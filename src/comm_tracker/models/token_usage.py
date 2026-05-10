"""LLM Token 用量追踪模型。"""

from datetime import date as date_type
from datetime import datetime

from sqlmodel import Field, SQLModel


class TokenUsage(SQLModel, table=True):
    __tablename__ = "token_usages"

    id: int | None = Field(default=None, primary_key=True)
    usage_date: date_type = Field(default_factory=date_type.today, index=True, description="日期")
    model: str = Field(default="", description="模型名称")
    operation: str = Field(default="chat", description="操作类型: chat/classify/summarize")
    prompt_tokens: int = Field(default=0, description="输入 token 数")
    completion_tokens: int = Field(default=0, description="输出 token 数")
    total_tokens: int = Field(default=0, description="总 token 数")
    request_count: int = Field(default=1, description="请求次数")
    created_at: datetime = Field(default_factory=datetime.now)
