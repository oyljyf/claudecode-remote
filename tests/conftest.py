"""Shared fixtures for claudecode-telegram tests."""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_claude_dir(tmp_path, monkeypatch):
    """Provide a temporary ~/.claude/ equivalent and monkeypatch all *_FILE constants."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "projects").mkdir()
    (claude_dir / "hooks").mkdir()
    (claude_dir / "logs").mkdir()

    import bridge

    monkeypatch.setattr(bridge, "CHAT_ID_FILE", str(claude_dir / "telegram_chat_id"))
    monkeypatch.setattr(bridge, "PENDING_FILE", str(claude_dir / "telegram_pending"))
    monkeypatch.setattr(bridge, "HISTORY_FILE", str(claude_dir / "history.jsonl"))
    monkeypatch.setattr(bridge, "SESSION_CHAT_MAP_FILE", str(claude_dir / "session_chat_map.json"))
    monkeypatch.setattr(bridge, "CURRENT_SESSION_FILE", str(claude_dir / "current_session_id"))
    monkeypatch.setattr(bridge, "SYNC_DISABLED_FILE", str(claude_dir / "telegram_sync_disabled"))
    monkeypatch.setattr(bridge, "SYNC_PAUSED_FILE", str(claude_dir / "telegram_sync_paused"))
    monkeypatch.setattr(bridge, "PERM_PENDING_FILE", str(claude_dir / "pending_permission.json"))
    monkeypatch.setattr(bridge, "PERM_RESPONSE_FILE", str(claude_dir / "permission_response.json"))

    # Patch Path.home() so functions using Path.home() / ".claude" / "projects" hit our temp dir
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    return claude_dir


@pytest.fixture
def fake_session_files(tmp_claude_dir):
    """Create realistic .jsonl session files with controlled mtimes."""
    projects_dir = tmp_claude_dir / "projects"

    def _create(project_name, sessions, base_time=None):
        """Create session files.

        Args:
            project_name: encoded project directory name (e.g. "-Users-foo-myapp")
            sessions: list of (session_id, age_seconds) tuples
            base_time: reference time (defaults to now)
        """
        if base_time is None:
            base_time = time.time()
        proj_dir = projects_dir / project_name
        proj_dir.mkdir(parents=True, exist_ok=True)
        created = []
        for sid, age in sessions:
            p = proj_dir / f"{sid}.jsonl"
            p.write_text(json.dumps({"type": "user", "message": "hello"}) + "\n")
            mtime = base_time - age
            os.utime(p, (mtime, mtime))
            created.append(p)
        return created

    return _create


@pytest.fixture
def mock_telegram_api(monkeypatch):
    """Capture telegram_api calls instead of making HTTP requests."""
    import bridge

    calls = []

    def _fake_api(method, data):
        calls.append({"method": method, "data": data})
        return {"ok": True, "result": True}

    monkeypatch.setattr(bridge, "telegram_api", _fake_api)
    return calls


@pytest.fixture
def mock_tmux(monkeypatch):
    """Patch subprocess calls for tmux, returning controlled values."""
    import subprocess as sp

    state = {
        "exists": True,
        "pane_content": "user@host $",
        "cwd": "/Users/test/project",
        "title": None,
        "calls": [],
    }

    original_run = sp.run

    def _fake_run(cmd, *args, **kwargs):
        state["calls"].append(cmd)

        if not isinstance(cmd, list) or not cmd or cmd[0] != "tmux":
            return original_run(cmd, *args, **kwargs)

        subcmd = cmd[1] if len(cmd) > 1 else ""

        if subcmd == "has-session":
            rc = 0 if state["exists"] else 1
            return sp.CompletedProcess(cmd, rc, stdout="", stderr="")

        if subcmd == "capture-pane":
            return sp.CompletedProcess(cmd, 0, stdout=state["pane_content"] + "\n", stderr="")

        if subcmd == "display-message":
            # pane_current_path or window_name
            fmt = cmd[-1] if cmd else ""
            if "pane_current_path" in fmt:
                return sp.CompletedProcess(cmd, 0, stdout=state["cwd"] + "\n", stderr="")
            if "window_name" in fmt:
                val = state["title"] or ""
                return sp.CompletedProcess(cmd, 0, stdout=val + "\n", stderr="")
            return sp.CompletedProcess(cmd, 0, stdout="\n", stderr="")

        if subcmd in ("send-keys", "rename-window"):
            return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

        return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(sp, "run", _fake_run)
    return state
