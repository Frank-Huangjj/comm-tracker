# comm-tracker

通信设备厂家进展跟踪数据采集工具。自动采集三大运营商（移动、电信、联通）、五大设备商（华为、中兴、爱立信、诺基亚、三星）及国际标准组织（GSMA、TM Forum）的新闻动态、行业资讯、专利和财务数据，通过 LLM 智能分类和摘要生成，输出趋势分析报告。

## 功能概览

- **多源数据采集** — 官网新闻、C114 行业媒体、微信搜狗、CNIPA 专利、巨潮财经（超过 14 个采集器）
- **智能处理管线** — HTML 清洗 → 去重 → 关键词/LLM 增强分类 → LLM 摘要生成
- **Token 用量追踪** — LLM 调用持久化到数据库，每日预算管控
- **摘要自动回填** — 重复采集时自动将 LLM 生成的摘要回写到已有记录
- **趋势分析报告** — 周度/月度自动生成，含厂家活跃度、分类分布、白皮书专属技术雷达（热点核心词汇）
- **数据可视化** — Streamlit 仪表盘，支持全中文化与厂商简称
- **灵活导出** — CSV / JSON / Excel 多格式

## 快速开始

### 1. 安装

```bash
cd comm-tracker
pip install -e ".[dev]"
playwright install chromium   # 仅部分采集器需要
```

### 2. 配置 LLM（可选）

LLM 功能用于增强分类和摘要生成。不配置时自动退回纯关键词分类模式。

```bash
export OPENAI_API_KEY="your-deepseek-api-key"
```

默认使用 DeepSeek，可通过环境变量切换：

```bash
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
```

配置文件在 `config/settings.yaml`，可调整模型、每日 token 预算等。

### 3. 初始化

```bash
comm-tracker init
```

创建数据库表和默认厂家记录。

### 4. 采集数据

```bash
# 采集所有已启用的数据源
comm-tracker collect

# 只采集华为相关新闻
comm-tracker collect -s huawei_news -m huawei

# 只采集 C114 行业媒体
comm-tracker collect -s c114_news

# 带详细日志
comm-tracker collect -v
```

### 5. 查看统计

```bash
comm-tracker stats
```

输出文章总数、分类分布、厂家活跃度、数据源分布、LLM token 用量、采集器状态。

### 6. 生成报告

```bash
# 周报（默认）
comm-tracker report

# 月报
comm-tracker report -p monthly

# 导出 JSON 格式
comm-tracker report -f json -o report.json
```

### 7. 导出数据

```bash
# CSV 格式
comm-tracker export -f csv

# Excel 格式，只导出华为数据
comm-tracker export -f excel -m huawei

# 指定输出路径
comm-tracker export -f json -o data/exports/huawei.json -m huawei
```

### 8. 可视化仪表盘

```bash
comm-tracker dashboard
# 或指定端口
comm-tracker dashboard -p 8080
```

浏览器打开 `http://localhost:8501` 查看交互式仪表盘。

### 9. 定时调度

```bash
comm-tracker scheduler
```

启动常驻进程，按 `config/settings.yaml` 中的调度策略自动采集。

## 项目结构

