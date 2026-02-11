# /report Command Implementation Plan

- Version: 1.0.0
- Created at: 2026-02-11 07:29:09
- Status: Implemented

---

## Context

Add a `/report` Telegram command for token usage statistics, similar to Claude Code's `/insights`. Users want to see total token usage across time periods, with today's detailed breakdown by model/project/session.

Data source: `~/.claude/projects/{encoded_project_path}/{session_id}.jsonl` — only `type: "assistant"` messages contain `message.usage` fields.

---

## Output Format

```
📊 Token Usage Report

Today: 245.3K (in:210.1K out:35.2K) ~$9.44
Week: 1.2M (in:1.0M out:200.5K) ~$38.50
Month: 5.8M (in:4.9M out:891.2K) ~$142.30
Cache today: read 1.5M, write 302.4K

📦 By Model (today)
  Opus 4.6: 200.1K
  Haiku 4.5: 45.2K

📁 By Project (today)
  tool/claudecode-remote: 150.3K
  AIM/aim-shorts: 95.0K

🔗 By Session (today, top 5)
  7cc07a15...: 80.2K
  1a8ca3f1...: 70.1K
```

---

## Changes

### bridge.py

1. **`MODEL_SHORT_NAMES` dict + `shorten_model_name()`** — Map model IDs to short display names (e.g. `claude-opus-4-6` -> `Opus 4.6`). Fallback: strip `claude-` prefix + date suffix, title case.

2. **`scan_token_usage(days=30)`** — Single-pass scan of all JSONL files:
   - mtime pre-filter: skip files older than 31 days
   - Fast line pre-check: `'"usage"' not in line` -> skip JSON parse
   - String comparison on ISO timestamps for day bucketing
   - Skip `<synthetic>` model entries
   - Returns: `{"totals": {today/7d/30d}, "by_model": {}, "by_model_7d": {}, "by_model_30d": {}, "by_project": {}, "by_session": {}, "cache_today": {}}`
   - "Today" = local timezone midnight

3. **`_format_tokens(n)` + `format_token_report(data)`** — Number formatting (K/M suffix), top 5 sessions, last 2 path components for projects, zero shows `-`.

4. **`/report` handler** — Send "Scanning sessions..." first, then scan and format.

5. **`BOT_COMMANDS`** — Added `{"command": "report", "description": "Token usage report"}`.

### tests/test_report.py (~20 tests)

| Test Class | Cases |
|---|---|
| `TestShortenModelName` | known models (opus/haiku/sonnet); unknown with date suffix; unknown without date; non-claude |
| `TestScanTokenUsage` | empty projects; today totals; 7d excludes old; 30d includes; by_model; by_project; by_session; skips synthetic; skips old mtime; skips user entries; cache tokens |
| `TestFormatTokenReport` | empty data; basic format; K/M suffix; zero shows dash; small number; model section; session top 5; cache section |

### Docs

- `CLAUDE.md` — `/report` in Telegram Commands table
- `README.md` — `/report` in command list
- `docs/README_CN.md` — `/report` in command list
- `docs/plans/new-features-plan.md` — 问题 10: /report
- `scripts/start.sh` — `/report` in help text output

---

## Key Design Decisions

- **Per-line cost estimation**: Cost attached to each time period line (today/week/month) using model-specific rates
- **Local timezone for "today"**: User expects "today" = their local day, not UTC midnight
- **Single-pass scan**: One file traversal produces all three time ranges
- **Top 5 sessions**: Avoid cluttering Telegram with too many entries
- **"Scanning sessions..." reply**: Immediate feedback since scan may take 1-2s on large datasets
- **mtime pre-filter**: Skip files that can't possibly contain data within the time range
- **Line pre-check**: Skip JSON parsing for lines without "usage" string
