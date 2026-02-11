#!/usr/bin/env python3
"""Claude Code <-> Telegram Bridge"""

import hashlib
import os
import json
import re
import shlex
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

def _load_config_env() -> dict[str, str]:
    """Load defaults from config.env (single source of truth)."""
    defaults = {}
    try:
        config = Path(__file__).parent / "config.env"
        for line in config.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                defaults[k.strip()] = v.strip()
    except Exception:
        pass
    return defaults


_CONFIG = _load_config_env()

TMUX_SESSION = os.environ.get("TMUX_SESSION", _CONFIG.get("DEFAULT_TMUX_SESSION", "claude"))
CHAT_ID_FILE = os.path.expanduser("~/.claude/telegram_chat_id")
PENDING_FILE = os.path.expanduser("~/.claude/telegram_pending")
SESSION_CHAT_MAP_FILE = os.path.expanduser("~/.claude/session_chat_map.json")
CURRENT_SESSION_FILE = os.path.expanduser("~/.claude/current_session_id")
SYNC_DISABLED_FILE = os.path.expanduser("~/.claude/telegram_sync_disabled")
SYNC_PAUSED_FILE = os.path.expanduser("~/.claude/telegram_sync_paused")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# In-memory cache: short hash -> encoded project name (for callback_data within 64 byte limit)
_project_id_cache: dict[str, str] = {}

# Window names that indicate no meaningful title is set
GENERIC_WINDOW_NAMES = frozenset({"bash", "zsh", "sh", "python", ""})

# Callback data prefixes
CB_RESUME = "resume:"
CB_PROJECT = "project:"
CB_NEW_IN_PROJECT = "new_in_project:"
CB_CONTINUE_RECENT = "continue_recent"
CB_ASK_ANSWER = "askq:"

# Sync state constants
SYNC_STATE_ACTIVE = "active"
SYNC_STATE_PAUSED = "paused"
SYNC_STATE_TERMINATED = "terminated"

SYNC_STATE_ICONS = {
    SYNC_STATE_ACTIVE: "🟢",
    SYNC_STATE_PAUSED: "🟡",
    SYNC_STATE_TERMINATED: "🔴",
}

SYNC_STATE_MESSAGES = {
    SYNC_STATE_PAUSED: "🟡 Sync paused. Use /start, /resume, or /continue to resume.",
    SYNC_STATE_TERMINATED: "🔴 Sync terminated. Use /start to reconnect.",
}

MODEL_SHORT_NAMES = {
    "claude-opus-4-6": "Opus 4.6",
    "claude-opus-4-5-20250514": "Opus 4.5",
    "claude-sonnet-4-5-20250929": "Sonnet 4.5",
    "claude-sonnet-4-5-20250514": "Sonnet 4.5",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-sonnet-4-20250514": "Sonnet 4",
}


def shorten_model_name(model_id: str) -> str:
    """Convert a model ID to a short display name."""
    if model_id in MODEL_SHORT_NAMES:
        return MODEL_SHORT_NAMES[model_id]
    name = model_id
    if name.startswith("claude-"):
        name = name[len("claude-"):]
    # Strip date suffix (e.g. -20250514)
    name = re.sub(r"-\d{8}$", "", name)
    # Title case
    return name.replace("-", " ").title()


def project_hash(encoded_name: str) -> str:
    """Generate a short 8-char hash for a project encoded name."""
    h = hashlib.md5(encoded_name.encode()).hexdigest()[:8]
    _project_id_cache[h] = encoded_name
    return h


def project_from_hash(h: str) -> str | None:
    """Resolve short hash back to encoded project name."""
    return _project_id_cache.get(h)


def is_shell_prompt(pane_content: str) -> bool:
    """Check if pane content looks like a shell prompt (Claude exited)."""
    for line in reversed(pane_content.splitlines()):
        line = line.strip()
        if not line:
            continue
        if line.endswith("$") or line.endswith("%") or line.endswith("#"):
            return True
        if "❯" in line or "➜" in line:
            return True
        break
    return False


def filter_window_title(title: str) -> str | None:
    """Return title if meaningful, None if generic/empty."""
    if title and title not in GENERIC_WINDOW_NAMES:
        return title
    return None


def format_session_message(action: str, session_id: str, project_path: str | None = None) -> str:
    """Format a confirmation message for session operations."""
    msg = f"{action}: {session_id}"
    if project_path:
        msg += f"\n📁 {project_path}"
    return msg


def clear_sync_flags() -> None:
    """Remove both sync paused and disabled flag files."""
    for f in (SYNC_PAUSED_FILE, SYNC_DISABLED_FILE):
        if os.path.exists(f):
            os.remove(f)


def get_sync_state() -> str:
    """Return current sync state: 'terminated', 'paused', or 'active'."""
    if os.path.exists(SYNC_DISABLED_FILE):
        return SYNC_STATE_TERMINATED
    if os.path.exists(SYNC_PAUSED_FILE):
        return SYNC_STATE_PAUSED
    return SYNC_STATE_ACTIVE


def parse_callback_data(data: str, prefix: str) -> str | None:
    """Extract and validate value after prefix in callback data."""
    if not data.startswith(prefix):
        return None
    value = data[len(prefix):]
    if not value or len(value) > 128:
        return None
    return value


PORT = int(os.environ.get("PORT", _CONFIG.get("DEFAULT_PORT", "8080")))

