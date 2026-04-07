# Daily arXiv Notify

[简体中文](README_ZH.md)

`Daily arXiv Notify` is a lightweight automation project for generating a daily arXiv digest email. It incrementally fetches papers from selected arXiv categories, applies rule-based keyword filtering, uses an LLM for relevance classification and structured summarization, optionally downloads shortlisted PDFs for deeper analysis through the Files API, renders the result into Markdown and HTML, and sends the digest through SMTP.

## Use Cases

- Track new papers in categories such as `cs.AI`, `cs.LG`, and other fields relevant to your research.
- Generate a daily reading shortlist for an individual researcher or a small team.
- Keep SQLite records for fetched papers, filtering decisions, summaries, detailed analyses, and delivery history.
- Run the pipeline on a schedule with PM2, cron, or another process manager.

## Features

- Incremental arXiv fetching through the Atom API.
- Multi-category ingestion with overlap windows to reduce missed papers.
- Rule-based include/exclude keyword filtering before any model call.
- LLM-based relevance classification for papers that pass the rule filter.
- Structured abstract-level summaries for shortlisted papers.
- Optional PDF download and deeper PDF-grounded analysis via the Files API.
- Markdown and HTML digest generation.
- SMTP delivery with optional Markdown attachment.
- SQLite caching for evaluations, summaries, details, runs, and digest metadata.
- External prompt templates under `app/prompts/`, instead of mixing prompt text into client code.
- `dry-run` mode for validating output without sending mail.

## Workflow

1. Fetch papers from configured arXiv categories inside the current time window.
2. Persist paper metadata to SQLite.
3. Apply local `include_keywords` / `exclude_keywords`.
4. Call the LLM to classify relevance for papers that survive the rule filter.
5. Generate a structured summary for shortlisted papers.
6. Optionally download the shortlisted paper PDFs.
7. Upload PDFs through the Files API and request a richer structured analysis.
8. Render the digest into `Markdown` and `HTML`.
9. Send the digest through SMTP.
10. Persist run state, evaluation results, summaries, detailed analyses, and delivery metadata.

## Current Scope

The repository already supports an end-to-end daily workflow:

- Config loading through `config.toml`, `.env`, and process environment overrides.
- arXiv category fetching with overlap windows and optional revision handling.
- Rule filter plus LLM classifier, with lexical fallback if classification fails.
- Structured summary generation from title and abstract.
- Optional PDF download, Files API upload, and richer paper detail analysis.
- Markdown and HTML digest rendering.
- SMTP delivery.
- SQLite persistence for runs and artifacts.
- External prompt templates loaded from files.
- Basic automated tests for config, DB, renderer, prompt loading, OpenAI client behavior, detail service fallback, and arXiv client utilities.

## Quick Start

### 1. Requirements

- Python `3.10+`
- Access to the arXiv API
- An SMTP service
- A working OpenAI-compatible API endpoint and API key

### 2. Install

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

### 3. Prepare Config

```bash
cp config.example.toml config.toml
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item config.example.toml config.toml
Copy-Item .env.example .env
```

Then edit `config.toml` and `.env` to fit your environment.

Example `config.toml`:

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

Example `.env`:

```env
OPENAI_API_KEY=your_openai_api_key
SMTP_HOST=smtp.example.com
SMTP_USERNAME=user@example.com
SMTP_PASSWORD=your_smtp_password
SMTP_FROM_ADDRESS=user@example.com
SMTP_RECIPIENTS=you@example.com,team@example.com
```

### 4. Dry Run

```bash
daily-arxiv-notify run-once --config config.toml --dry-run
```

This will:

- fetch arXiv data
- generate digest files
- write run records to SQLite
- skip actual email delivery

### 5. Send for Real

```bash
daily-arxiv-notify run-once --config config.toml
```

Verbose mode:

```bash
daily-arxiv-notify run-once --config config.toml --verbose
```

CLI help:

```bash
daily-arxiv-notify run-once --help
```

## Configuration

### Priority

Sensitive values are overridden in this order:

1. process environment variables
2. `.env`
3. `config.toml`

Supported secret overrides:

- `OPENAI_API_KEY`
- `SMTP_HOST`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_ADDRESS`
- `SMTP_RECIPIENTS`

### Main Settings

| Key | Description |
| --- | --- |
| `arxiv.categories` | arXiv categories to monitor, such as `cs.AI` and `cs.LG`. |
| `arxiv.include_revisions` | Whether revised versions should also enter the time window. |
| `arxiv.overlap_hours` | Overlap with the previous successful run to reduce misses. |
| `arxiv.request_delay_seconds` | Minimum delay between arXiv requests. |
| `arxiv.max_retries` | Retry count for transient arXiv failures. |
| `arxiv.max_rate_limit_retries` | Extra retry budget used specifically for HTTP 429 rate limiting. |
| `arxiv.retry_backoff_seconds` | Base retry backoff for arXiv requests. |
| `arxiv.min_rate_limit_delay_seconds` | Conservative fallback delay when arXiv returns HTTP 429 without `Retry-After`. |
| `filtering.include_keywords` | Required keywords for the first rule-based pass. |
| `filtering.exclude_keywords` | Keywords that immediately exclude a paper. |
| `filtering.ai_target_keywords` | Keywords used by the LLM to judge relevance. |
| `llm.base_url` | Base URL for the OpenAI-compatible SDK client. |
| `llm.endpoint` | Supported endpoints are `/responses` and `/chat/completions`. |
| `llm.classify_model` | Model used for relevance classification. |
| `llm.summarize_model` | Model used for structured summaries. |
| `llm.detail_model` | Model used for PDF-grounded detailed analysis. |
| `llm.output_language` | Output language for summaries and deep analysis. |
| `llm.reasoning_effort` | General reasoning setting and fallback detail reasoning value. |
| `llm.detail_reasoning_effort` | Reasoning effort specifically for PDF detail analysis. |
| `pdf_enrichment.enabled` | Whether shortlisted PDFs should be downloaded and analyzed. |
| `pdf_enrichment.download_dir` | Local directory for cached PDFs. |
| `pdf_enrichment.max_file_size_mb` | Maximum allowed PDF size per paper. |
| `pdf_enrichment.timeout_seconds` | Request timeout for PDF download. |
| `pdf_enrichment.upload_expires_after_hours` | File expiration period for Files API uploads. |
| `digest.max_papers` | Maximum papers included in one daily digest. |
| `digest.output_dir` | Output directory for Markdown and HTML digests. |
| `email.recipients` | Recipient list for the final email. |

Notes:

- `schedule` is currently a recorded config field; scheduling is still handled by PM2, cron, or another external scheduler.
- `digest.section_strategy` is still effectively `keyword` in the current implementation.
- When `pdf_enrichment.enabled = true`, `llm.endpoint` must be `/responses`.
- Prompt templates live under `app/prompts/`, while prompt-version naming is still managed by code constants in the service layer.

## Output

Default artifacts:

```text
data/
  app.db
  pdfs/
    *.pdf
  digests/
    digest-YYYY-MM-DD.md
    digest-YYYY-MM-DD.html
```

- `data/app.db`: run history, paper metadata, evaluation cache, summary cache, detail cache, and delivery state
- `data/pdfs/`: downloaded PDF cache for shortlisted papers
- `data/digests/*.md`: archival digest and optional email attachment
- `data/digests/*.html`: HTML email body

Core database tables:

- `runs`
- `papers`
- `paper_evaluations`
- `paper_summaries`
- `paper_details`
- `digests`

## Prompt Management

Prompt templates are stored under `app/prompts/` and rendered through a shared loader. The current prompt set includes:

- `keyword_filter_system.txt`
- `keyword_filter_user.txt`
- `paper_summary_system.txt`
- `paper_summary_user.txt`
- `paper_detail_system.txt`
- `paper_detail_user.txt`

This keeps prompt text out of the OpenAI client implementation and makes prompt iteration easier.

## Detailed Paper Analysis

For shortlisted papers, the optional PDF-enrichment path can ask the model for a richer `PaperDetailResult`. The current structure is designed for practical paper triage rather than only producing a longer abstract:

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

The model is asked to separate what the paper claims from how convincing the evidence appears, avoid unsupported details, and explicitly acknowledge uncertainty when the PDF does not justify a conclusion.

## Scheduling

The repository includes `ecosystem.config.cjs` for PM2-based scheduling.

```bash
pm2 start ecosystem.config.cjs
pm2 save
```

You can also override defaults via environment variables:

```bash
PM2_CRON="15 13 * * *" \
PYTHON_BIN="python" \
CONFIG_FILE="config.toml" \
pm2 start ecosystem.config.cjs
```

Recommendations:

- keep `PM2_CRON` aligned with `config.toml`
- do one `--dry-run` before enabling production delivery
- inspect `logs/pm2-out.log` and `logs/pm2-error.log`

## Release Packaging

```bash
python scripts/build_release.py --clean --exclude-local-config
```

PowerShell:

```powershell
.\scripts\build_release.ps1 -Clean -ExcludeLocalConfig
```

The archive is written to `dist/` and includes:

- `app/`
- `scripts/`
- `docs/`
- `pyproject.toml`
- `ecosystem.config.cjs`
- `config.example.toml`
- `.env.example`

If `--exclude-local-config` is not used, local `config.toml` and `.env` are included too.

## Testing

Run the full test suite locally:

```bash
python -m pytest -q
```

Current tests cover:

- config loading and validation
- database persistence and cache behavior
- Markdown / HTML rendering
- prompt loading
- OpenAI client mode switching and Files API detail flow
- detail service fallback behavior
- arXiv client request spacing and PDF download validation

## Project Layout

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

## Known Limitations

- Delivery retry and backoff for OpenAI / SMTP are still limited.
- Prompt templates are externalized, but prompt versioning is still code-driven rather than independently managed.
- There is no built-in backfill, replay, alerting, monitoring, or Docker deployment workflow yet.
- `section_strategy` is present as a config field, but broader sectioning strategies are not fully implemented.

## License

MIT
