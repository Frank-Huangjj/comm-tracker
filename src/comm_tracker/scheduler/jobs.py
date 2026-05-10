"""定时任务定义。"""

from comm_tracker.config import load_sources

# 默认调度策略：采集器名 → (触发方式, 参数)
DEFAULT_SCHEDULES = {
    # 官网采集器：每 4 小时
    "huawei_news": {"trigger": "interval", "hours": 4},
    "zte_news": {"trigger": "interval", "hours": 4},
    "ericsson_news": {"trigger": "interval", "hours": 4},
    "nokia_news": {"trigger": "interval", "hours": 4},
    "samsung_news": {"trigger": "interval", "hours": 4},
    # 行业媒体：每 2 小时
    "c114_news": {"trigger": "interval", "hours": 2},
    # 社交平台：每 6 小时
    "wechat_sogou": {"trigger": "interval", "hours": 6},
    # 专利：每天凌晨 2 点
    "cnipa_patent": {"trigger": "cron", "hour": 2, "minute": 0},
    # 财务：每周一上午 9 点
    "cninfo_finance": {"trigger": "cron", "day_of_week": "mon", "hour": 9, "minute": 0},
}


def get_enabled_schedules() -> dict[str, dict]:
    """获取所有已启用数据源的调度配置。

    Returns:
        {collector_name: schedule_params}
    """
    sources = load_sources()
    schedules = {}

    for source in sources:
        if not source.get("enabled", False):
            continue
        name = source["name"]
        if name in DEFAULT_SCHEDULES:
            schedules[name] = DEFAULT_SCHEDULES[name]

    return schedules