```
comm-tracker/
├── config/
│   ├── settings.yaml          # 全局设置（数据库、LLM、调度）
│   ├── manufacturers.yaml     # 厂家定义（华为/中兴/爱立信/诺基亚/三星）
│   └── sources.yaml           # 数据源配置（10 个采集器）
├── src/comm_tracker/
│   ├── cli.py                 # CLI 命令入口（9 个命令）
│   ├── config.py              # 配置管理
│   ├── db.py                  # 数据库引擎与会话
│   ├── repository.py          # 数据存储仓库（CRUD + 统计查询）
│   ├── collectors/            # 采集器
│   │   ├── base.py            # BaseCollector / ParsedItem / RawItem
│   │   ├── registry.py        # 自动发现与注册
│   │   ├── official/          # 官网采集器（华为/中兴/爱立信/诺基亚/三星）
│   │   ├── news/              # 行业媒体采集器（C114 新闻/论坛）
│   │   ├── social/            # 社交平台采集器（微信搜狗）
│   │   ├── patents/           # 专利采集器（CNIPA）
│   │   ├── finance/           # 财经采集器（巨潮资讯）
│   │   └── middleware/        # 中间件（限速/重试/UA 轮换）
│   ├── pipeline/              # 数据处理管线
│   │   ├── processor.py       # 管线编排器
│   │   ├── cleaner.py         # HTML 清洗
│   │   ├── deduplicator.py    # 标题相似度去重
│   │   ├── classifier.py      # 关键词 + LLM 增强分类
│   │   └── summarizer.py      # LLM 摘要生成
│   ├── llm/
│   │   └── client.py          # DeepSeek LLM 客户端（token 预算管控）
│   ├── models/                # 数据模型
│   │   ├── article.py         # 文章（含 LLM 摘要）
│   │   ├── manufacturer.py    # 厂家
│   │   ├── token_usage.py     # Token 用量追踪
│   │   ├── checkpoint.py      # 采集检查点
│   │   └── ...                # 产品/专利/财务模型
│   ├── reports/
│   │   └── trend.py           # 趋势分析报告生成
│   ├── dashboard/
│   │   └── app.py             # Streamlit 可视化仪表盘
│   ├── exporters/             # 数据导出（CSV/JSON/Excel）
│   ├── scheduler/             # APScheduler 定时调度
│   └── utils/
│       └── http_client.py     # HTTP 客户端（httpx + Playwright）
├── tests/                     # 单元测试
├── data/
│   ├── db/                    # SQLite 数据库
│   └── exports/               # 导出文件输出目录
└── whitepaper_data/           # 白皮书支撑数据独立存储区
    ├── tables/                # 白皮书中硬编码的表格数据（CSV等）
    ├── trends/                # 按厂商分离的行业动态和追踪归档（Markdown）
    └── sources_registry.csv   # 所有数据、图表、动态的原始出处溯源表
```

## 数据处理管线

采集到的原始数据经过 4 级管线处理：

```
RawItem → Cleaner → Deduplicator → Classifier → Summarizer → Article
            │            │              │              │
            │            │              │              └ LLM 生成 80-150 字摘要
            │            │              └ 关键词优先，未命中时 LLM 分类
            │            └ Jaccard + SequenceMatcher 去重
            └ HTML → 纯文本，去除噪声标签
```

- `enable_llm=False`（默认）— 只运行 Cleaner + Deduplicator + 关键词分类
- `enable_llm=True` — 额外启用 LLM 增强分类 + 摘要生成，共享 LLM client 控制预算

## 已注册采集器

| 名称 | 类型 | 厂家 | 状态 |
|------|------|------|------|
| huawei_news | 官网 | 华为 | 启用 |
| zte_news | 官网 | 中兴 | 启用 |
| ericsson_news | 官网 | 爱立信 | 启用 |
| nokia_news | 官网 | 诺基亚 | 启用 |
| samsung_news | 官网 | 三星 | 启用 |
| china_mobile | 官网 | 中国移动 | 启用 |
| china_telecom | 官网 | 中国电信 | 启用 |
| china_unicom | 官网 | 中国联通 | 启用 |
| gsma | 官网 | GSMA | 启用 |
| tmforum | 官网 | TM Forum | 启用 |
| c114_news | 行业媒体 | 全部 | 启用 |
| c114_bbs | 行业论坛 | 全部 | 禁用（域名已失效） |
| wechat_sogou | 微信搜狗 | 全部 | 禁用 |
| cnipa_patent | 专利 | 全部 | 禁用 |
| cninfo_finance | 财经 | 中兴 | 禁用 |

