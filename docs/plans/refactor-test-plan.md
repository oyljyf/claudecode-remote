# Refactoring & Unit Test Plan

- Version: 1.0.3
- Updated at: 2026-02-10 08:20:00
- Status: Implemented (162 tests)

---

## Context

The project has zero tests, significant code duplication (~25-30% in shell scripts, 4x repeated patterns in bridge.py), giant functions (handle_message ~250 lines), tight I/O coupling making everything untestable, and a path-quoting security bug. This plan prioritizes high-value, low-risk changes first.

---

## Phase 1: Test Infrastructure

**Files:** `pyproject.toml`, `tests/__init__.py`, `tests/conftest.py`

- Add `pytest>=7.0` to `[project.optional-dependencies]`
- Create `tests/` with conftest.py fixtures:
  - `tmp_claude_dir` — temp `~/.claude/` equivalent, monkeypatches all `*_FILE` constants
  - `fake_session_files` — realistic `.jsonl` files with controlled mtimes
  - `mock_telegram_api` — captures calls instead of HTTP
  - `mock_tmux` — patches subprocess calls, returns controlled values

---

## Phase 2: Extract Pure Functions from bridge.py

All changes in `bridge.py` (no module split).

### 2.1 `is_shell_prompt(pane_content: str) -> bool`
Extract from `tmux_is_at_shell()` (L120-133). Pure string logic.
`tmux_is_at_shell()` becomes: `return is_shell_prompt(tmux_get_pane_content(3))`

### 2.2 `filter_window_title(title: str) -> str | None`
Extract from `tmux_get_title()` (L214-225). Move ignored names to `GENERIC_WINDOW_NAMES` constant.

### 2.3 Make `decode_project_path()` injectable
Add `exists_fn=os.path.isdir` parameter for test injection.

### 2.4 `format_session_message(action, session_id, project_path) -> str`
Replace 4x repeated confirmation message pattern (L534, L551, L627, L771).

---

## Phase 3: Extract Sync State Management

### 3.1 `clear_sync_flags() -> None`
Replace 4x identical pattern at L594, L679, L754, L804.

### 3.2 `get_sync_state() -> str`
Returns `"active"` / `"paused"` / `"terminated"`. Replaces inline checks at L652 and L852.

### 3.3 `SYNC_STATE_MESSAGES` and `SYNC_STATE_ICONS` dicts
Centralize the status message strings.

---

## Phase 4: Extract Cross-Project CD Logic + Security Fix

### 4.1 `tmux_exit_claude() -> None`
Extract exit sequence duplicated at L157-168 and L602-612.

### 4.2 `tmux_cd_and_start(target_path, resume_session_id=None) -> None`
Extract cd + start logic. **Fix: `shlex.quote()` for paths with spaces.**

### 4.3 Simplify `tmux_switch_session()` and `new_in_project` callback
Both use `tmux_exit_claude()` + `tmux_cd_and_start()`.

---

## Phase 5: Callback Constants + Validation

### 5.1 Magic string constants
```python
CB_RESUME = "resume:"
CB_PROJECT = "project:"
CB_NEW_IN_PROJECT = "new_in_project:"
CB_CONTINUE_RECENT = "continue_recent"
```

### 5.2 `parse_callback_data(data, prefix) -> str | None`
Validate non-empty, length < 128.

---

## Phase 6: Write Unit Tests

### `tests/test_project_utils.py` (~15 tests)

| Function                   | Cases                                                                                          |
| -------------------------- | ---------------------------------------------------------------------------------------------- |
| `project_hash()`           | 8-char hex; deterministic; populates cache                                                     |
| `project_from_hash()`      | found -> name; missing -> None                                                                 |
| `decode_project_path()`    | simple path; hyphenated dir (my-app); nested (AIM/aim-skills); no match -> None; empty -> None |
| `format_session_message()` | with/without path; short ID                                                                    |

### `tests/test_session.py` (~10 tests)

| Function                           | Cases                                               |
| ---------------------------------- | --------------------------------------------------- |
| `is_valid_session()`               | valid; empty; invalid JSON; old (>30d); nonexistent |
| `get_recent_sessions_from_files()` | sorted by mtime; empty dir; filters invalid         |
| `get_sessions_for_project()`       | sorted; respects limit; filters invalid             |
| `get_projects()`                   | counts; limit; sorted by activity                   |

### `tests/test_sync_state.py` (~7 tests)

| Function             | Cases                                                      |
| -------------------- | ---------------------------------------------------------- |
| `get_sync_state()`   | no flags -> active; paused; terminated; both -> terminated |
| `clear_sync_flags()` | both exist; one exists; none exist                         |

### `tests/test_tmux_detection.py` (~12 tests)

| Function                | Cases                                                                                                                      |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `is_shell_prompt()`     | `"user@host $"` yes; `"~ %"` yes; `"root #"` yes; `">"` yes; `"-> project"` yes; `"Claude..."` no; empty no; all blanks no |
| `filter_window_title()` | UUID -> returns; "bash" -> None; "zsh" -> None; empty -> None                                                              |

### `tests/test_handler.py` (~34 tests, mocked I/O)

| Test Class | Cases |
| --- | --- |
| `TestStatusCommand` | tmux up+active; tmux down; paused; terminated |
| `TestStartCommand` | tmux exists; tmux missing |
| `TestStopCommand` | creates paused flag |
| `TestEscapeCommand` | sends escape; tmux missing |
| `TestTerminateCommand` | creates disabled flag |
| `TestContinueCommand` | clears flags+finds session; no sessions |
| `TestResumeCommand` | keyboard with sessions; no sessions |
| `TestProjectsCommand` | keyboard with projects; no projects |
| `TestRegularMessage` | active->tmux; paused->reject; terminated->reject; auto-binds |
| `TestPermissionCallback` | allow; deny; expired; no pending; allow no tmux needed |
| `TestPermissionEndToEnd` | allow produces correct JSON; deny produces correct JSON; response file cleaned after read; stale response ignored; telegram confirmation message |
| `TestParseCallbackData` | valid; empty value; too long; wrong prefix |

