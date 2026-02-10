#!/usr/bin/env python3
"""Claude Code <-> Telegram Bridge"""

import hashlib
import os
import json
import shlex
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
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
HISTORY_FILE = os.path.expanduser("~/.claude/history.jsonl")
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
PERM_PENDING_FILE = os.path.expanduser("~/.claude/pending_permission.json")
PERM_RESPONSE_FILE = os.path.expanduser("~/.claude/permission_response.json")

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


def tmux_exists():
    return subprocess.run(["tmux", "has-session", "-t", TMUX_SESSION], capture_output=True).returncode == 0


def tmux_send(text, literal=True):
    cmd = ["tmux", "send-keys", "-t", TMUX_SESSION]
    if literal:
        cmd.append("-l")
    cmd.append(text)
    subprocess.run(cmd)


def tmux_send_enter():
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "Enter"])


def tmux_send_escape():
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "Escape"])


def tmux_get_pane_content(lines=3) -> str:
    """Get the last N lines of the tmux pane to detect state."""
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", TMUX_SESSION, "-p", "-S", f"-{lines}"],
        capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def tmux_is_at_shell() -> bool:
    """Check if tmux pane is at a shell prompt (Claude exited)."""
    return is_shell_prompt(tmux_get_pane_content(3))


def tmux_get_cwd() -> str | None:
    """Get the current working directory of the tmux pane."""
    result = subprocess.run(
        ["tmux", "display-message", "-t", TMUX_SESSION, "-p", "#{pane_current_path}"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def tmux_exit_claude() -> None:
    """Exit Claude in the tmux pane, returning to shell prompt."""
    tmux_send_escape()
    time.sleep(0.3)
    tmux_send("/exit")
    tmux_send_enter()
    time.sleep(1.0)
    # If Claude didn't exit, force it
    if not tmux_is_at_shell():
        tmux_send_escape()
        time.sleep(0.2)
        tmux_send("exit")
        tmux_send_enter()
        time.sleep(0.5)


def tmux_cd_and_start(target_path: str, resume_session_id: str | None = None) -> None:
    """cd to target_path and start Claude, optionally resuming a session."""
    tmux_send(f"cd {shlex.quote(target_path)}")
    tmux_send_enter()
    time.sleep(0.3)
    if resume_session_id:
        tmux_send(f"claude --resume {resume_session_id} --dangerously-skip-permissions")
    else:
        tmux_send("claude --dangerously-skip-permissions")
    tmux_send_enter()
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
        tmux_send(f"/resume {session_id}")
        tmux_send_enter()
        time.sleep(2.0)

        # Check if Claude exited (returned to shell prompt)
        if tmux_is_at_shell():
            if target_path:
                tmux_cd_and_start(target_path, resume_session_id=session_id)
            else:
                tmux_send(f"claude --resume {session_id} --dangerously-skip-permissions")
                tmux_send_enter()
                time.sleep(2.0)


def tmux_new_session() -> None:
    """Start a new Claude session, handling both in-process and restart cases."""
    tmux_send_escape()
    time.sleep(0.3)
    tmux_send("/clear")
    tmux_send_enter()
    time.sleep(1.5)

    # Check if Claude exited
    if tmux_is_at_shell():
        tmux_send("claude --dangerously-skip-permissions")
        tmux_send_enter()
        time.sleep(2.0)


def tmux_set_title(title: str) -> None:
    """Set the tmux window title to track current session."""
    subprocess.run(["tmux", "rename-window", "-t", TMUX_SESSION, title], capture_output=True)


def tmux_get_title() -> str | None:
    """Get the current tmux window title (used as session ID)."""
    result = subprocess.run(
        ["tmux", "display-message", "-t", TMUX_SESSION, "-p", "#{window_name}"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return filter_window_title(result.stdout.strip())
    return None


def get_recent_sessions(limit=5):
    """Get recent sessions from history file (legacy)."""
    if not os.path.exists(HISTORY_FILE):
        return []
    sessions = []
    try:
        with open(HISTORY_FILE) as f:
            for line in f:
                try:
                    sessions.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
        return []
    sessions.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return sessions[:limit]


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
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
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
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
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
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
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
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return None
    for jsonl in projects_dir.glob("*/*.jsonl"):
        if jsonl.stem == session_id:
            return decode_project_path(jsonl.parent.name)
    return None


def get_session_id(project_path):
    encoded = project_path.replace("/", "-").lstrip("-")
    for prefix in [f"-{encoded}", encoded]:
        project_dir = Path.home() / ".claude" / "projects" / prefix
        if project_dir.exists():
            jsonls = list(project_dir.glob("*.jsonl"))
            if jsonls:
                return max(jsonls, key=lambda p: p.stat().st_mtime).stem
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
    projects_dir = Path.home() / ".claude" / "projects"
    recent_sid = None
    if projects_dir.exists():
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

    def handle_callback(self, cb: dict[str, Any]) -> None:
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        data = cb.get("data", "")
        telegram_api("answerCallbackQuery", {"callback_query_id": cb.get("id")})

        if not tmux_exists():
            self.reply(chat_id, "tmux session not found")
            return

        if data.startswith(CB_RESUME):
            session_id = parse_callback_data(data, CB_RESUME)
            if not session_id:
                return
            project_path = get_project_path_for_session(session_id)

            # Switch session (auto-handles Claude exit + restart)
            tmux_switch_session(session_id)

            tmux_set_title(session_id)
            bind_session_to_chat(session_id, chat_id)
            self.reply(chat_id, format_session_message("✅ Resumed", session_id, project_path))

        elif data == CB_CONTINUE_RECENT:
            sessions = get_recent_sessions_from_files(limit=1)
            if not sessions:
                self.reply(chat_id, "No sessions found")
                return
            expected_sid = sessions[0]["session_id"]
            project_path = get_project_path_for_session(expected_sid)

            tmux_switch_session(expected_sid)

            tmux_set_title(expected_sid)
            bind_session_to_chat(expected_sid, chat_id)
            self.reply(chat_id, format_session_message("✅ Continuing", expected_sid, project_path))

        elif data.startswith(CB_PROJECT):
            ph = parse_callback_data(data, CB_PROJECT)
            if not ph:
                return
            encoded_name = project_from_hash(ph)
            if not encoded_name:
                self.reply(chat_id, "Session expired. Use /projects again.")
                return
            resolved_dir = resolve_project_dir(encoded_name)
            real_name = resolved_dir.name if resolved_dir else encoded_name
            sessions = get_sessions_for_project(encoded_name, limit=8)
            if not sessions:
                self.reply(chat_id, "No sessions in this project")
                return
            project_path = decode_project_path(real_name)
            header = f"📁 {project_path or real_name}\n\nSessions:"
            # Re-hash to keep cache alive for new_in_project
            nph = project_hash(encoded_name)
            kb = [[{"text": "🆕 New session", "callback_data": f"{CB_NEW_IN_PROJECT}{nph}"}]]
            for s in sessions:
                sid = s["session_id"]
                ts = datetime.fromtimestamp(s["mtime"]).strftime("%m-%d %H:%M")
                label = f"{sid} | {ts}"
                kb.append([{"text": label, "callback_data": f"{CB_RESUME}{sid}"}])
            telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": header,
                "reply_markup": {"inline_keyboard": kb}
            })

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
            # Navigate TUI: Down × idx to reach the option, then Enter to select
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
            encoded_name = project_from_hash(ph)
            if not encoded_name:
                self.reply(chat_id, "Session expired. Use /projects again.")
                return
            resolved_dir = resolve_project_dir(encoded_name)
            real_name = resolved_dir.name if resolved_dir else encoded_name
            project_path = decode_project_path(real_name)
            clear_sync_flags()
            # cd to target project before starting new session
            if project_path:
                current_cwd = tmux_get_cwd()
                if current_cwd and os.path.realpath(project_path) != os.path.realpath(current_cwd):
                    tmux_exit_claude()
                    tmux_cd_and_start(project_path)
                else:
                    tmux_new_session()
            else:
                tmux_new_session()
            current_sid = get_current_session_id()
            if current_sid:
                tmux_set_title(current_sid)
                bind_session_to_chat(current_sid, chat_id)
                self.reply(chat_id, format_session_message("🟢 New session", current_sid, project_path))
            else:
                self.reply(chat_id, "⚠️ Starting... (session detection pending)")

    def handle_message(self, update: dict[str, Any]) -> None:
        msg: dict[str, Any] = update.get("message", {})
        text: str = msg.get("text", "")
        chat_id: int | None = msg.get("chat", {}).get("id")
        _msg_id: int | None = msg.get("message_id")  # noqa: F841
        if not text or not chat_id:
            return

        with open(CHAT_ID_FILE, "w") as f:
            f.write(str(chat_id))

        if text.startswith("/"):
            cmd = text.split()[0].lower()

            if cmd == "/status":
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
                return

            if cmd == "/start":
                # Start a new conversation
                if not tmux_exists():
                    self.reply(chat_id, "tmux session not found.\nUse start.sh --new to create one.")
                    return
                clear_sync_flags()
                # Start fresh (auto-handles Claude exit + restart)
                tmux_new_session()
                current_sid = get_current_session_id()
                if current_sid:
                    tmux_set_title(current_sid)
                    bind_session_to_chat(current_sid, chat_id)
                    self.reply(chat_id, f"🟢 New session started: {current_sid}")
                else:
                    self.reply(chat_id, "⚠️ Starting... (session detection pending)")
                return

            if cmd == "/stop":
                # Pause sync (recoverable with /start or /resume)
                try:
                    with open(SYNC_PAUSED_FILE, "w") as f:
                        f.write(str(int(time.time())))
                    if os.path.exists(PENDING_FILE):
                        os.remove(PENDING_FILE)
                    self.reply(chat_id, "🟡 Sync paused.\n\nUse /start, /resume, or /continue to resume.")
                except OSError as e:
                    self.reply(chat_id, f"Failed to pause: {e}")
                return

            if cmd == "/escape":
                # Send Escape to interrupt Claude
                if tmux_exists():
                    tmux_send_escape()
                if os.path.exists(PENDING_FILE):
                    os.remove(PENDING_FILE)
                self.reply(chat_id, "Interrupted (Escape sent)")
                return

            if cmd == "/terminate":
                # Fully disconnect (need /start to reconnect)
                try:
                    with open(SYNC_DISABLED_FILE, "w") as f:
                        f.write(str(int(time.time())))
                    # Also remove paused and pending files
                    for fp in (SYNC_PAUSED_FILE, PENDING_FILE):
                        if os.path.exists(fp):
                            os.remove(fp)
                    self.reply(chat_id, "🔴 Sync terminated.\n\nUse /start to reconnect.")
                except OSError as e:
                    self.reply(chat_id, f"Failed to terminate: {e}")
                return

            if cmd == "/bind":
                # Get session ID from file (not title) since we're binding a new session
                projects_dir = Path.home() / ".claude" / "projects"
                all_jsonls = list(projects_dir.glob("*/*.jsonl")) if projects_dir.exists() else []
                current_sid = max(all_jsonls, key=lambda p: p.stat().st_mtime).stem if all_jsonls else None
                if not current_sid:
                    self.reply(chat_id, "No active session found")
                    return
                tmux_set_title(current_sid)
                bind_session_to_chat(current_sid, chat_id)
                self.reply(chat_id, f"Bound session {current_sid} to this chat")
                return

            if cmd == "/clear":
                if not tmux_exists():
                    self.reply(chat_id, "tmux not found")
                    return
                tmux_send_escape()
                time.sleep(0.2)
                tmux_send("/clear")
                tmux_send_enter()
                self.reply(chat_id, "Cleared")
                return

            if cmd == "/continue":
                clear_sync_flags()
                if not tmux_exists():
                    self.reply(chat_id, "tmux not found")
                    return
                sessions = get_recent_sessions_from_files(limit=1)
                if not sessions:
                    self.reply(chat_id, "No sessions found")
                    return
                sid = sessions[0]["session_id"]
                project_path = get_project_path_for_session(sid)

                tmux_switch_session(sid)

                tmux_set_title(sid)
                bind_session_to_chat(sid, chat_id)
                self.reply(chat_id, format_session_message("✅ Continuing", sid, project_path))
                return

            if cmd == "/loop":
                if not tmux_exists():
                    self.reply(chat_id, "tmux not found")
                    return
                # Check binding
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
                with open(PENDING_FILE, "w") as f:
                    f.write(str(int(time.time())))
                threading.Thread(target=send_typing_loop, args=(chat_id,), daemon=True).start()
                tmux_send(f'/ralph-loop:ralph-loop "{full}" --max-iterations 5 --completion-promise "DONE"')
                time.sleep(0.3)
                tmux_send_enter()
                self.reply(chat_id, "Ralph Loop started (max 5 iterations)")
                return

            if cmd == "/resume":
                clear_sync_flags()
                # Use file-based session discovery (more reliable than history.jsonl)
                sessions = get_recent_sessions_from_files(limit=8)
                if not sessions:
                    self.reply(chat_id, "No sessions found")
                    return
                kb = [[{"text": "▶️ Continue most recent", "callback_data": CB_CONTINUE_RECENT}]]
                for s in sessions:
                    sid = s["session_id"]
                    proj_decoded = decode_project_path(s["project_dir"]) or s["project_dir"]
                    label = f"📁 {proj_decoded}\n{sid}"
                    kb.append([{"text": label, "callback_data": f"{CB_RESUME}{sid}"}])
                telegram_api("sendMessage", {
                    "chat_id": chat_id,
                    "text": "Select session to resume:",
                    "reply_markup": {"inline_keyboard": kb}
                })
                return

            if cmd == "/projects":
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
                    label = f"📁 {display} ({p['session_count']})"
                    kb.append([{"text": label, "callback_data": f"{CB_PROJECT}{ph}"}])
                telegram_api("sendMessage", {
                    "chat_id": chat_id,
                    "text": "Select a project:",
                    "reply_markup": {"inline_keyboard": kb}
                })
                return

            if cmd in BLOCKED_COMMANDS:
                self.reply(chat_id, f"'{cmd}' not supported (interactive)")
                return

        # Regular message
        print(f"[{chat_id}] {text[:50]}...")

        # Check sync state
        state = get_sync_state()
        if state != SYNC_STATE_ACTIVE:
            self.reply(chat_id, SYNC_STATE_MESSAGES[state])
            return

        if not tmux_exists():
            self.reply(chat_id, "tmux not found. Start a session first.")
            return

        # Auto-detect and bind session
        current_sid = get_current_session_id()
        if current_sid:
            bound_chat = get_chat_id_for_session(current_sid)
            if not bound_chat:
                # Unbound session → auto-bind
                bind_session_to_chat(current_sid, chat_id)
                tmux_set_title(current_sid)
            elif bound_chat != str(chat_id):
                self.reply(chat_id, "⚠️ Session bound to another chat.\nUse /bind to rebind.")
                return

        with open(PENDING_FILE, "w") as f:
            f.write(str(int(time.time())))

        threading.Thread(target=send_typing_loop, args=(chat_id,), daemon=True).start()
        tmux_send(text)
        time.sleep(0.1)  # Small delay to ensure text is received before Enter
        tmux_send_enter()

    def reply(self, chat_id: int, text: str) -> None:
        telegram_api("sendMessage", {"chat_id": chat_id, "text": text})

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
