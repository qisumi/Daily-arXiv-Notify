# Daily arXiv Notify

[English](README.md)

`Daily arXiv Notify` 是一个用于生成每日 arXiv 论文摘要邮件的轻量级自动化项目。它会按配置增量抓取指定分类下的新论文或更新论文，先做规则关键词过滤，再用 LLM 判断相关性并生成结构化摘要；对于最终入选的论文，还可以下载 PDF，通过 Files API 交给模型做更深入的分析，然后输出 Markdown / HTML digest，并通过 SMTP 发送邮件。

## 适用场景

- 跟踪 `cs.AI`、`cs.LG` 等分类下与你研究方向相关的新论文。
- 为个人研究者或小团队生成每日论文阅读 shortlist。
- 使用 SQLite 保存抓取、筛选、摘要、详细解析和发送记录，便于审计与回溯。
- 通过 PM2、cron 或其他调度器进行定时运行。

## 功能特性

- 基于 arXiv Atom API 的增量抓取。
- 支持多分类抓取和重叠时间窗口，降低漏抓概率。
- 在模型调用前先做本地 include / exclude 关键词规则过滤。
- 对通过规则过滤的论文使用 LLM 做相关性判断。
- 为入选论文生成结构化 abstract 级摘要。
- 可选下载入选论文 PDF，并通过 Files API 做基于 PDF 的深度分析。
- 自动生成 Markdown 和 HTML 两种 digest。
- 通过 SMTP 发送邮件，并可附加 Markdown 文件。
- 使用 SQLite 缓存评估结果、摘要结果、详细解析结果、运行记录和 digest 元数据。
- 将提示词模板统一放在 `app/prompts/` 中管理，不再混在 client 代码中。
- 支持 `dry-run`，便于先验证输出而不实际发信。

## 工作流程

1. 从配置的 arXiv 分类抓取当前时间窗口内的论文。
2. 将论文元数据写入 SQLite。
3. 用本地 `include_keywords` / `exclude_keywords` 做规则过滤。
4. 对通过规则过滤的论文调用 LLM 做相关性判断。
5. 为入选论文生成结构化摘要。
6. 可选下载入选论文的 PDF。
7. 通过 Files API 上传 PDF，并请求更丰富的结构化深度分析。
8. 将 digest 渲染为 `Markdown` 和 `HTML`。
9. 通过 SMTP 发送 digest。
10. 将运行状态、筛选结果、摘要结果、详细解析结果和发送元数据落库。

## 当前实现范围

当前仓库已经可以跑通完整的每日工作流：

- 使用 `config.toml`、`.env` 和进程环境变量做配置加载。
- 支持带重叠时间窗口的 arXiv 分类抓取，以及可选 revision 纳入。
- 规则过滤 + LLM 分类，分类失败时有词法回退。
- 基于标题和摘要生成结构化摘要。
- 可选下载 PDF、通过 Files API 上传，并生成更丰富的论文详细解析。
- 生成 Markdown 和 HTML digest。
- 通过 SMTP 发送邮件。
- 使用 SQLite 持久化运行记录和产物信息。
- 从文件中加载并管理外部 prompt 模板。
- 包含基础自动化测试，覆盖配置、数据库、渲染、prompt loader、OpenAI client、detail service 回退路径和 arXiv client 工具逻辑。

## 快速开始

### 1. 环境要求

- Python `3.10+`
- 可访问 arXiv API
- 可用的 SMTP 服务
- 一个可用的 OpenAI 兼容接口和 API Key

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
max_rate_limit_retries = 6
retry_backoff_seconds = 15.0
min_rate_limit_delay_seconds = 60.0

[filtering]
include_keywords = ["time series"]
exclude_keywords = []
ai_target_keywords = ["time series"]

[llm]
provider = "openai"
base_url = "https://api.openai.com/v1"
endpoint = "/responses"
# legacy chat endpoint is also supported:
# endpoint = "/chat/completions"
api_key = ""
classify_model = "gpt-5-mini"
summarize_model = "gpt-5.4"
detail_model = "gpt-5.4"
output_language = "Chinese"
reasoning_effort = "high"
detail_reasoning_effort = "high"
timeout_seconds = 120

