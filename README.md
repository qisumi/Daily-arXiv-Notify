# Daily arXiv Notify

`Daily arXiv Notify` 是一个用于生成每日 arXiv 论文摘要邮件的轻量级自动化项目。它会按配置抓取指定分类的新论文或更新论文，先做关键词规则过滤，再用 LLM 判断相关性并生成摘要，最后把结果渲染成 Markdown / HTML digest，通过 SMTP 发送到邮箱。

适合以下场景：

- 跟踪 `cs.AI`、`cs.LG` 等分类下与你研究方向相关的新论文
- 为个人或小团队生成每日论文晨报
- 用 SQLite 保留抓取、筛选、摘要和发送记录，便于回溯
- 通过 PM2 或其他调度器做日常定时运行

## 功能特性

- 基于 arXiv Atom API 增量抓取论文
- 支持多分类抓取和重叠时间窗口，降低漏抓风险
- 先做本地关键词规则过滤，再做 LLM 相关性判断
- 使用 LLM 为入选论文生成结构化摘要
- 自动生成 Markdown 和 HTML 两种 digest
- 通过 SMTP 发送邮件，可附带 Markdown 文件
- 使用 SQLite 缓存论文、评估结果、摘要结果和运行记录
- 支持 `dry-run`，便于先验证输出，不直接发信
- 内置 PM2 部署配置和 release 打包脚本

## 工作流程

1. 从 arXiv 抓取指定分类在时间窗口内的论文
2. 把论文元数据写入 SQLite
3. 用 `include_keywords` / `exclude_keywords` 做首轮规则过滤
4. 对通过规则过滤的论文调用 LLM 做相关性判断
5. 对最终入选的论文调用 LLM 生成结构化摘要
6. 输出 `data/digests/*.md` 和 `data/digests/*.html`
7. 通过 SMTP 发送 digest 邮件
8. 将运行状态、筛选结果、摘要结果和发送状态落库

## 当前实现范围

当前仓库已经具备一个可运行的 MVP：

- 配置加载：`config.toml` + `.env` + 进程环境变量覆盖
- 抓取：arXiv 分类抓取、时间窗口增量拉取、可选 revision 纳入
- 筛选：规则过滤 + LLM 分类，失败时有词法回退
- 摘要：LLM 摘要，失败时回退到基于 abstract 的简版摘要
- 渲染：Markdown 和 HTML digest
- 发送：SMTP 发信
- 存储：SQLite 持久化运行和产物信息
- 部署：PM2 配置、release 压缩包构建脚本

## 快速开始

### 1. 环境要求

- Python `3.10+`
- 可访问 arXiv API
- 可用的 SMTP 服务
- 可用的 OpenAI API Key，或兼容 OpenAI SDK 的接口地址

### 2. 安装依赖

```bash
git clone <your-repo-url>
cd Daily-arXiv-notify

python -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

### 3. 准备配置文件

复制示例配置：

```bash
cp config.example.toml config.toml
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item config.example.toml config.toml
Copy-Item .env.example .env
```

然后按需修改 `config.toml` 和 `.env`。

`config.toml` 示例：

```toml
timezone = "Asia/Shanghai"
schedule = "15 13 * * *"

[database]
sqlite_path = "data/app.db"

[arxiv]
categories = ["cs.AI", "cs.LG", "cs.GL"]
page_size = 100
include_revisions = false
max_pages = 5
overlap_hours = 36
request_delay_seconds = 3.0
max_retries = 3
retry_backoff_seconds = 15.0

[filtering]
include_keywords = ["time series"]
exclude_keywords = []
ai_target_keywords = ["time series"]

[llm]
provider = "openai"
base_url = "https://api.openai.com/v1"
endpoint = "/responses"
api_key = ""
classify_model = "gpt-5-mini"
summarize_model = "gpt-5.4"
output_language = "English"
reasoning_effort = "low"
timeout_seconds = 120

[digest]
max_papers = 12
section_strategy = "keyword"
output_dir = "data/digests"
attach_markdown = true

[email]
smtp_host = ""
smtp_port = 587
smtp_username = ""
smtp_password = ""
smtp_use_tls = true
from_name = "Daily arXiv Notify"
from_address = ""
recipients = []
```

`.env` 示例：

```env
OPENAI_API_KEY=your_openai_api_key
SMTP_HOST=smtp.example.com
SMTP_USERNAME=user@example.com
SMTP_PASSWORD=your_smtp_password
SMTP_FROM_ADDRESS=user@example.com
SMTP_RECIPIENTS=you@example.com,team@example.com
```

### 4. 先做一次 dry-run

```bash
daily-arxiv-notify run-once --config config.toml --dry-run
```

这一步会：

- 抓取 arXiv 数据
- 生成 digest 文件
- 写入 SQLite 运行记录
- 不实际发送邮件

### 5. 正式发送

```bash
daily-arxiv-notify run-once --config config.toml
```

开启详细日志：

```bash
daily-arxiv-notify run-once --config config.toml --verbose
```

CLI 帮助：

```bash
daily-arxiv-notify run-once --help
```

## 配置说明

### 配置优先级

敏感配置按以下优先级覆盖：

1. 进程环境变量
2. `.env`
3. `config.toml`

当前支持覆盖的字段：

- `OPENAI_API_KEY`
- `SMTP_HOST`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_ADDRESS`
- `SMTP_RECIPIENTS`