在 `config/sources.yaml` 中将 `enabled` 改为 `true` 启用对应采集器。

## 文章分类

| 分类 | 说明 |
|------|------|
| product_release | 产品发布、新品上市 |
| tech_dynamic | 技术突破、研发进展、标准动态 |
| market_finance | 营收财报、市场合作、中标签约 |
| patent_filing | 专利申请、知识产权 |
| standard_contribution | 标准化提案、3GPP 贡献 |
| industry_news | 行业综合新闻（默认分类） |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | LLM API Key | 无（禁用 LLM 功能） |
| `OPENAI_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///data/db/comm_tracker.db` |

## 测试

```bash
pytest tests/ -v
```

## 项目开发总结

### 实现阶段

| 阶段 | 内容 | 关键文件 |
|------|------|----------|
| 1.1 | ParsedItem 添加 summary 字段 | `collectors/base.py`, `models/article.py` |
| 1.2 | Pipeline 基础架构 | `pipeline/cleaner.py`, `deduplicator.py` |
| 1.3 | Summarizer 管线组件 | `pipeline/summarizer.py`, Pipeline 异步化 |
| 1.4 | LLM 增强分类器 | `pipeline/classifier.py` (LLMClassifier) |
| 1.5 | 集成 LLM 到 Pipeline | `pipeline/processor.py` (enable_llm 参数) |
| 1.6 | Token 用量持久化 | `models/token_usage.py`, LLMClient 集成 |
| 1.7 | CLI stats 命令 | `cli.py` stats/report/dashboard |
| 2 | 趋势报告生成 | `reports/trend.py` |
| 3.1 | C114 行业媒体采集器 | `collectors/news/c114_news.py` |
| 3.2 | C114 论坛采集器 | `collectors/news/c114_bbs.py`（域名已失效） |
| 3.3 | 微信搜狗采集器 | `collectors/social/wechat_sogou.py` |
| 3.4 | CNIPA 专利采集器 | `collectors/patents/cnipa_patent.py` |
| 3.5 | 巨潮财经采集器 | `collectors/finance/cninfo_finance.py` |
| 4 | Streamlit 可视化仪表盘 | `dashboard/app.py` |
| 4.1 | 厂家简称与分类中文化 | `dashboard/app.py`, `reports/trend.py` |
| 4.2 | 白皮书专属核心词库提取 | `reports/trend.py` |

### 修复记录

| 问题 | 原因 | 修复 |
|------|------|------|
| C114 采集乱码 | C114 使用 GB2312 编码，httpx 默认 UTF-8 | `HttpClient.get_text()` 增加 `encoding` 参数 |
| 三星 RSS 解析崩溃 | dateutil 返回带时区 datetime，与 naive datetime 比较 | 统一转为 naive datetime |
| 已有文章不回填摘要 | URL 去重后直接跳过，Pipeline 产物丢弃 | `save_article` 检测并回填缺失字段 |
| 运营商官网 SSL 握手失败 | 老旧 SSL 证书 / 反爬拦截 | `HttpClient` 禁用 SSL 严格验证，加入 C114 智能兜底 |
| LLM 调用崩溃 TypeError | `httpx` (0.28+) 导致 `proxies` 参数被废弃，`openai` 旧版不兼容 | 升级 `openai` 包至最新兼容版 |
| `.env` 变量无法被读取 | 未显式导入并加载 `python-dotenv` | 在 `config.py` 增加 `load_dotenv()` |
| 英文介词混淆热点关键词 | 通用分词把 "to/for" 认作热点 | 替换为 **白皮书专属领域词库** 精准提取 |

### 运行数据

- **支持厂商**: 10 家（含三大运营商、五大设备商、GSMA/TM Forum）
- **架构升级**: 支持 Dashboard 全量中文化、厂商品牌简称及白皮书词库雷达
- **CLI 命令**: collect, sources, manufacturers, init, stats, report, export, dashboard, scheduler
