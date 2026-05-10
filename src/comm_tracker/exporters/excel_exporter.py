"""Excel 导出。"""

from pathlib import Path
from datetime import datetime

from openpyxl import Workbook
from sqlmodel import Session, select

from comm_tracker.models import Article, Manufacturer


def export_excel(
    session: Session,
    output_path: str | Path,
    manufacturer: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    category: str | None = None,
) -> int:
    """导出文章为 Excel 文件。返回导出条数。"""
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

    wb = Workbook()
    ws = wb.active
    ws.title = "通信设备厂家动态"

    # 表头
    headers = ["厂家", "标题", "分类", "来源", "发布日期", "采集时间", "摘要", "URL"]
    ws.append(headers)

    # 设置列宽
    col_widths = [15, 50, 15, 15, 12, 18, 40, 60]
    for i, width in enumerate(col_widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width

    # 数据行
    for article in articles:
        ws.append([
            mfr_cache.get(article.manufacturer_id, ""),
            article.title,
            article.category or "",
            article.source_name,
            article.published_at.strftime("%Y-%m-%d") if article.published_at else "",
            article.collected_at.strftime("%Y-%m-%d %H:%M") if article.collected_at else "",
            article.summary or article.content_clean[:100] if article.content_clean else "",
            article.original_url,
        ])

    wb.save(output_path)
    return len(articles)
