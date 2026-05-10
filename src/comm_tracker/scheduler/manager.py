"""调度管理器——封装 APScheduler。"""

import asyncio
import logging
import signal
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from comm_tracker.collectors.registry import auto_discover, get_collector, list_collectors
from comm_tracker.config import get_database_url, load_manufacturers
from comm_tracker.db import get_session, init_db
from comm_tracker.pipeline.processor import Pipeline
from comm_tracker.repository import Repository
from comm_tracker.scheduler.jobs import get_enabled_schedules
from comm_tracker.utils.http_client import HttpClient

logger = logging.getLogger(__name__)


class SchedulerManager:
    """定时调度管理器。"""

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or get_database_url()
        self._client: HttpClient | None = None
        self._scheduler: AsyncIOScheduler | None = None

    def start(self) -> None:
        """启动调度器（阻塞运行）。"""
        init_db(self.db_url)
        auto_discover()

        jobstore = SQLAlchemyJobStore(url=self.db_url.replace("sqlite:///", "sqlite:///data/db/jobs.db"))
        self._scheduler = AsyncIOScheduler(
            jobstores={"default": jobstore},
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
        )

        # 注册所有已启用数据源的定时任务
        schedules = get_enabled_schedules()
        for collector_name, schedule_params in schedules.items():
            cls = get_collector(collector_name)
            if not cls:
                logger.warning("采集器未注册，跳过: %s", collector_name)
                continue

            trigger = schedule_params.pop("trigger", "interval")
            self._scheduler.add_job(
                self._run_collector_job,
                trigger=trigger,
                args=[collector_name],
                id=f"collect_{collector_name}",
                name=f"采集 {collector_name}",
                replace_existing=True,
                **schedule_params,
            )
            logger.info("注册定时任务: %s (%s)", collector_name, trigger)

        # 优雅退出
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown)

        self._scheduler.start()
        logger.info("调度器已启动，共 %d 个任务", len(schedules))

        # 阻塞主线程
        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            self._shutdown()

    def _shutdown(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("调度器已停止")

    async def _run_collector_job(self, collector_name: str) -> None:
        """定时任务执行入口。"""
        logger.info("开始执行采集任务: %s", collector_name)

        cls = get_collector(collector_name)
        if not cls:
            logger.error("采集器未找到: %s", collector_name)
            return

        # 确保 HttpClient 已初始化
        if self._client is None:
            self._client = HttpClient()

        # 需要用 async with 但不能每次都创建/销毁浏览器
        # 对于 Playwright 采集器，在单次任务内管理生命周期
        client_needs_init = cls.needs_js
        client = self._client

        try:
            if client_needs_init:
                # Playwright 采集器需要独立管理浏览器生命周期
                async with HttpClient() as pw_client:
                    await self._do_collect(pw_client, collector_name, cls)
            else:
                # httpx 采集器可以复用
                if not client._httpx:
                    await client.__aenter__()
                await self._do_collect(client, collector_name, cls)
        except Exception:
            logger.exception("采集任务失败: %s", collector_name)

    async def _do_collect(self, client, collector_name: str, cls) -> None:
        """执行单个采集器的采集流程。"""
        collector = cls(client=client)
        mfrs = load_manufacturers()

        for mfr in mfrs:
            code = mfr["short_code"]
            if code not in collector.supported_manufacturers:
                continue

            try:
                session_gen = get_session(self.db_url)
                session = next(session_gen)
                repo = Repository(session)

                db_mfr = repo.get_or_create_manufacturer(
                    code, mfr["name_zh"], mfr.get("name_en", ""),
                    official_url=mfr.get("official_url", ""),
                    news_url=mfr.get("news_url", ""),
                )

                checkpoint = repo.get_checkpoint(collector_name, code)
                parsed_items = await collector.run(code, checkpoint)
                pipeline = Pipeline(enable_llm=True, session=session)
                processed = await pipeline.process(parsed_items)
                saved = repo.save_parsed_items(processed, db_mfr.id, collector.source_type, collector_name)

                last_url = processed[-1].original_url if processed else ""
                repo.save_checkpoint(collector_name, code, last_url=last_url, items_count=saved)

                session.close()
                logger.info("[%s] %s: %d 条新增", collector_name, mfr["name_zh"], saved)
            except Exception:
                logger.exception("[%s] %s 采集失败", collector_name, code)