---

## Phase 7: Shell Script Deduplication

### 7.1 `scripts/lib/common.sh`
Extract from start.sh, install.sh, uninstall.sh:
- Color codes (3x)
- `print_status/error/warning/info` (3x)
- `kill_process()`, `kill_bridge()`, `kill_cloudflared()` (2x)

Each script: `source "$SCRIPT_DIR/lib/common.sh"`

### 7.2 `hooks/lib/common.sh`
Extract from both hooks:
- All env var definitions
- `mkdir -p "$LOG_DIR"`
- `get_chat_id()` -- chat ID lookup (2x)
- `get_sync_disabled()` -- sync check (2x)

Update `--setup-hook` and install.sh to copy `hooks/lib/` to `~/.claude/hooks/lib/`.

### 7.3 Shell Script Consistency Tests (`tests/test_shell_scripts.py`)

Post-refactor regression tests to ensure common.sh usage stays consistent.

| Test Class | Cases |
| --- | --- |
| `TestScriptsLibCommon` | defines all shared path vars (incl PERM_PENDING_FILE, PERM_RESPONSE_FILE); defines print functions |
| `TestHooksLibCommon` | defines shared path vars; defines token; defines helper functions |
| `TestPathConsistency` | both common.sh files define identical paths |
| `TestHookScriptsSourceCommon` | all 4 hook scripts (send-to-telegram, send-input-to-telegram, play-alarm, handle-permission) source lib/common.sh; no hardcoded token in telegram hooks |
| `TestScriptsSourceCommon` | all 4 scripts (start, install, uninstall, clean-logs) source lib/common.sh |
| `TestTokenReplacementTarget` | install.sh/start.sh sed targets common.sh; grep checks target common.sh |
| `TestNoHardcodedStateFiles` | no hardcoded SYNC_DISABLED_FILE/PENDING_FILE/LOG_DIR assignments in scripts |
| `TestSetupHookCopiesLib` | install.sh and start.sh --setup-hook copy hooks/lib/ |
| `TestAlarmHookIntegration` | play-alarm.sh exists, is executable, sources common.sh, checks disabled flag, runs in background; install.sh/start.sh copy alarm hook + sounds + settings.json includes alarm + Notification hook; uninstall.sh removes alarm hook + sounds + alarm_disabled |
| `TestPermissionHookIntegration` | handle-permission.sh exists, sources common.sh, checks sync, reads stdin, uses jq; install.sh/start.sh copy permission hook + settings.json includes PermissionRequest with timeout 120; uninstall.sh removes permission hook + settings + state files |
| `TestUninstallComponentFlags` | supports --telegram/--alarm/--all/--keep-deps/--force flags; interactive chooser (Telegram/Alarm/Both); --force defaults both; REMOVE_TELEGRAM/REMOVE_ALARM guards; hooks/lib only when both; selective jq for telegram-only and alarm-only; removes Notification hooks; processes/env vars under telegram guard; --all removes logs; deps only with telegram |
| `TestCleanLogsScript` | uses -mmin not -mtime; DAYS * 1440 calculation; targets cc_[0-9]{8}.log (MMDDYYYY only); cleans debug.log; default 30 days |

---

## NOT Doing (Deferred)

- Full module split of bridge.py -> too much churn
- Handler dispatch table -> lower priority
- bats tests for shell scripts -> pytest covers critical logic
- Config class / logging module -> current approach adequate

---

## File Change Summary

| File                              | Action                                            |
| --------------------------------- | ------------------------------------------------- |
| `pyproject.toml`                  | Add test deps                                     |
| `bridge.py`                       | Extract functions, de-dup, shlex.quote, constants |
| `tests/__init__.py`               | New                                               |
| `tests/conftest.py`               | New (fixtures)                                    |
| `tests/test_project_utils.py`     | New (~15 tests)                                   |
| `tests/test_session.py`           | New (~10 tests)                                   |
| `tests/test_sync_state.py`        | New (~7 tests)                                    |
| `tests/test_tmux_detection.py`    | New (~12 tests)                                   |
| `tests/test_handler.py`           | New (~34 tests)                                   |
| `scripts/lib/common.sh`           | New                                               |
| `hooks/lib/common.sh`             | New                                               |
| `hooks/send-to-telegram.sh`       | Source common.sh, remove duplication              |
| `hooks/send-input-to-telegram.sh` | Source common.sh, remove duplication              |
| `hooks/handle-permission.sh`      | New (PermissionRequest hook)                      |
| `tests/test_shell_scripts.py`     | New (~76 tests)                                   |
| `scripts/start.sh`                | Source common.sh, update --setup-hook             |
| `scripts/install.sh`              | Source common.sh                                  |
| `scripts/uninstall.sh`            | Source common.sh                                  |
| `scripts/clean-logs.sh`           | Source common.sh                                  |

---

## Verification

1. `pytest tests/ -v` -- all 162 tests pass (86 Python + 76 shell script consistency)
2. `./scripts/start.sh --new` -> Telegram message -> response back
3. `./scripts/start.sh --setup-hook` -> hooks + lib copied correctly
4. Test `/status`, `/stop`, `/escape`, `/resume`, `/projects`, `/continue` from Telegram
5. Verify logs written when sync paused/terminated
6. Permission request -> Telegram Allow/Deny buttons -> Claude continues
