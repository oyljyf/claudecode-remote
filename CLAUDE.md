# AGENTS.md - Project Overview for AI Agents

## Security Rules

**IMPORTANT: Before committing any changes, run the pre-commit security check below.**

### Pre-Commit Security Checklist

Run these commands from the project root before every commit:

```bash
# 1. Telegram bot tokens (format: 123456789:ABC-DEF...)
grep -rn "[0-9]\{9,10\}:[A-Za-z0-9_-]\{35\}" --include="*.sh" --include="*.py" --include="*.json" .

# 2. API keys, secrets, passwords
grep -rniE "(api_key|secret|password|credential|private_key)\s*[:=]" --include="*.sh" --include="*.py" .

# 3. Real user paths (replace 'yourusername' with actual username)
grep -rn "/Users/$(whoami)/" --include="*.sh" --include="*.py" --include="*.md" --include="*.json" .

# 4. Hardcoded chat IDs (numeric, 6+ digits, not in comments/examples)
grep -rnE "chat_id\s*=\s*[0-9]{6,}" --include="*.py" --include="*.sh" .

# 5. Verify token placeholder is only in hooks/lib/common.sh
grep -rn "YOUR_BOT_TOKEN_HERE" --include="*.sh" .
# Expected: only hooks/lib/common.sh line 5
```

**Expected results:**
- Check 1-4: No output (clean)
- Check 5: Only `hooks/lib/common.sh` should contain the placeholder

### Token Rules

- Never commit real `TELEGRAM_BOT_TOKEN` values
- Use `YOUR_BOT_TOKEN_HERE` as placeholder in `hooks/lib/common.sh` only
- Token should only exist at runtime in:
  - `~/.claude/hooks/lib/common.sh` (installed copy, not in repo)
  - `~/.zshrc` or `~/.bashrc` (local, not in repo)
  - Environment variables

### .gitignore Must Exclude

| Pattern | Reason |
|---------|--------|
| `.venv/` | Contains absolute user paths in editable install metadata |
| `.env` | May contain tokens |
| `.claude/*` | Local user configuration and state |
| `*.egg-info/` | Build metadata with absolute paths |
| `.installed` | Local install marker |

---

## Project Summary

**claudecode-remote** is a Telegram bot bridge for Claude Code that enables bidirectional sync between desktop Claude Code sessions and Telegram. It supports three-state sync control, cross-project session switching, and automatic session binding.

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Desktop        │      │   Bridge         │      │   Telegram      │
│  Claude Code    │◄────►│   (Python)       │◄────►│   Bot API       │
│  (in tmux)      │      │   + Hooks        │      │                 │
│                 │      │   + Poller       │      │                 │
└─────────────────┘      └──────────────────┘      └─────────────────┘
         │                       │
         │ Hook scripts          │ cloudflared tunnel
         │ (Stop, UserPrompt)    │ (HTTPS → localhost:PORT)
         ▼                       ▼
    ~/.claude/logs/         Telegram Webhook