BOT_COMMANDS = [
    {"command": "start", "description": "Start new Claude session in tmux"},
    {"command": "stop", "description": "Pause sync (resume with /start, /resume, or /continue)"},
    {"command": "escape", "description": "Interrupt Claude (send Escape)"},
    {"command": "terminate", "description": "Disconnect completely (need /start to reconnect)"},
    {"command": "resume", "description": "Resume session (shows picker)"},
    {"command": "continue", "description": "Continue most recent session"},
    {"command": "clear", "description": "Clear conversation"},
    {"command": "bind", "description": "Bind this chat to current session"},
    {"command": "loop", "description": "Ralph Loop: /loop <prompt>"},
    {"command": "status", "description": "Check tmux status"},
    {"command": "projects", "description": "Browse projects and sessions"},
    {"command": "report", "description": "Token usage report"},
]

BLOCKED_COMMANDS = [
    "/mcp", "/help", "/settings", "/config", "/model", "/compact", "/cost",
    "/doctor", "/init", "/login", "/logout", "/memory", "/permissions",
    "/pr", "/review", "/terminal", "/vim", "/approved-tools", "/listen"
]


def telegram_api(method, data):
    if not BOT_TOKEN:
        return None
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"Telegram API error: {e}")
        return None


def setup_bot_commands():
    result = telegram_api("setMyCommands", {"commands": BOT_COMMANDS})
    if result and result.get("ok"):
        print("Bot commands registered")