[pdf_enrichment]
enabled = true
download_dir = "data/pdfs"
max_file_size_mb = 40
timeout_seconds = 180
max_retries = 2
retry_backoff_seconds = 10.0
upload_expires_after_hours = 24

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

### 4. 先做一次 Dry Run

```bash
daily-arxiv-notify run-once --config config.toml --dry-run
```

这一步会：

- 抓取 arXiv 数据
- 生成 digest 文件
- 将运行记录写入 SQLite
- 不实际发送邮件

### 5. 正式发送

```bash
daily-arxiv-notify run-once --config config.toml
```

详细日志模式：

```bash
daily-arxiv-notify run-once --config config.toml --verbose
```

CLI 帮助：

```bash
daily-arxiv-notify run-once --help
```

## 配置说明

### 配置优先级

敏感配置的覆盖优先级如下：

1. 进程环境变量
2. `.env`
3. `config.toml`

当前支持覆盖的敏感字段：

- `OPENAI_API_KEY`
- `SMTP_HOST`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_ADDRESS`
- `SMTP_RECIPIENTS`

### 主要配置项

| 配置项 | 说明 |
| --- | --- |
| `arxiv.categories` | 需要跟踪的 arXiv 分类，例如 `cs.AI`、`cs.LG`。 |
| `arxiv.include_revisions` | 是否将论文更新版本也纳入时间窗口。 |
| `arxiv.overlap_hours` | 与上次成功运行的重叠时间，用于降低漏抓风险。 |
| `arxiv.request_delay_seconds` | 两次 arXiv 请求之间的最小间隔秒数。 |
| `arxiv.max_retries` | arXiv 短暂失败时的最大重试次数。 |
| `arxiv.max_rate_limit_retries` | 针对 HTTP 429 限流额外提供的重试次数。 |
| `arxiv.retry_backoff_seconds` | arXiv 请求的重试退避基线秒数。 |
| `arxiv.min_rate_limit_delay_seconds` | 当 arXiv 返回 HTTP 429 且未提供 `Retry-After` 时使用的保守等待秒数。 |
| `filtering.include_keywords` | 首轮规则过滤要求命中的关键词。 |
| `filtering.exclude_keywords` | 命中后立即排除论文的关键词。 |
| `filtering.ai_target_keywords` | LLM 用于判断相关性的目标关键词。 |
| `llm.base_url` | OpenAI 兼容 SDK 的基础地址。 |
| `llm.endpoint` | 当前支持 `/responses` 和 `/chat/completions`。 |
| `llm.classify_model` | 用于相关性判断的模型。 |
| `llm.summarize_model` | 用于结构化摘要生成的模型。 |
| `llm.detail_model` | 用于基于 PDF 生成详细解析的模型。 |
| `llm.output_language` | 摘要与深度解析的输出语言。 |
| `llm.reasoning_effort` | 通用推理强度设置，也是 detail 推理的回退值。 |
| `llm.detail_reasoning_effort` | 专用于 PDF 深度分析的推理强度。 |
| `pdf_enrichment.enabled` | 是否下载 shortlist 论文 PDF 并做深度分析。 |
| `pdf_enrichment.download_dir` | PDF 本地缓存目录。 |
| `pdf_enrichment.max_file_size_mb` | 单篇论文允许下载的最大 PDF 体积。 |
| `pdf_enrichment.timeout_seconds` | PDF 下载请求的超时时间。 |
| `pdf_enrichment.upload_expires_after_hours` | Files API 上传文件的过期时间。 |
| `digest.max_papers` | 每日 digest 最多收录的论文数。 |
| `digest.output_dir` | Markdown 与 HTML digest 的输出目录。 |
| `email.recipients` | 最终邮件的收件人列表。 |

说明：

- `schedule` 当前主要作为记录性配置字段存在，实际定时仍由 PM2、cron 或其他外部调度器负责。
- 当前实现中，`digest.section_strategy` 实际上仍以 `keyword` 策略为主。
- 当 `pdf_enrichment.enabled = true` 时，`llm.endpoint` 必须使用 `/responses`。
- 提示词模板已经抽离到 `app/prompts/`，但 prompt version 的命名仍主要由 service 层常量控制。

## 输出结果

默认会生成以下产物：

```text
data/
  app.db
  pdfs/
    *.pdf
  digests/
    digest-YYYY-MM-DD.md
    digest-YYYY-MM-DD.html