```

## Key Components

| File | Purpose |
|------|---------|
| `bridge.py` | HTTP server: Telegram webhooks, tmux communication, session management, project navigation |
| `hooks/lib/common.sh` | Shared hook library: Telegram token, file paths, helper functions |
| `hooks/send-to-telegram.sh` | Stop hook: sends Claude responses to Telegram, always logs |
| `hooks/send-input-to-telegram.sh` | UserPromptSubmit hook: syncs desktop input to Telegram, always logs |
| `scripts/lib/common.sh` | Shared script library: colors, print functions, process helpers, file paths |
| `scripts/start.sh` | Startup script: tmux/tunnel/webhook management |
| `scripts/install.sh` | One-command installation |
| `scripts/uninstall.sh` | Clean uninstallation with tmux/process cleanup |

## Three-State Sync Model

| State | Flag File | Hook Behavior | Bridge Behavior |
|-------|-----------|---------------|-----------------|
| Active | (none) | Send + log | Forward messages |
| Paused | `~/.claude/telegram_sync_paused` | Log only | Reject (hint: paused) |
| Terminated | `~/.claude/telegram_sync_disabled` | Log only | Reject (hint: terminated) |

## Session Management

Sessions stored in `~/.claude/projects/{encoded_project_path}/{session_id}.jsonl`

### Path Encoding

Claude Code encodes project paths: `/Users/foo/my-app` → `-Users-foo-my-app`

`decode_project_path()` uses greedy filesystem matching to handle hyphens in directory names (e.g., `aim-skills` vs path separators).

### Key Files

| File | Purpose |
|------|---------|
| `~/.claude/session_chat_map.json` | Maps session_id → telegram_chat_id |
| `~/.claude/current_session_id` | Current active session ID |
| `~/.claude/telegram_chat_id` | Global fallback chat ID |
| `~/.claude/telegram_sync_disabled` | Terminated state flag |
| `~/.claude/telegram_sync_paused` | Paused state flag |

### Session ID Detection (Priority Order)

1. tmux window title (set via `tmux rename-window`)
2. `current_session_id` file
3. Most recently modified `.jsonl` file

### Session Validation

`is_valid_session()` filters sessions by:
- File size > 0 (non-empty)
- Age < 30 days
- Valid JSON first line

## Important Functions (bridge.py)

| Function | Purpose |
|----------|---------|
| `get_current_session_id()` | Get active session with cross-validation |
| `get_recent_sessions_from_files()` | Scan actual session files |
| `get_project_path_for_session()` | Find project path for a session ID |
| `decode_project_path()` | Convert encoded dir name back to path (greedy FS matching) |
| `resolve_project_dir()` | Find project dir under `~/.claude/projects/` |
| `bind_session_to_chat()` | Create session ↔ chat binding |
| `tmux_switch_session()` | Switch session (handles cross-project cd + restart) |
| `tmux_new_session()` | Start new session (with shell fallback) |
| `tmux_is_at_shell()` | Detect if tmux is at shell prompt (not in Claude) |
| `tmux_get_cwd()` | Get tmux pane current working directory |
| `session_poller()` | Background thread: detect new sessions, auto-bind |
| `is_valid_session()` | Filter empty/old/corrupted sessions |
| `get_projects()` | List projects with session counts |
| `get_sessions_for_project()` | List sessions for a specific project |
| `project_hash()` / `project_from_hash()` | Short hash for callback_data (64-byte limit) |

## Telegram Commands

| Command | Handler | Action |
|---------|---------|--------|
| `/start` | `handle_message` | New session in tmux, clear paused/disabled flags |
| `/stop` | `handle_message` | Create paused flag, pause sync |
| `/escape` | `handle_message` | Send Escape to tmux, interrupt Claude |
| `/terminate` | `handle_message` | Create disabled flag, disconnect |
| `/resume` | `handle_message` + `handle_callback` | List sessions, resume selected (cross-project aware) |
| `/continue` | `handle_message` | Continue most recent session |
| `/projects` | `handle_message` + `handle_callback` | Browse projects → sessions (two-level navigation) |
| `/bind` | `handle_message` | Force-bind current session to chat |
| `/clear` | `handle_message` | Send /clear to Claude |
| `/status` | `handle_message` | Show tmux, session, sync, binding status |
| `/loop <prompt>` | `handle_message` | Ralph Loop: auto-iteration |

### Callback Data Format

Telegram callback_data has 64-byte limit. Uses short hashes for project IDs:
- `project:{8-char-hash}` — select project (16 bytes)
- `new_in_project:{8-char-hash}` — new session in project (23 bytes)
- `resume:{uuid}` — resume specific session (43 bytes)
- `continue_recent` — continue most recent session

## Script Options (start.sh)

| Option | Action |
|--------|--------|
| `--new [path]` | Create tmux session (shell first, then inject Claude) + start bridge |
| `--attach` | Attach to tmux with session picker |
| `--detach` | Detach clients from tmux |
| `--view` | View tmux output without attaching |
| `--terminate` | Kill all processes + disable sync |
| `--setup-hook` | Configure Claude hooks |
| `--check` | Verify configuration |

### tmux Session Creation

Sessions are created with interactive shell first, then Claude is injected:
```bash
tmux new-session -d -s "$TMUX_SESSION" -c "$TARGET_DIR"
tmux set-option -t "$TMUX_SESSION" mouse on
tmux set-option -t "$TMUX_SESSION" history-limit 10000
tmux set-window-option -t "$TMUX_SESSION" allow-rename off
sleep 0.5
tmux send-keys -t "$TMUX_SESSION" "claude --dangerously-skip-permissions" Enter
```

This ensures:
- Mouse scrollback works
- Shell is available when Claude exits (no session termination)
- Window title is under our control (`allow-rename off`)

## Message Flow

### Telegram → Desktop
```
Telegram message
  → cloudflared tunnel → Bridge webhook (do_POST)
  → Check paused/disabled state
  → Auto-bind if needed
  → tmux_send(text) + tmux_send_enter()
  → Claude Code receives input
```

### Desktop → Telegram
```
User types in Claude Code
  → UserPromptSubmit hook fires
  → send-input-to-telegram.sh
  → Always log to ~/.claude/logs/
  → If sync active: send to Telegram API

Claude responds
  → Stop hook fires
  → send-to-telegram.sh
  → Extract text from transcript
  → Always log to ~/.claude/logs/
  → If sync active: send to mapped chat_id
```

### Cross-Project Session Switch
```
User selects session from different project (via /projects or /resume)
  → get_project_path_for_session() → decode_project_path()
  → tmux_get_cwd() → compare with target path
  → If different project:
    → Exit Claude (/exit)
    → cd to target project
    → claude --resume <session_id> --dangerously-skip-permissions
  → If same project:
    → /resume <session_id> (Claude built-in)
    → Fallback: restart if Claude exits
```

## Common Issues

1. **Session not found**: Use `/projects` for cross-project switch (auto-handles cd)
2. **Sync disabled**: Check `~/.claude/telegram_sync_disabled` and `telegram_sync_paused`
3. **tmux title mismatch**: `allow-rename off` prevents shell from overwriting title
4. **Hyphenated dir names**: `decode_project_path()` uses greedy FS matching
5. **Callback data too long**: Project names use 8-char MD5 hash, resolved via in-memory cache

## Development Notes

- Bridge uses stdlib only (no external dependencies)
- Hooks are bash scripts with embedded Python for Telegram API
- Shared config (file paths, token) lives in `hooks/lib/common.sh` and `scripts/lib/common.sh`
- Token placeholder (`YOUR_BOT_TOKEN_HERE`) is defined in `hooks/lib/common.sh` only; install/setup scripts replace it there
- `DEFAULT_PORT=8080` is defined in `scripts/lib/common.sh`; `start.sh` uses `PORT=${PORT:-$DEFAULT_PORT}`; `bridge.py` reads `PORT` from env
- Session files are JSONL format (one JSON object per line)
- Cloudflare Quick Tunnels provide HTTPS endpoint for webhooks
- Session poller runs as background daemon thread
- Hook scripts always log, conditionally send (based on sync state flags)
