"""CSV 导出。"""

import csv
from pathlib import Path
from datetime import datetime

from sqlmodel import Session, select

from comm_tracker.models import Article, Manufacturer


def export_csv(
    session: Session,
    output_path: str | Path,
    manufacturer: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    category: str | None = None,
) -> int:
    """导出文章为 CSV 文件。返回导出条数。"""
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

    columns = ["title", "manufacturer_id", "source_name", "category", "published_at", "original_url", "summary", "tags"]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for article in articles:
            row = article.model_dump()
            writer.writerow(row)

    return len(articles)
