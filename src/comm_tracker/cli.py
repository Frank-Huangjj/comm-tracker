"""CLI 入口——基于 Typer 的命令行界面。"""

import asyncio
import json
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from comm_tracker.collectors.registry import auto_discover, get_collector, list_collectors
from comm_tracker.config import get_database_url, load_manufacturers, load_sources
from comm_tracker.db import get_session, init_db
from comm_tracker.pipeline.processor import Pipeline
from comm_tracker.repository import Repository
from comm_tracker.utils.http_client import HttpClient

app = typer.Typer(name="comm-tracker", help="通信设备厂家进展跟踪数据采集工具")
console = Console()


def _setup_logging(verbose: bool = False) -> None:
    import os
    from logging.handlers import TimedRotatingFileHandler

    level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

    # 确保日志目录存在
    log_dir = "data/logs"
    os.makedirs(log_dir, exist_ok=True)

    # 获取并配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    # 控制台输出 (Console)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # 文件输出 (按天轮转，保留 30 天)
    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "comm_tracker.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)


@app.command()
def collect(
    source: Optional[str] = typer.Option(None, "--source", "-s", help="指定采集器名称"),
    manufacturer: Optional[str] = typer.Option(None, "--manufacturer", "-m", help="指定厂家编码"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
) -> None:
    """执行数据采集。"""
    _setup_logging(verbose)
    auto_discover()

    db_url = get_database_url()
    init_db(db_url)

    collectors = list_collectors()

    if source:
        if source not in collectors:
            console.print(f"[red]未找到采集器: {source}[/red]")
            raise typer.Exit(1)
        collector_names = [source]
    else:
        # 只采集已启用的数据源
        enabled_sources = {s["name"] for s in load_sources() if s.get("enabled", False)}
        collector_names = [n for n in collectors if n in enabled_sources]

    asyncio.run(_run_collection(collector_names, manufacturer, db_url))


@app.command()
def sources() -> None:
    """列出所有已注册的采集器。"""
    auto_discover()
    collector_map = list_collectors()

    table = Table(title="已注册采集器")
    table.add_column("名称", style="cyan")
    table.add_column("类型", style="green")
    table.add_column("支持厂家")

    for name, cls in collector_map.items():
        table.add_row(name, cls.source_type.value, ", ".join(cls.supported_manufacturers))

    console.print(table)


@app.command()
def manufacturers() -> None:
    """列出已配置的厂家。"""
    mfrs = load_manufacturers()

    table = Table(title="已配置厂家")
    table.add_column("编码", style="cyan")
    table.add_column("中文名")
    table.add_column("英文名")
    table.add_column("股票代码")

    for m in mfrs:
        codes = ", ".join(m.get("stock_codes", [])) or "-"
        table.add_row(m["short_code"], m["name_zh"], m.get("name_en", ""), codes)

    console.print(table)


async def _run_collection(
    collector_names: list[str],
    manufacturer_filter: str | None,
    db_url: str,
) -> None:
    """执行采集任务。"""
    async with HttpClient() as client:
        for name in collector_names:
            cls = get_collector(name)
            if not cls:
                continue

            # 实例化采集器，注入 HTTP 客户端
            collector = cls(client=client)

            # 确定要采集的厂家
            mfrs = load_manufacturers()
            targets = []
            for m in mfrs:
                code = m["short_code"]
                if manufacturer_filter and code != manufacturer_filter:
                    continue
                if code not in collector.supported_manufacturers and "*" not in collector.supported_manufacturers:
                    continue
                targets.append(m)

            for mfr in targets:
                console.print(f"[bold blue]采集 {mfr['name_zh']} ({name})...[/bold blue]")
                try:
                    # 获取检查点
                    session_gen = get_session(db_url)
                    session = next(session_gen)
                    repo = Repository(session)
                    checkpoint = repo.get_checkpoint(name, mfr["short_code"])

                    # 确保厂家记录存在
                    db_mfr = repo.get_or_create_manufacturer(
                        mfr["short_code"], mfr["name_zh"], mfr.get("name_en", ""),
                        official_url=mfr.get("official_url", ""),
                        news_url=mfr.get("news_url", ""),
                    )

                    # 执行采集
                    parsed_items = await collector.run(mfr["short_code"], checkpoint)

                    # 处理管道（传入 session 以持久化 token 用量）
                    pipeline = Pipeline(enable_llm=True, session=session)
                    processed = await pipeline.process(parsed_items)

                    # 存储
                    saved = repo.save_parsed_items(
                        processed, db_mfr.id, collector.source_type, name
                    )

                    # 更新检查点
                    last_url = processed[-1].original_url if processed else ""
                    repo.save_checkpoint(name, mfr["short_code"], last_url=last_url, items_count=saved)

                    session.close()
                    console.print(f"  [green]完成: {saved} 条新增[/green]")
                except Exception:
                    console.print(f"  [red]失败[/red]")
                    logging.exception("采集失败: %s / %s", name, mfr["short_code"])


@app.command()
def scheduler(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
) -> None:
    """启动定时调度器（常驻进程）。"""
    _setup_logging(verbose)
    from comm_tracker.scheduler.manager import SchedulerManager

    mgr = SchedulerManager()
    console.print("[bold green]启动调度器，按 Ctrl+C 停止[/bold green]")
    mgr.start()


@app.command()
def export(
    format: str = typer.Option("csv", "--format", "-f", help="导出格式: csv, json, excel"),
    manufacturer: Optional[str] = typer.Option(None, "--manufacturer", "-m", help="过滤厂家编码"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="过滤分类"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出文件路径"),
) -> None:
    """导出采集数据。"""
    db_url = get_database_url()
    init_db(db_url)

    from datetime import datetime as dt

    session = next(get_session(db_url))

    # 默认输出路径
    if not output:
        ext = {"csv": "csv", "json": "json", "excel": "xlsx"}[format]
        timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
        output = f"data/exports/comm_tracker_{timestamp}.{ext}"

    if format == "csv":
        from comm_tracker.exporters.csv_exporter import export_csv
        count = export_csv(session, output, manufacturer=manufacturer, category=category)
    elif format == "json":
        from comm_tracker.exporters.json_exporter import export_json
        count = export_json(session, output, manufacturer=manufacturer, category=category)
    elif format == "excel":
        from comm_tracker.exporters.excel_exporter import export_excel
        count = export_excel(session, output, manufacturer=manufacturer, category=category)
    else:
        console.print(f"[red]不支持的格式: {format}[/red]")
        raise typer.Exit(1)

    session.close()
    console.print(f"[green]已导出 {count} 条数据到 {output}[/green]")


@app.command()
def init() -> None:
    """初始化数据库和默认配置。"""
    db_url = get_database_url()
    init_db(db_url)

    # 初始化默认厂家
    session_gen = get_session(db_url)
    session = next(session_gen)
    repo = Repository(session)

    for mfr in load_manufacturers():
        repo.get_or_create_manufacturer(
            mfr["short_code"],
            mfr["name_zh"],
            mfr.get("name_en", ""),
            official_url=mfr.get("official_url", ""),
            news_url=mfr.get("news_url", ""),
        )
        console.print(f"  厂家已就绪: {mfr['name_zh']}")

    session.close()
    console.print("[bold green]初始化完成[/bold green]")


@app.command()
def stats() -> None:
    """查看采集统计和 LLM 用量。"""
    db_url = get_database_url()
    init_db(db_url)

    session = next(get_session(db_url))
    repo = Repository(session)

    # 文章总览
    total = repo.get_article_count()
    console.print(f"\n[bold]文章总数:[/bold] {total}")

    if total == 0:
        session.close()
        console.print("[dim]暂无数据[/dim]")
        return

    # 分类分布
    categories = repo.get_category_distribution()
    table = Table(title="分类分布")
    table.add_column("分类", style="cyan")
    table.add_column("数量", justify="right")
    table.add_column("占比", justify="right", style="green")
    for cat, cnt in sorted(categories.items(), key=lambda x: -x[1]):
        pct = f"{cnt / total * 100:.1f}%"
        table.add_row(cat, str(cnt), pct)
    console.print(table)

    # 数据源分布
    sources = repo.get_source_distribution()
    table = Table(title="数据源分布")
    table.add_column("采集器", style="cyan")
    table.add_column("数量", justify="right")
    for name, cnt in sorted(sources.items(), key=lambda x: -x[1]):
        table.add_row(name, str(cnt))
    console.print(table)

    # 厂家分布
    mfrs = repo.get_manufacturer_distribution()
    table = Table(title="厂家分布")
    table.add_column("厂家", style="cyan")
    table.add_column("数量", justify="right")
    for name, cnt in sorted(mfrs.items(), key=lambda x: -x[1]):
        table.add_row(name, str(cnt))
    console.print(table)

    # 摘要统计
    with_summary, _ = repo.get_summary_stats()
    console.print(f"\n[bold]摘要覆盖:[/bold] {with_summary}/{total} ({with_summary / total * 100:.1f}%)")

    # Token 用量
    today_usage = repo.get_token_usage_today()
    total_usage = repo.get_token_usage_total()
    if today_usage or total_usage:
        console.print(f"\n[bold]LLM Token 用量[/bold]")
        console.print(f"  历史累计: {total_usage:,} tokens")
        if today_usage:
            for op in ["classify", "summarize", "chat"]:
                tokens = today_usage.get(op, 0)
                requests = today_usage.get(f"{op}_requests", 0)
                if tokens > 0:
                    console.print(f"  今日 {op}: {tokens:,} tokens ({requests} 次调用)")

    # 采集器状态
    checkpoints = repo.get_checkpoints()
    if checkpoints:
        table = Table(title="采集器状态")
        table.add_column("采集器", style="cyan")
        table.add_column("厂家")
        table.add_column("最后采集时间")
        table.add_column("状态")
        table.add_column("采集数", justify="right")
        for cp in checkpoints:
            status_style = "green" if cp.status == "success" else "red"
            time_str = cp.last_collected_at.strftime("%Y-%m-%d %H:%M") if cp.last_collected_at else "-"
            table.add_row(
                cp.collector_name,
                cp.manufacturer_code,
                time_str,
                f"[{status_style}]{cp.status}[/{status_style}]",
                str(cp.items_collected),
            )
        console.print(table)

    session.close()


@app.command()
def report(
    period: str = typer.Option("weekly", "--period", "-p", help="报告周期: weekly, monthly"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出文件路径（默认打印到终端）"),
    format: str = typer.Option("text", "--format", "-f", help="输出格式: text, json"),
) -> None:
    """生成趋势分析报告。"""
    db_url = get_database_url()
    init_db(db_url)

    session = next(get_session(db_url))

    from comm_tracker.reports.trend import TrendAnalyzer

    analyzer = TrendAnalyzer(session)
    report_data = analyzer.generate_report(period=period)

    if format == "json":
        content = json.dumps(report_data, ensure_ascii=False, indent=2)
    else:
        content = analyzer.format_report_text(report_data)

    if output:
        from pathlib import Path
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(content, encoding="utf-8")
        console.print(f"[green]报告已保存到 {output}[/green]")
    else:
        console.print(content)

    session.close()


@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", "-p", help="端口号"),
) -> None:
    """启动数据可视化仪表盘。"""
    import subprocess
    import sys

    dashboard_path = "src/comm_tracker/dashboard/app.py"
    console.print(f"[bold green]启动仪表盘: http://localhost:{port}[/bold green]")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", dashboard_path, "--server.port", str(port)],
        cwd=".",
    )


if __name__ == "__main__":
    app()