```

- `data/app.db`：保存运行记录、论文元数据、评估缓存、摘要缓存、详细解析缓存和发送状态
- `data/pdfs/`：保存 shortlist 论文下载下来的 PDF 缓存
- `data/digests/*.md`：适合归档，也可以作为邮件附件
- `data/digests/*.html`：用于邮件 HTML 正文

当前数据库核心表包括：

- `runs`
- `papers`
- `paper_evaluations`
- `paper_summaries`
- `paper_details`
- `digests`

## 提示词管理

提示词模板统一存放在 `app/prompts/` 下，并通过共享 loader 进行渲染。当前包括：

- `keyword_filter_system.txt`
- `keyword_filter_user.txt`
- `paper_summary_system.txt`
- `paper_summary_user.txt`
- `paper_detail_system.txt`
- `paper_detail_user.txt`

这样可以避免将 prompt 文案直接写死在 OpenAI client 中，也方便后续单独迭代提示词。

## 论文详细解析

对于 shortlist 论文，可选的 PDF enrichment 路径会请求模型输出更丰富的 `PaperDetailResult`。当前结构更偏向“帮助你判断这篇论文是否值得读”，而不只是生成一个更长的摘要：

- `headline`
- `contribution_summary`
- `problem_and_context`
- `research_question`
- `method_overview`
- `novelty_and_positioning`
- `experimental_setup`
- `key_findings`
- `evidence_and_credibility`
- `strengths`
- `limitations`
- `practical_implications`
- `open_questions`
- `relevance_to_keywords`
- `reading_guide`

提示词会明确要求模型区分“论文声称了什么”和“证据是否足够有说服力”，避免编造 PDF 未支持的细节，并在依据不足时明确承认不确定性。

## 定时运行

仓库内置了 `ecosystem.config.cjs`，可用于基于 PM2 的定时运行。

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

- 让 `PM2_CRON` 与 `config.toml` 中的配置保持一致
- 首次上线前先执行一次 `--dry-run`
- 检查 `logs/pm2-out.log` 和 `logs/pm2-error.log`

## 构建发布包

```bash
python scripts/build_release.py --clean --exclude-local-config
```

PowerShell:

```powershell
.\scripts\build_release.ps1 -Clean -ExcludeLocalConfig
```

压缩包默认输出到 `dist/`，包含：

- `app/`
- `scripts/`
- `docs/`
- `pyproject.toml`
- `ecosystem.config.cjs`
- `config.example.toml`
- `.env.example`

如果不加 `--exclude-local-config`，本地 `config.toml` 和 `.env` 也会被一起打进压缩包。

## 测试

本地运行完整测试：

```bash
python -m pytest -q
```

当前测试覆盖：

- 配置加载与校验
- 数据库存储与缓存逻辑
- Markdown / HTML 渲染
- prompt 加载
- OpenAI client 的接口模式切换和 Files API 深度分析链路
- detail service 的回退逻辑
- arXiv client 的请求节流与 PDF 下载校验

## 项目结构

```text
.
├─ app/
│  ├─ clients/      # arXiv / OpenAI / SMTP clients
│  ├─ prompts/      # external LLM prompt templates
│  ├─ render/       # Markdown / HTML rendering
│  ├─ services/     # ingest / filter / summarize / detail / digest / delivery
│  ├─ cli.py        # CLI entrypoint
│  ├─ config.py     # config loading and validation
│  ├─ db.py         # SQLite persistence
│  ├─ models.py     # data models
│  └─ pipeline.py   # pipeline orchestration
├─ scripts/
├─ tests/
├─ docs/
├─ config.example.toml
├─ .env.example
└─ ecosystem.config.cjs
```

## 已知限制

- OpenAI / SMTP 的投递重试与退避机制还不够完整。
- prompt 模板虽然已经外置，但 prompt version 仍主要由代码控制，而不是完全独立管理。
- 目前还没有内置 backfill、replay、告警、监控或 Docker 部署流程。
- `section_strategy` 虽然已经预留为配置项，但更丰富的分组策略还没有完全实现。

## License

MIT