### 主要配置项

| 配置项 | 说明 |
| --- | --- |
| `arxiv.categories` | 需要跟踪的 arXiv 分类，例如 `cs.AI`、`cs.LG` |
| `arxiv.include_revisions` | 是否把更新版本论文也纳入时间窗口 |
| `arxiv.overlap_hours` | 与上次成功运行的重叠时间，降低漏抓风险 |
| `arxiv.request_delay_seconds` | 任意两次 arXiv 请求之间的最小间隔秒数 |
| `arxiv.max_retries` | arXiv 短暂失败（如 `429` / `5xx`）时的最大重试次数 |
| `arxiv.retry_backoff_seconds` | arXiv 重试退避基线秒数，后续按指数增长 |
| `filtering.include_keywords` | 首轮规则过滤必须命中的关键词 |
| `filtering.exclude_keywords` | 命中即排除的关键词 |
| `filtering.ai_target_keywords` | LLM 用来判断“是否相关”的目标关键词 |
| `llm.base_url` | OpenAI SDK 使用的基础地址，可换成兼容接口 |
| `llm.endpoint` | 当前支持 `/responses` 和 `/chat/completions` |
| `llm.classify_model` | 用于相关性判断的模型 |
| `llm.summarize_model` | 用于摘要生成的模型 |
| `llm.output_language` | `Why matched` 与 summary 内容的输出语言，默认 `English` |
| `digest.max_papers` | 每日 digest 最多收录论文数 |
| `digest.output_dir` | Markdown / HTML digest 输出目录 |
| `email.recipients` | 收件人列表 |

说明：

- `schedule` 当前主要作为配置记录字段存在，实际定时执行仍由 PM2、cron 或其他调度器负责。
- `digest.section_strategy` 在当前 MVP 中建议保持为 `keyword`。
- `llm.reasoning_effort` 已在配置中保留，但当前版本没有传入 OpenAI 请求参数。

## 输出结果

默认会在本地生成以下产物：

```text
data/
  app.db
  digests/
    digest-YYYY-MM-DD.md
    digest-YYYY-MM-DD.html
```

其中：

- `data/app.db` 保存运行记录、论文元数据、评估缓存、摘要缓存和 digest 发送状态
- `data/digests/*.md` 适合归档、审阅或作为邮件附件
- `data/digests/*.html` 用作邮件 HTML 正文

当前数据库包含以下核心表：

- `runs`
- `papers`
- `paper_evaluations`
- `paper_summaries`
- `digests`

## 定时运行

仓库已经提供 PM2 配置文件：`ecosystem.config.cjs`。

安装 PM2 后可以这样启动：

```bash
pm2 start ecosystem.config.cjs
pm2 save
```

也可以通过环境变量覆盖默认参数：

```bash
PM2_CRON="15 13 * * *" \
PYTHON_BIN="python" \
CONFIG_FILE="config.toml" \
pm2 start ecosystem.config.cjs
```

建议：

- 让 `PM2_CRON` 与 `config.toml` 中的 `schedule` 保持一致，避免配置和实际运行时间不一致
- 首次部署先执行一次 `--dry-run`
- 检查 `logs/pm2-out.log` 和 `logs/pm2-error.log`

## 构建发布包

项目提供了一个 release 打包脚本，用来生成可部署的 zip 包。

Python 方式：

```bash
python scripts/build_release.py --clean --exclude-local-config
```

PowerShell 方式：

```powershell
.\scripts\build_release.ps1 -Clean -ExcludeLocalConfig
```

默认输出到 `dist/` 目录，压缩包内包含：

- `app/`
- `scripts/`
- `docs/`
- `pyproject.toml`
- `ecosystem.config.cjs`
- `config.example.toml`
- `.env.example`

如果不加 `--exclude-local-config`，还会把本地 `config.toml` 和 `.env` 一起打进去。

## 测试

当前仓库包含基础测试，覆盖：

- 配置加载和环境变量优先级
- SQLite 基本落库逻辑
- Markdown renderer 输出字段
- OpenAI client 在 `/responses` 和 `/chat/completions` 两种模式下的切换

本地执行：

```bash
python -m pytest -q
```

## 项目结构

```text
.
├─ app/
│  ├─ clients/      # arXiv / OpenAI / SMTP 客户端
│  ├─ render/       # Markdown / HTML 渲染
│  ├─ services/     # ingest / filter / summarize / digest / delivery
│  ├─ cli.py        # CLI 入口
│  ├─ config.py     # 配置加载与校验
│  ├─ db.py         # SQLite 持久化
│  ├─ models.py     # 数据模型
│  └─ pipeline.py   # 主流程编排
├─ scripts/         # 运行与打包脚本
├─ tests/           # 基础测试
├─ docs/            # 规划文档
├─ config.example.toml
├─ .env.example
└─ ecosystem.config.cjs
```

## 已知限制

- 摘要和相关性判断目前只基于 title + abstract，不读取 PDF 全文
- LLM prompt 还写在代码里，没有独立版本化管理
- OpenAI / SMTP 目前还没有自动重试与退避
- 没有提供 backfill、replay、告警、监控、Docker 部署
- `section_strategy` 等部分配置项已经预留，但还没有完整发挥作用

## License

MIT
