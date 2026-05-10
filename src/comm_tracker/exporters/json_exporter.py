"""JSON 导出。"""

import json
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal

from sqlmodel import Session, select

from comm_tracker.models import Article, Manufacturer


class _DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def export_json(
    session: Session,
    output_path: str | Path,
    manufacturer: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    category: str | None = None,
) -> int:
    """导出文章为 JSON 文件。返回导出条数。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stmt = select(Article)
    if manufacturer:
        mfr = session.exec(select(Manufacturer).where(Manufacturer.short_code == manufacturer)).first()
        if mfr:
            stmt = stmt.where(Article.manufacturer_id == mfr.id)
    if since:
        stmt = stmt.where(Article.published_at >= since)
    if until:
        stmt = stmt.where(Article.published_at <= until)
    if category:
        stmt = stmt.where(Article.category == category)

    stmt = stmt.order_by(Article.published_at.desc())
    articles = session.exec(stmt).all()

    # 关联厂家名称
    mfr_cache: dict[int, str] = {}
    for m in session.exec(select(Manufacturer)).all():
        mfr_cache[m.id] = m.name_zh

    data = []
    for article in articles:
        row = article.model_dump()
        row["manufacturer_name"] = mfr_cache.get(article.manufacturer_id, "")
        data.append(row)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, cls=_DateTimeEncoder)

    return len(data)
