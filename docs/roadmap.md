# Daily arXiv Notify Roadmap

## 1. Current Baseline

The current codebase already has a working Phase 1 MVP:

- TOML + `.env` + environment-variable config loading
- SQLite storage for runs, papers, evaluations, summaries, and digests
- arXiv API ingestion with overlap-window incremental fetching
- rule filter + AI keyword related / not-related classification
- per-paper summary generation
- Markdown + HTML digest rendering
- SMTP delivery
- PM2 deployment config
- basic tests for config, DB, renderer, and OpenAI client mode switching

This roadmap only covers the work that is still not implemented or only partially implemented.

## 2. Guiding Priority

Recommended order:

1. reliability and operability first
2. digest quality second
3. deeper content accuracy third
4. production hardening last

Reason:

- the current system can already run end to end
- the biggest near-term risk is not missing functionality, but unstable daily operation
- quality improvements only matter after the daily pipeline is trustworthy

## 3. Roadmap

### Roadmap A: Reliability and Operability

Status: not implemented / partially implemented

Goal:

- make daily runs safe to repeat, inspect, and recover

Scope:

- add retry and backoff for arXiv, OpenAI, and SMTP transient failures
- add structured run metrics:
  - fetched count
  - rule-matched count
  - AI-evaluated count
  - selected count
  - summary-generated count
  - send status
- add token usage and estimated cost reporting
- externalize prompts into versioned files under `app/prompts/`
- add `scripts/backfill.py`
- add `scripts/replay_run.py`
- add tests for:
  - arXiv parsing
  - filter service
  - digest generation edge cases

Acceptance criteria:

- transient API failures are retried automatically
- every run can be audited from DB + logs
- prompts are not hardcoded in client/service modules
- backfill and replay can be invoked from CLI

Suggested implementation order:

1. prompt files + prompt loader
2. retry wrappers
3. run metrics persistence/logging
4. backfill/replay scripts
5. test expansion

### Roadmap B: Digest Quality

Status: partially implemented

Already present:

- per-paper structured summary
- HTML email rendering

Still missing:

- topic clustering
- better cross-paper digest synthesis
- configurable section strategies beyond first-keyword grouping
- higher-quality digest intro / executive summary
- prompt version management as a first-class feature rather than constants in code
- cost-aware summarization policy

Goal:

- make the daily digest easier to scan and more useful as a reading shortlist

Scope:

- add topic clustering for shortlisted papers
- support section strategies:
  - by keyword
  - by topic
  - new papers vs updated papers
- generate a digest-level overview using the LLM
- improve ranking and ordering inside each section
- add optional “why this matters today” intro block

Acceptance criteria:

- digest sections no longer depend only on the first matched keyword
- digest overview summarizes the main themes of the day
- ranking is deterministic and configurable

### Roadmap C: Content Accuracy and Coverage

Status: not implemented

Goal:

- improve summary quality and reduce false positives / false negatives

Scope:

- selective PDF download for shortlisted papers
- PDF text extraction for first pages / intro / conclusion
- richer summarization using abstract + extracted text
- better revision handling and version-delta classification
- profile-based personalization:
  - preferred keywords
  - excluded areas
  - category weights
- optional manual review / approval workflow before email send

Acceptance criteria:

- shortlisted paper summaries can use more than title + abstract
- revised papers are handled separately and more accurately
- different users or profiles can receive different digests

Implementation notes:

- keep PDF enrichment opt-in and only run on shortlisted papers
- do not expand this before cost reporting from Roadmap A is available

### Roadmap D: Production Hardening

Status: partially implemented

Already present:

- PM2 deployment config for scheduled execution

Still missing:

- Docker image
- containerized scheduling option
- metrics and alerting
- SMTP delivery hardening
- operational documentation
- backup / restore guidance for SQLite

Goal:

- make deployment easier to reproduce and easier to monitor

Scope:

- add `Dockerfile`
- add `.dockerignore`
- add deployment docs for:
  - PM2 on VPS
  - Docker + cron/container scheduler
- add health and failure alerting:
  - run failure notification
  - send failure notification
  - stale-run detection
- improve SMTP delivery observability:
  - message-id tracking
  - retry classification
  - clearer send logs
- add DB backup guidance for SQLite

Acceptance criteria:

- a new host can deploy the service from documented steps
- failed daily runs are visible without manual log inspection
- email delivery failures can be traced from logs and DB records

## 4. Recommended Next Sprint

If implementing in the next iteration, the recommended sprint is:

1. prompt files + prompt version loader
2. retry/backoff for arXiv/OpenAI/SMTP
3. run metrics + token/cost reporting
4. `backfill.py`
5. `replay_run.py`
6. arXiv/filter/digest tests

Reason:

- this closes the biggest gap between “working MVP” and “daily service you can trust”

## 5. Nice-to-Have After the Main Roadmap

- multi-profile digests from one run
- web review page for shortlisted papers
- Slack/Telegram/Feishu delivery
- attachment of CSV / JSON exports for run results
- lightweight admin commands for inspecting recent runs

## 6. Tracking Convention

Recommended issue labels:

- `roadmap:A-reliability`
- `roadmap:B-quality`
- `roadmap:C-accuracy`
- `roadmap:D-production`

Recommended milestone order:

1. `v0.2 reliability`
2. `v0.3 digest-quality`
3. `v0.4 enrichment`
4. `v0.5 production`