def send_typing_loop(chat_id):
    while os.path.exists(PENDING_FILE):
        telegram_api("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        time.sleep(4)


def _start_typing(chat_id: int) -> None:
    """Mark pending and start background typing indicator."""
    with open(PENDING_FILE, "w") as f:
        f.write(str(int(time.time())))
    threading.Thread(target=send_typing_loop, args=(chat_id,), daemon=True).start()


def _tmux_run(*args, capture=False, text=False) -> subprocess.CompletedProcess:
    """Run a tmux subcommand targeting TMUX_SESSION."""
    cmd = ["tmux", *args]
    return subprocess.run(cmd, capture_output=capture, text=text)


def tmux_exists():
    return _tmux_run("has-session", "-t", TMUX_SESSION, capture=True).returncode == 0


def tmux_send(text, literal=True):
    cmd = ["tmux", "send-keys", "-t", TMUX_SESSION]
    if literal:
        cmd.append("-l")
    cmd.append(text)
    subprocess.run(cmd)


def tmux_send_enter():
    _tmux_run("send-keys", "-t", TMUX_SESSION, "Enter")


def tmux_send_escape():
    _tmux_run("send-keys", "-t", TMUX_SESSION, "Escape")


def tmux_send_line(text, literal=True):
    """Send text followed by Enter to tmux."""
    tmux_send(text, literal=literal)
    tmux_send_enter()


def tmux_get_pane_content(lines=3) -> str:
    """Get the last N lines of the tmux pane to detect state."""
    result = _tmux_run("capture-pane", "-t", TMUX_SESSION, "-p", "-S", f"-{lines}",
                       capture=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def tmux_is_at_shell() -> bool:
    """Check if tmux pane is at a shell prompt (Claude exited)."""
    return is_shell_prompt(tmux_get_pane_content(3))


def tmux_get_cwd() -> str | None:
    """Get the current working directory of the tmux pane."""
    result = _tmux_run("display-message", "-t", TMUX_SESSION, "-p", "#{pane_current_path}",
                       capture=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def tmux_exit_claude() -> None:
    """Exit Claude in the tmux pane, returning to shell prompt."""
    tmux_send_escape()
    time.sleep(0.3)
    tmux_send_line("/exit")
    time.sleep(1.0)
    # If Claude didn't exit, force it
    if not tmux_is_at_shell():
        tmux_send_escape()
        time.sleep(0.2)
        tmux_send_line("exit")
        time.sleep(0.5)


def tmux_cd_and_start(target_path: str, resume_session_id: str | None = None) -> None:
    """cd to target_path and start Claude, optionally resuming a session."""
    tmux_send_line(f"cd {shlex.quote(target_path)}")
    time.sleep(0.3)
    if resume_session_id:
        tmux_send_line(f"claude --resume {resume_session_id} --dangerously-skip-permissions")
    else:
        tmux_send_line("claude --dangerously-skip-permissions")
    time.sleep(2.0)


def tmux_switch_session(session_id: str) -> None:
    """Switch Claude to a different session, handling cross-project switches."""
    target_path = get_project_path_for_session(session_id)
    current_cwd = tmux_get_cwd()

    # Check if target session is in a different project
    needs_cd = target_path and current_cwd and os.path.realpath(target_path) != os.path.realpath(current_cwd)

    if needs_cd:
        # Cross-project: must exit Claude, cd, then restart
        tmux_exit_claude()
        tmux_cd_and_start(target_path, resume_session_id=session_id)
    else:
        # Same project: try Claude's built-in /resume first
        tmux_send_escape()
        time.sleep(0.3)
        tmux_send_line(f"/resume {session_id}")
        time.sleep(2.0)

        # Check if Claude exited (returned to shell prompt)
        if tmux_is_at_shell():
            if target_path:
                tmux_cd_and_start(target_path, resume_session_id=session_id)
            else:
                tmux_send_line(f"claude --resume {session_id} --dangerously-skip-permissions")
                time.sleep(2.0)


def tmux_new_session() -> None:
    """Start a new Claude session, handling both in-process and restart cases."""
    tmux_send_escape()
    time.sleep(0.3)
    tmux_send_line("/clear")
    time.sleep(1.5)

    # Check if Claude exited
    if tmux_is_at_shell():
        tmux_send_line("claude --dangerously-skip-permissions")
        time.sleep(2.0)


def tmux_set_title(title: str) -> None:
    """Set the tmux window title to track current session."""
    _tmux_run("rename-window", "-t", TMUX_SESSION, title, capture=True)


def tmux_get_title() -> str | None:
    """Get the current tmux window title (used as session ID)."""
    result = _tmux_run("display-message", "-t", TMUX_SESSION, "-p", "#{window_name}",
                       capture=True, text=True)
    if result.returncode == 0:
        return filter_window_title(result.stdout.strip())
    return None



def _get_projects_dir() -> Path | None:
    """Return ~/.claude/projects if it exists, else None."""
    d = Path.home() / ".claude" / "projects"
    return d if d.exists() else None


def is_valid_session(jsonl_path: Path, max_age_days: int = 30) -> bool:
    """Check if a session file is valid and recoverable."""
    try:
        stat = jsonl_path.stat()
        # Skip empty files
        if stat.st_size == 0:
            return False
        # Skip files older than max_age_days
        age_days = (time.time() - stat.st_mtime) / 86400
        if age_days > max_age_days:
            return False
        # Verify it has at least one valid JSON line
        with open(jsonl_path) as f:
            first_line = f.readline().strip()
            if not first_line:
                return False
            json.loads(first_line)
        return True
    except (OSError, json.JSONDecodeError):
        return False


def get_recent_sessions_from_files(limit=10):
    """Get recent sessions directly from session files (more reliable)."""
    projects_dir = _get_projects_dir()
    if not projects_dir:
        return []
    all_sessions = []
    for jsonl in projects_dir.glob("*/*.jsonl"):
        if not is_valid_session(jsonl):
            continue
        try:
            stat = jsonl.stat()
            all_sessions.append({
                "session_id": jsonl.stem,
                "project_dir": jsonl.parent.name,
                "mtime": stat.st_mtime,
                "display": f"{jsonl.parent.name}:{jsonl.stem}"
            })
        except OSError:
            continue
    all_sessions.sort(key=lambda x: x["mtime"], reverse=True)
    return all_sessions[:limit]


def get_projects(limit=10):
    """Get project list with session counts and latest modification time."""
    projects_dir = _get_projects_dir()
    if not projects_dir:
        return []
    projects = []
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        jsonls = [j for j in project_dir.glob("*.jsonl") if is_valid_session(j)]
        if not jsonls:
            continue
        latest = max(jsonls, key=lambda p: p.stat().st_mtime)
        projects.append({
            "encoded_name": project_dir.name,
            "session_count": len(jsonls),
            "mtime": latest.stat().st_mtime,
        })
    projects.sort(key=lambda x: x["mtime"], reverse=True)
    return projects[:limit]


def resolve_project_dir(encoded_name: str) -> Path | None:
    """Resolve an encoded project name (possibly truncated) to a project directory."""
    projects_dir = _get_projects_dir()
    if not projects_dir:
        return None
    exact = projects_dir / encoded_name
    if exact.exists():
        return exact
    # Try prefix match (for truncated callback_data)
    for d in projects_dir.iterdir():
        if d.is_dir() and d.name.startswith(encoded_name):
            return d
    return None


def get_sessions_for_project(encoded_name: str, limit=10):
    """Get sessions for a specific project."""
    project_dir = resolve_project_dir(encoded_name)
    if not project_dir:
        return []
    sessions = []
    for jsonl in project_dir.glob("*.jsonl"):
        if not is_valid_session(jsonl):
            continue
        try:
            sessions.append({
                "session_id": jsonl.stem,
                "mtime": jsonl.stat().st_mtime,
            })
        except OSError:
            continue
    sessions.sort(key=lambda x: x["mtime"], reverse=True)
    return sessions[:limit]


def scan_token_usage(days: int = 30) -> dict:
    """Scan all session JSONL files and aggregate token usage.

    Returns dict with keys: totals, by_model, by_project, by_session,
    session_project, cache_today.
    Uses local timezone for "today" boundary.
    """
    projects_dir = _get_projects_dir()
    empty = {
        "totals": {}, "by_model": {}, "by_project": {}, "by_session": {},
        "session_project": {}, "cache_today": {},
    }
    if not projects_dir:
        return empty

    now = time.time()
    cutoff_mtime = now - (days + 1) * 86400  # +1 day buffer for timezone

    # Compute date boundaries in local timezone
    local_now = datetime.now()
    today_str = local_now.strftime("%Y-%m-%d")
    yesterday_str = (local_now - timedelta(days=1)).strftime("%Y-%m-%d")
    day7_str = (local_now - timedelta(days=7)).strftime("%Y-%m-%d")
    day30_str = (local_now - timedelta(days=30)).strftime("%Y-%m-%d")

    totals = {
        "today": {"input": 0, "output": 0},
        "yesterday": {"input": 0, "output": 0},
        "7d": {"input": 0, "output": 0},
        "30d": {"input": 0, "output": 0},
    }
    # by_model per period: model -> {"input": N, "output": N}
    by_model: dict[str, dict[str, int]] = {}       # today
    by_model_7d: dict[str, dict[str, int]] = {}    # week
    by_model_30d: dict[str, dict[str, int]] = {}   # month
    by_project: dict[str, int] = {}
    by_session: dict[str, int] = {}
    session_project: dict[str, str] = {}  # session_id -> project_name
    cache_today = {"read": 0, "creation": 0}

    for jsonl_path in projects_dir.glob("*/*.jsonl"):
        try:
            if jsonl_path.stat().st_mtime < cutoff_mtime:
                continue
        except OSError:
            continue

        project_name = jsonl_path.parent.name
        session_id = jsonl_path.stem

        try:
            with open(jsonl_path) as f:
                for line in f:
                    if '"usage"' not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") != "assistant":
                        continue
                    msg = entry.get("message", {})
                    usage = msg.get("usage")
                    if not usage:
                        continue
                    model = msg.get("model", "")
                    if model == "<synthetic>":
                        continue

                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    total = input_tokens + output_tokens

                    # Get timestamp for day bucketing
                    ts = entry.get("timestamp", "")
                    if not ts:
                        continue
                    # ts is ISO format like "2026-02-11T..."
                    day = ts[:10]  # "YYYY-MM-DD"

                    if day >= day30_str:
                        totals["30d"]["input"] += input_tokens
                        totals["30d"]["output"] += output_tokens
                        if model not in by_model_30d:
                            by_model_30d[model] = {"input": 0, "output": 0}
                        by_model_30d[model]["input"] += input_tokens
                        by_model_30d[model]["output"] += output_tokens
                    if day >= day7_str:
                        totals["7d"]["input"] += input_tokens
                        totals["7d"]["output"] += output_tokens
                        if model not in by_model_7d:
                            by_model_7d[model] = {"input": 0, "output": 0}
                        by_model_7d[model]["input"] += input_tokens
                        by_model_7d[model]["output"] += output_tokens
                    if day == yesterday_str:
                        totals["yesterday"]["input"] += input_tokens
                        totals["yesterday"]["output"] += output_tokens
                    if day == today_str:
                        totals["today"]["input"] += input_tokens
                        totals["today"]["output"] += output_tokens
                        # by_model with input/output split for cost estimation
                        if model not in by_model:
                            by_model[model] = {"input": 0, "output": 0}
                        by_model[model]["input"] += input_tokens
                        by_model[model]["output"] += output_tokens
                        by_project[project_name] = by_project.get(project_name, 0) + total
                        by_session[session_id] = by_session.get(session_id, 0) + total
                        session_project[session_id] = project_name
                        cache_today["read"] += usage.get("cache_read_input_tokens", 0)
                        cache_today["creation"] += usage.get("cache_creation_input_tokens", 0)
        except OSError:
            continue

    return {
        "totals": totals,
        "by_model": by_model,
        "by_model_7d": by_model_7d,
        "by_model_30d": by_model_30d,
        "by_project": by_project,
        "by_session": by_session,
        "session_project": session_project,
        "cache_today": cache_today,
    }


def _format_tokens(n: int) -> str:
    """Format token count with K/M suffix."""
    if n == 0:
        return "-"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


# Cost per 1M tokens (input, output) in USD
MODEL_COSTS = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.25, 1.25),
}


def _model_cost_key(model_id: str) -> str:
    """Map model ID to cost key (opus/sonnet/haiku)."""
    short = shorten_model_name(model_id).lower()
    for key in MODEL_COSTS:
        if key in short:
            return key
    return ""


def _estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for given model and token counts."""
    key = _model_cost_key(model_id)
    if not key:
        return 0.0
    inp_rate, out_rate = MODEL_COSTS[key]
    return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000


def _bar(fraction: float, width: int = 6) -> str:
    """Render a percentage bar like ████░░."""
    filled = round(fraction * width)
    return "█" * filled + "░" * (width - filled)


def _change_indicator(today: int, yesterday: int) -> str:
    """Return ↑/↓/→ indicator comparing today vs yesterday."""
    if yesterday == 0:
        return ""
    pct = (today - yesterday) / yesterday * 100
    if pct > 5:
        return f" ↑{pct:.0f}%"
    elif pct < -5:
        return f" ↓{abs(pct):.0f}%"
    return " →"


def _short_project_name(encoded_name: str, parts_count: int = 2) -> str:
    """Decode encoded project name and return last N path components."""
    decoded = decode_project_path(encoded_name)
    if decoded:
        parts = decoded.rstrip("/").split("/")
        return "/".join(parts[-parts_count:]) if len(parts) >= parts_count else decoded
    return encoded_name


def _total_cost(by_model_data: dict) -> float:
    """Sum estimated cost across all models in a by_model dict."""
    total = 0.0
    for model, counts in by_model_data.items():
        total += _estimate_cost(model, counts["input"], counts["output"])
    return total


def format_token_report(data: dict) -> str:
    """Format scan_token_usage output into a Telegram-friendly message."""
    totals = data.get("totals", {})
    by_model = data.get("by_model", {})
    by_model_7d = data.get("by_model_7d", {})
    by_model_30d = data.get("by_model_30d", {})
    lines = ["📊 Token Usage Report", ""]

    # Today with yesterday comparison + cost
    t_today = totals.get("today", {})
    t_yest = totals.get("yesterday", {})
    today_total = t_today.get("input", 0) + t_today.get("output", 0)
    yest_total = t_yest.get("input", 0) + t_yest.get("output", 0)
    change = _change_indicator(today_total, yest_total)
    today_cost = _total_cost(by_model)
    cost_str = f" ~${today_cost:.2f}" if today_cost > 0 else ""
    lines.append(
        f"Today: {_format_tokens(today_total)}"
        f" (in:{_format_tokens(t_today.get('input', 0))}"
        f" out:{_format_tokens(t_today.get('output', 0))}){change}{cost_str}"
    )

    for label, key, model_data in [("Week", "7d", by_model_7d), ("Month", "30d", by_model_30d)]:
        t = totals.get(key, {})
        inp = t.get("input", 0)
        out = t.get("output", 0)
        total = inp + out
        cost = _total_cost(model_data)
        cost_str = f" ~${cost:.2f}" if cost > 0 else ""
        lines.append(f"{label}: {_format_tokens(total)} (in:{_format_tokens(inp)} out:{_format_tokens(out)}){cost_str}")

    # Cache hit rate
    cache = data.get("cache_today", {})
    cr = cache.get("read", 0)
    cw = cache.get("creation", 0)
    today_input = t_today.get("input", 0)
    if cr or cw:
        hit_rate = ""
        if today_input > 0:
            rate = cr / (cr + today_input) * 100
            hit_rate = f", hit {rate:.0f}%"
        lines.append(f"Cache today: read {_format_tokens(cr)}, write {_format_tokens(cw)}{hit_rate}")

    # By Model with bar
    if by_model:
        lines.append("")
        lines.append("📦 By Model (today)")
        model_totals = {m: c["input"] + c["output"] for m, c in by_model.items()}
        grand = sum(model_totals.values()) or 1
        for model, count in sorted(model_totals.items(), key=lambda x: x[1], reverse=True):
            frac = count / grand
            pct = frac * 100
            counts = by_model[model]
            cost = _estimate_cost(model, counts["input"], counts["output"])
            lines.append(
                f"  {shorten_model_name(model)}: {_format_tokens(count)}"
                f" {_bar(frac)} {pct:.0f}%"
                + (f" ~${cost:.2f}" if cost > 0 else "")
            )

    # By Project with bar
    by_project = data.get("by_project", {})
    if by_project:
        lines.append("")
        lines.append("📁 By Project (today)")
        grand = sum(by_project.values()) or 1
        for proj, count in sorted(by_project.items(), key=lambda x: x[1], reverse=True):
            display = _short_project_name(proj, 2)
            frac = count / grand
            pct = frac * 100
            lines.append(f"  {display}: {_format_tokens(count)} {_bar(frac)} {pct:.0f}%")

    # By Session with project name
    by_session = data.get("by_session", {})
    session_project = data.get("session_project", {})
    if by_session:
        lines.append("")
        lines.append("🔗 By Session (today, top 3)")
        top3 = sorted(by_session.items(), key=lambda x: x[1], reverse=True)[:3]
        for sid, count in top3:
            proj_name = session_project.get(sid, "")
            if proj_name:
                proj_display = _short_project_name(proj_name, 1)
                lines.append(f"  {sid[:8]}… [{proj_display}]: {_format_tokens(count)}")
            else:
                lines.append(f"  {sid[:8]}…: {_format_tokens(count)}")

    return "\n".join(lines)


def decode_project_path(encoded_name: str, exists_fn=os.path.isdir) -> str | None:
    """Decode project directory name back to path (best effort).

    Claude Code encodes /Users/foo/my-app -> -Users-foo-my-app
    The challenge is that hyphens in folder names (my-app) look identical
    to path separators. We use greedy filesystem matching to resolve this.

    Args:
        exists_fn: callable to test directory existence (default: os.path.isdir).
    """
    name = encoded_name.lstrip("-")

    # Fast path: simple replacement works
    simple = "/" + name.replace("-", "/")
    if exists_fn(simple):
        return simple

    # Greedy match: split by '-' and try to reconstruct by testing filesystem
    parts = name.split("-")
    if not parts:
        return None

    current = ""
    i = 0
    while i < len(parts):
        # Try joining remaining parts with '-' (greedy: longest match first)
        found = False
        for j in range(len(parts), i, -1):
            candidate = current + "/" + "-".join(parts[i:j])
            if exists_fn(candidate):
                current = candidate
                i = j
                found = True
                break
        if not found:
            # Single part as path component
            current = current + "/" + parts[i]
            i += 1

    if exists_fn(current):
        return current
    return None


def get_project_path_for_session(session_id: str) -> str | None:
    """Find the project path for a given session ID."""
    projects_dir = _get_projects_dir()
    if not projects_dir:
        return None
    for jsonl in projects_dir.glob("*/*.jsonl"):
        if jsonl.stem == session_id:
            return decode_project_path(jsonl.parent.name)
    return None



def get_current_session_id():
    """Get current session ID with cross-validation for reliability."""
    title_sid = tmux_get_title()
    file_sid = None

    # Read from current session file
    if os.path.exists(CURRENT_SESSION_FILE):
        try:
            with open(CURRENT_SESSION_FILE) as f:
                file_sid = f.read().strip()
        except OSError:
            pass

    # If both match, high confidence
    if title_sid and title_sid == file_sid:
        return title_sid

    # Get most recently modified session file as ground truth
    projects_dir = _get_projects_dir()
    recent_sid = None
    if projects_dir:
        all_jsonls = list(projects_dir.glob("*/*.jsonl"))
        if all_jsonls:
            most_recent = max(all_jsonls, key=lambda p: p.stat().st_mtime)
            recent_sid = most_recent.stem

    # Prefer tmux title if it matches recent file
    if title_sid and title_sid == recent_sid:
        return title_sid

    # Prefer file_sid if it matches recent file
    if file_sid and file_sid == recent_sid:
        return file_sid

    # Fallback: use recent file (most reliable ground truth)
    if recent_sid:
        return recent_sid

    # Last resort: use whatever we have
    return title_sid or file_sid


def load_session_chat_map() -> dict[str, str]:
    """Load session-to-chat mapping from file."""
    if not os.path.exists(SESSION_CHAT_MAP_FILE):
        return {}
    try:
        with open(SESSION_CHAT_MAP_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_session_chat_map(mapping: dict[str, str]) -> None:
    """Save session-to-chat mapping to file."""
    try:
        with open(SESSION_CHAT_MAP_FILE, "w") as f:
            json.dump(mapping, f, indent=2)
    except OSError as e:
        print(f"Failed to save session-chat map: {e}")


def bind_session_to_chat(session_id: str, chat_id: int) -> None:
    """Bind a session ID to a Telegram chat ID."""
    if not session_id:
        return
    mapping = load_session_chat_map()
    mapping[session_id] = str(chat_id)
    save_session_chat_map(mapping)
    # Also save current session ID for hooks to use
    try:
        with open(CURRENT_SESSION_FILE, "w") as f:
            f.write(session_id)
    except OSError:
        pass


def get_chat_id_for_session(session_id: str) -> str | None:
    """Get the chat ID bound to a session."""
    if not session_id:
        return None
    mapping = load_session_chat_map()
    return mapping.get(session_id)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            update = json.loads(body)
            if "callback_query" in update:
                self.handle_callback(update["callback_query"])
            elif "message" in update:
                self.handle_message(update)
        except Exception as e:
            print(f"Error: {e}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Claude-Telegram Bridge")

    # --- Session operation helpers ---

    def resume_and_bind(self, session_id: str, chat_id: int, action: str = "✅ Resumed") -> None:
        """Switch to session, set title, bind to chat, and reply."""
        project_path = get_project_path_for_session(session_id)
        tmux_switch_session(session_id)
        tmux_set_title(session_id)
        bind_session_to_chat(session_id, chat_id)
        self.reply(chat_id, format_session_message(action, session_id, project_path))

    def start_new_and_bind(self, chat_id: int, project_path: str | None = None) -> None:
        """Detect new session after tmux_new_session, bind and reply."""
        current_sid = get_current_session_id()
        if current_sid:
            tmux_set_title(current_sid)
            bind_session_to_chat(current_sid, chat_id)
            self.reply(chat_id, format_session_message("🟢 New session", current_sid, project_path))
        else:
            self.reply(chat_id, "⚠️ Starting... (session detection pending)")

    def resolve_project_hash(self, ph: str, chat_id: int) -> tuple[str, str, str | None] | None:
        """Resolve hash -> (encoded_name, real_name, project_path). None if expired."""
        encoded_name = project_from_hash(ph)
        if not encoded_name:
            self.reply(chat_id, "Session expired. Use /projects again.")
            return None
        resolved_dir = resolve_project_dir(encoded_name)
        real_name = resolved_dir.name if resolved_dir else encoded_name
        project_path = decode_project_path(real_name)
        return encoded_name, real_name, project_path

    # --- Callback handler ---

    def handle_callback(self, cb: dict[str, Any]) -> None:
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        data = cb.get("data", "")
        telegram_api("answerCallbackQuery", {"callback_query_id": cb.get("id")})

        if not tmux_exists():
            self.reply(chat_id, "tmux session not found")
            return

        if data.startswith(CB_RESUME):
            session_id = parse_callback_data(data, CB_RESUME)
            if session_id:
                self.resume_and_bind(session_id, chat_id)

        elif data == CB_CONTINUE_RECENT:
            sessions = get_recent_sessions_from_files(limit=1)
            if not sessions:
                self.reply(chat_id, "No sessions found")
                return
            self.resume_and_bind(sessions[0]["session_id"], chat_id, "✅ Continuing")

        elif data.startswith(CB_PROJECT):
            ph = parse_callback_data(data, CB_PROJECT)
            if not ph:
                return
            result = self.resolve_project_hash(ph, chat_id)
            if not result:
                return
            encoded_name, real_name, project_path = result
            sessions = get_sessions_for_project(encoded_name, limit=8)
            if not sessions:
                self.reply(chat_id, "No sessions in this project")
                return
            header = f"📁 {project_path or real_name}\n\nSessions:"
            nph = project_hash(encoded_name)
            kb = [[{"text": "🆕 New session", "callback_data": f"{CB_NEW_IN_PROJECT}{nph}"}]]
            for s in sessions:
                sid = s["session_id"]
                ts = datetime.fromtimestamp(s["mtime"]).strftime("%m-%d %H:%M")
                kb.append([{"text": f"{sid} | {ts}", "callback_data": f"{CB_RESUME}{sid}"}])
            self.reply_keyboard(chat_id, header, kb)

        elif data.startswith(CB_ASK_ANSWER):
            idx_str = parse_callback_data(data, CB_ASK_ANSWER)
            if idx_str is None:
                return
            try:
                idx = int(idx_str)
            except ValueError:
                return
            if not tmux_exists():
                self.reply(chat_id, "tmux session not found")
                return
            for _ in range(idx):
                tmux_send("Down", literal=False)
                time.sleep(0.15)
            time.sleep(0.2)
            tmux_send_enter()
            self.reply(chat_id, f"✅ Selected option {idx + 1}")

        elif data.startswith(CB_NEW_IN_PROJECT):
            ph = parse_callback_data(data, CB_NEW_IN_PROJECT)
            if not ph:
                return
            result = self.resolve_project_hash(ph, chat_id)
            if not result:
                return
            encoded_name, real_name, project_path = result
            clear_sync_flags()
            if project_path:
                current_cwd = tmux_get_cwd()
                if current_cwd and os.path.realpath(project_path) != os.path.realpath(current_cwd):
                    tmux_exit_claude()
                    tmux_cd_and_start(project_path)
                else:
                    tmux_new_session()
            else:
                tmux_new_session()
            self.start_new_and_bind(chat_id, project_path)

    # --- Command handlers ---

    def _cmd_status(self, chat_id: int, text: str) -> None:
        status = "✅ running" if tmux_exists() else "❌ not found"
        current_sid = get_current_session_id()
        bound_chat = get_chat_id_for_session(current_sid) if current_sid else None
        state = get_sync_state()
        sync_status = f"{SYNC_STATE_ICONS[state]} {state}"
        msg = f"tmux '{TMUX_SESSION}': {status}"
        msg += f"\nSync: {sync_status}"
        if current_sid:
            msg += f"\nSession: {current_sid}"
            if bound_chat == str(chat_id):
                msg += f"\n✅ Bound to this chat"
            elif bound_chat:
                msg += f"\n⚠️ Bound to different chat: {bound_chat}"
            else:
                msg += f"\n⚠️ Not bound. Use /bind to connect"
        else:
            msg += "\n⚠️ No active session"
        self.reply(chat_id, msg)

    def _cmd_start(self, chat_id: int, text: str) -> None:
        if not tmux_exists():
            self.reply(chat_id, "tmux session not found.\nUse start.sh --new to create one.")
            return
        clear_sync_flags()
        tmux_new_session()
        self.start_new_and_bind(chat_id)

    def _cmd_stop(self, chat_id: int, text: str) -> None:
        try:
            with open(SYNC_PAUSED_FILE, "w") as f:
                f.write(str(int(time.time())))
            if os.path.exists(PENDING_FILE):
                os.remove(PENDING_FILE)
            self.reply(chat_id, "🟡 Sync paused.\n\nUse /start, /resume, or /continue to resume.")
        except OSError as e:
            self.reply(chat_id, f"Failed to pause: {e}")

    def _cmd_escape(self, chat_id: int, text: str) -> None:
        if tmux_exists():
            tmux_send_escape()
            time.sleep(0.2)
            tmux_send("C-c", literal=False)
        if os.path.exists(PENDING_FILE):
            os.remove(PENDING_FILE)
        self.reply(chat_id, "Interrupted")

    def _cmd_terminate(self, chat_id: int, text: str) -> None:
        try:
            with open(SYNC_DISABLED_FILE, "w") as f:
                f.write(str(int(time.time())))
            for fp in (SYNC_PAUSED_FILE, PENDING_FILE):
                if os.path.exists(fp):
                    os.remove(fp)
            self.reply(chat_id, "🔴 Sync terminated.\n\nUse /start to reconnect.")
        except OSError as e:
            self.reply(chat_id, f"Failed to terminate: {e}")

    def _cmd_bind(self, chat_id: int, text: str) -> None:
        current_sid = get_current_session_id()
        if not current_sid:
            self.reply(chat_id, "No active session found")
            return
        tmux_set_title(current_sid)
        bind_session_to_chat(current_sid, chat_id)
        self.reply(chat_id, f"Bound session {current_sid} to this chat")

    def _cmd_clear(self, chat_id: int, text: str) -> None:
        if not tmux_exists():
            self.reply(chat_id, "tmux not found")
            return
        tmux_send_escape()
        time.sleep(0.2)
        tmux_send_line("/clear")
        self.reply(chat_id, "Cleared")

    def _cmd_continue(self, chat_id: int, text: str) -> None:
        clear_sync_flags()
        if not tmux_exists():
            self.reply(chat_id, "tmux not found")
            return
        sessions = get_recent_sessions_from_files(limit=1)
        if not sessions:
            self.reply(chat_id, "No sessions found")
            return
        self.resume_and_bind(sessions[0]["session_id"], chat_id, "✅ Continuing")

    def _cmd_loop(self, chat_id: int, text: str) -> None:
        if not tmux_exists():
            self.reply(chat_id, "tmux not found")
            return
        current_sid = get_current_session_id()
        bound_chat = get_chat_id_for_session(current_sid) if current_sid else None
        if not bound_chat or bound_chat != str(chat_id):
            self.reply(chat_id, "⚠️ Not bound. Use /bind first.")
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            self.reply(chat_id, "Usage: /loop <prompt>")
            return
        prompt = parts[1].replace('"', '\\"')
        full = f'{prompt} Output <promise>DONE</promise> when complete.'
        _start_typing(chat_id)
        tmux_send_line(f'/ralph-loop:ralph-loop "{full}" --max-iterations 5 --completion-promise "DONE"')
        time.sleep(0.3)
        self.reply(chat_id, "Ralph Loop started (max 5 iterations)")

    def _cmd_resume(self, chat_id: int, text: str) -> None:
        clear_sync_flags()
        sessions = get_recent_sessions_from_files(limit=8)
        if not sessions:
            self.reply(chat_id, "No sessions found")
            return
        kb = [[{"text": "▶️ Continue most recent", "callback_data": CB_CONTINUE_RECENT}]]
        for s in sessions:
            sid = s["session_id"]
            proj_decoded = decode_project_path(s["project_dir"]) or s["project_dir"]
            kb.append([{"text": f"📁 {proj_decoded}\n{sid}", "callback_data": f"{CB_RESUME}{sid}"}])
        self.reply_keyboard(chat_id, "Select session to resume:", kb)

    def _cmd_projects(self, chat_id: int, text: str) -> None:
        projects = get_projects(limit=8)
        if not projects:
            self.reply(chat_id, "No projects found")
            return
        kb = []
        for p in projects:
            name = p["encoded_name"]
            ph = project_hash(name)
            decoded = decode_project_path(name)
            display = decoded if decoded else name
            kb.append([{"text": f"📁 {display} ({p['session_count']})", "callback_data": f"{CB_PROJECT}{ph}"}])
        self.reply_keyboard(chat_id, "Select a project:", kb)

    def _cmd_report(self, chat_id: int, text: str) -> None:
        self.reply(chat_id, "Scanning sessions...")
        data = scan_token_usage()
        self.reply(chat_id, format_token_report(data))

    _COMMANDS: dict[str, Any] = {
        "/status": _cmd_status,
        "/start": _cmd_start,
        "/stop": _cmd_stop,
        "/escape": _cmd_escape,
        "/terminate": _cmd_terminate,
        "/bind": _cmd_bind,
        "/clear": _cmd_clear,
        "/continue": _cmd_continue,
        "/loop": _cmd_loop,
        "/resume": _cmd_resume,
        "/projects": _cmd_projects,
        "/report": _cmd_report,
    }

    # --- Message handler ---

    def handle_message(self, update: dict[str, Any]) -> None:
        msg: dict[str, Any] = update.get("message", {})
        text: str = msg.get("text", "")
        chat_id: int | None = msg.get("chat", {}).get("id")
        if not text or not chat_id:
            return

        with open(CHAT_ID_FILE, "w") as f:
            f.write(str(chat_id))

        if text.startswith("/"):
            cmd = text.split()[0].lower()
            handler = self._COMMANDS.get(cmd)
            if handler:
                handler(self, chat_id, text)
                return
            if cmd in BLOCKED_COMMANDS:
                self.reply(chat_id, f"'{cmd}' not supported (interactive)")
                return

        self._handle_regular_message(chat_id, text)

    def _handle_regular_message(self, chat_id: int, text: str) -> None:
        print(f"[{chat_id}] {text[:50]}...")

        state = get_sync_state()
        if state != SYNC_STATE_ACTIVE:
            self.reply(chat_id, SYNC_STATE_MESSAGES[state])
            return

        if not tmux_exists():
            self.reply(chat_id, "tmux not found. Start a session first.")
            return

        current_sid = get_current_session_id()
        if current_sid:
            bound_chat = get_chat_id_for_session(current_sid)
            if not bound_chat:
                bind_session_to_chat(current_sid, chat_id)
                tmux_set_title(current_sid)
            elif bound_chat != str(chat_id):
                self.reply(chat_id, "⚠️ Session bound to another chat.\nUse /bind to rebind.")
                return

        _start_typing(chat_id)
        tmux_send(text)
        time.sleep(0.1)
        tmux_send_enter()

    def reply(self, chat_id: int, text: str) -> None:
        telegram_api("sendMessage", {"chat_id": chat_id, "text": text})

    def reply_keyboard(self, chat_id: int, text: str, keyboard: list) -> None:
        """Send a message with an inline keyboard."""
        telegram_api("sendMessage", {
            "chat_id": chat_id, "text": text,
            "reply_markup": {"inline_keyboard": keyboard}
        })

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def session_poller():
    """Background poller: detect new sessions and auto-bind to current chat."""
    last_known_sid = None
    while True:
        time.sleep(5)
        try:
            current_sid = get_current_session_id()
            if current_sid and current_sid != last_known_sid:
                last_known_sid = current_sid
                if not get_chat_id_for_session(current_sid):
                    if os.path.exists(CHAT_ID_FILE):
                        with open(CHAT_ID_FILE) as f:
                            cid = f.read().strip()
                        if cid:
                            bind_session_to_chat(current_sid, int(cid))
                            tmux_set_title(current_sid)
        except Exception:
            pass


def main():
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set")
        return
    setup_bot_commands()
    # Start background session poller
    threading.Thread(target=session_poller, daemon=True).start()
    print(f"Bridge on :{PORT} | tmux: {TMUX_SESSION}")
    try:
        HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
