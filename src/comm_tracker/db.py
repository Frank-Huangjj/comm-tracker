"""数据库引擎与会话管理。"""

from pathlib import Path
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from comm_tracker.models import (  # noqa: F401 — ensure models are registered
    Article,
    CollectionCheckpoint,
    FinancialReport,
    Manufacturer,
    PatentRecord,
    ProductRelease,
    TokenUsage,
)

_engine = None


def get_engine(db_url: str | None = None):
    """获取或创建数据库引擎。"""
    global _engine
    if _engine is not None and db_url is None:
        return _engine

    if db_url is None:
        db_path = Path("data/db/comm_tracker.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{db_path}"

    _engine = create_engine(db_url, echo=False)
    return _engine


def init_db(db_url: str | None = None) -> None:
    """创建所有表。"""
    engine = get_engine(db_url)
    SQLModel.metadata.create_all(engine)


def get_session(db_url: str | None = None) -> Generator[Session, None, None]:
    """获取数据库会话（上下文管理器）。"""
    engine = get_engine(db_url)
    with Session(engine) as session:
        yield session
