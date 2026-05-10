"""Streamlit 数据可视化仪表盘。

启动方式: streamlit run src/comm_tracker/dashboard/app.py
"""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from comm_tracker.config import get_database_url
from comm_tracker.db import get_engine, init_db
from comm_tracker.repository import Repository
from comm_tracker.reports.trend import TrendAnalyzer

from sqlmodel import Session

st.set_page_config(
    page_title="通信行业进展追踪",
    page_icon="📡",
    layout="wide",
)


@st.cache_resource
def get_repo() -> Repository:
    """获取数据库 Repository（缓存）。"""
    db_url = get_database_url()
    init_db(db_url)
    engine = get_engine(db_url)
    session = Session(engine)
    return Repository(session)


@st.cache_data(ttl=300)
def load_report(period: str) -> dict:
    """加载趋势报告（缓存 5 分钟）。"""
    repo = get_repo()
    analyzer = TrendAnalyzer(repo.session)
    return analyzer.generate_report(period=period)


def main():
    st.title("📡 通信行业进展追踪仪表盘")

    # 侧边栏
    st.sidebar.header("设置")
    period = st.sidebar.radio(
        "报告周期",
        options=["weekly", "monthly"],
        format_func=lambda x: "周报" if x == "weekly" else "月报",
    )
    auto_refresh = st.sidebar.checkbox("自动刷新 (5 分钟)", value=False)
    if auto_refresh:
        st.empty()

    # 加载数据
    report = load_report(period)
    overview = report["overview"]

    if overview["total_articles"] == 0:
        st.warning("暂无数据，请先执行采集。")
        return

    # === 总览指标 ===
    st.header("总览")
    st.caption(f"报告期间: {report['start_date']} ~ {report['end_date']}")
    
    repo = get_repo()
    today_usage = repo.get_token_usage_today()
    today_total = sum(v for k, v in today_usage.items() if "_" not in k)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("文章总数", overview["total_articles"])
    with col2:
        change = overview["change_percent"]
        st.metric(
            "环比变化",
            f"{change:+.1f}%",
            delta_color="normal" if change >= 0 else "inverse",
        )
    with col3:
        st.metric("摘要覆盖率", f"{overview['summary_coverage']:.1f}%")
    with col4:
        st.metric("今日 Token 用量", f"{today_total:,}")

    st.divider()

    # === 图表区域 ===
    col_left, col_right = st.columns(2)

    # 厂家活跃度 - 柱状图
    with col_left:
        st.subheader("厂家活跃度")
        if report["manufacturers"]:
            mfr_df = pd.DataFrame(
                list(report["manufacturers"].items()), columns=["厂家", "文章数"]
            )
            fig = px.bar(mfr_df, x="厂家", y="文章数", color="文章数", color_continuous_scale="Blues")
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无厂家数据")

    # 分类分布 - 饼图
    with col_right:
        st.subheader("分类分布")
        if report["categories"]:
            cat_df = pd.DataFrame(
                list(report["categories"].items()), columns=["分类", "数量"]
            )
            fig = px.pie(cat_df, values="数量", names="分类", hole=0.4)
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无分类数据")

    # 日趋势 - 折线图
    st.subheader("日采集趋势")
    if report["daily_trend"]:
        trend_df = pd.DataFrame(
            list(report["daily_trend"].items()), columns=["日期", "文章数"]
        )
        trend_df = trend_df.sort_values("日期")
        fig = px.area(trend_df, x="日期", y="文章数", markers=True)
        fig.update_traces(line=dict(width=2))
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暂无趋势数据")

    # 热点关键词
    st.subheader("热点关键词 TOP 15")
    if report["hot_keywords"]:
        kw_df = pd.DataFrame(
            report["hot_keywords"][:15], columns=["关键词", "频次"]
        )
        fig = px.bar(kw_df, x="频次", y="关键词", orientation="h", color="频次",
                     color_continuous_scale="Oranges")
        fig.update_layout(showlegend=False, height=300, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    # === 最新高价值动态 ===
    st.divider()
    st.subheader("💡 最新高价值动态 (白皮书可用素材)")
    if report.get("latest_articles"):
        df_latest = pd.DataFrame(report["latest_articles"])
        st.dataframe(
            df_latest,
            use_container_width=True,
            hide_index=True,
            column_config={
                "链接": st.column_config.LinkColumn("原文链接"),
                "摘要": st.column_config.TextColumn("摘要", width="large")
            }
        )
    else:
        st.info("暂无最新动态")

    # 页脚
    st.divider()
    st.caption("通信设备厂家进展跟踪数据采集工具 | 数据自动更新")


if __name__ == "__main__":
    main()
