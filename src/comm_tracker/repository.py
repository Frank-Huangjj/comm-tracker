"""数据存储仓库——封装 CRUD 操作。"""

import json
import logging
from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, select

from comm_tracker.collectors.base import ParsedItem
from comm_tracker.models import (
    Article,
    CollectionCheckpoint,
    Manufacturer,
)
from comm_tracker.models.base import SourceType
from comm_tracker.models.token_usage import TokenUsage

logger = logging.getLogger(__name__)


class Repository:
    """数据存储仓库。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_manufacturer(self, short_code: str) -> Manufacturer | None:
        stmt = select(Manufacturer).where(Manufacturer.short_code == short_code)
        return self.session.exec(stmt).first()

    def get_or_create_manufacturer(
        self, short_code: str, name_zh: str, name_en: str = "", **kwargs
    ) -> Manufacturer:
        mfr = self.get_manufacturer(short_code)
        if mfr:
            return mfr
        mfr = Manufacturer(short_code=short_code, name_zh=name_zh, name_en=name_en, **kwargs)
        self.session.add(mfr)
        self.session.commit()
        self.session.refresh(mfr)
        return mfr

    def save_article(self, item: ParsedItem, manufacturer_id: int, source_type: SourceType, source_name: str) -> Article | None:
        """保存解析后的文章，URL 去重。"""
        # 检查是否已存在
        existing = self.session.exec(
            select(Article).where(Article.original_url == item.original_url)
        ).first()
        if existing:
            # 回填缺失字段：摘要和分类
            updated = False
            if item.summary and not existing.summary:
                existing.summary = item.summary
                updated = True
            if item.category and not existing.category:
                existing.category = item.category
                updated = True
            if updated:
                self.session.add(existing)
                self.session.commit()
                logger.debug("回填已有文章字段: %s", item.original_url)
            return None

        article = Article(
            manufacturer_id=manufacturer_id,
            source_type=source_type,
            source_name=source_name,
            category=item.category,
            title=item.title,
            original_url=item.original_url,
            content_raw=item.content_raw,
            content_clean=item.content_clean,
            summary=item.summary,
            published_at=item.published_at,
            author=item.author,
            tags=json.dumps(item.tags, ensure_ascii=False),
            extra_metadata=json.dumps(item.extra_metadata, ensure_ascii=False),
        )
        self.session.add(article)
        self.session.commit()
        self.session.refresh(article)
        logger.info("保存文章: [%s] %s", source_name, item.title[:50])
        return article

    def get_checkpoint(self, collector_name: str, manufacturer_code: str) -> CollectionCheckpoint | None:
        stmt = select(CollectionCheckpoint).where(
            CollectionCheckpoint.collector_name == collector_name,
            CollectionCheckpoint.manufacturer_code == manufacturer_code,
        )
        return self.session.exec(stmt).first()

    def save_checkpoint(
        self,
        collector_name: str,
        manufacturer_code: str,
        last_url: str = "",
        items_count: int = 0,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        checkpoint = self.get_checkpoint(collector_name, manufacturer_code)
        if checkpoint:
            checkpoint.last_collected_at = datetime.now()
            checkpoint.last_url_or_id = last_url
            checkpoint.status = status
            checkpoint.items_collected = items_count
            checkpoint.error_message = error_message
            checkpoint.updated_at = datetime.now()
        else:
            checkpoint = CollectionCheckpoint(
                collector_name=collector_name,
                manufacturer_code=manufacturer_code,
                last_collected_at=datetime.now(),
                last_url_or_id=last_url,
                status=status,
                items_collected=items_count,
                error_message=error_message,
            )
            self.session.add(checkpoint)
        self.session.commit()

    def save_parsed_items(
        self,
        items: list[ParsedItem],
        manufacturer_id: int,
        source_type: SourceType,
        source_name: str,
    ) -> int:
        """批量保存解析后的数据项，返回新增数量。"""
        saved = 0
        for item in items:
            article = self.save_article(item, manufacturer_id, source_type, source_name)
            if article:
                saved += 1
        return saved

    # --- 统计查询 ---

    def get_article_count(self) -> int:
        """文章总数。"""
        result = self.session.exec(select(func.count(Article.id))).one()
        return result

    def get_category_distribution(self) -> dict[str, int]:
        """分类分布。"""
        rows = self.session.exec(
            select(Article.category, func.count(Article.id))
            .group_by(Article.category)
        ).all()
        result = {}
        for cat, cnt in rows:
            name = cat.value if hasattr(cat, "value") else str(cat or "未分类")
            result[name] = cnt
        return result

    def get_source_distribution(self) -> dict[str, int]:
        """数据源分布。"""
        rows = self.session.exec(
            select(Article.source_name, func.count(Article.id))
            .group_by(Article.source_name)
        ).all()
        return {name: cnt for name, cnt in rows}

    def get_manufacturer_distribution(self) -> dict[str, int]:
        """厂家分布。"""
        rows = self.session.exec(
            select(Manufacturer.name_zh, func.count(Article.id))
            .join(Article, Article.manufacturer_id == Manufacturer.id)
            .group_by(Manufacturer.name_zh)
        ).all()
        return {name: cnt for name, cnt in rows}

    def get_summary_stats(self) -> tuple[int, int]:
        """摘要统计: (有摘要数, 总数)。"""
        with_summary = self.session.exec(
            select(func.count(Article.id)).where(Article.summary.is_not(None))
        ).one()
        total = self.get_article_count()
        return with_summary, total

    def get_token_usage_today(self) -> dict[str, int]:
        """今日 token 用量。"""
        from datetime import date
        rows = self.session.exec(
            select(TokenUsage.operation, func.sum(TokenUsage.total_tokens), func.count(TokenUsage.id))
            .where(TokenUsage.usage_date == date.today())
            .group_by(TokenUsage.operation)
        ).all()
        result: dict[str, int] = {}
        for op, total_tokens, req_count in rows:
            result[op] = int(total_tokens or 0)
            result[f"{op}_requests"] = int(req_count or 0)
        return result

    def get_token_usage_total(self) -> int:
        """历史累计 token 用量。"""
        result = self.session.exec(
            select(func.sum(TokenUsage.total_tokens))
        ).one()
        return int(result or 0)

    def get_checkpoints(self) -> list[CollectionCheckpoint]:
        """所有采集检查点。"""
        return list(self.session.exec(select(CollectionCheckpoint)).all())
