"""Tests for the HTTP handler in bridge.py."""

import json
import os
import time
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

import bridge


def _make_update(text, chat_id=123, message_id=1):
    """Build a Telegram update dict."""
    return {
        "message": {
            "text": text,
            "chat": {"id": chat_id},
            "message_id": message_id,
        }
    }


def _make_handler(mock_tmux, mock_telegram_api):
    """Create a Handler instance with mocked I/O."""
    handler = bridge.Handler.__new__(bridge.Handler)
    handler.reply = MagicMock()
    return handler


class TestStatusCommand:
    def test_tmux_up_active(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj", [("sess1", 5)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/status"))
        handler.reply.assert_called_once()
        msg = handler.reply.call_args[0][1]
        assert "running" in msg
        assert "active" in msg

    def test_tmux_down(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        mock_tmux["exists"] = False
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/status"))
        msg = handler.reply.call_args[0][1]
        assert "not found" in msg

    def test_paused(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        with open(bridge.SYNC_PAUSED_FILE, "w") as f:
            f.write("1")
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/status"))
        msg = handler.reply.call_args[0][1]
        assert "paused" in msg

    def test_terminated(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        with open(bridge.SYNC_DISABLED_FILE, "w") as f:
            f.write("1")
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/status"))
        msg = handler.reply.call_args[0][1]
        assert "terminated" in msg


class TestStartCommand:
    def test_tmux_exists(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj", [("newsess", 1)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/start"))
        handler.reply.assert_called_once()
        msg = handler.reply.call_args[0][1]
        assert "New session" in msg or "Starting" in msg

    def test_tmux_missing(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        mock_tmux["exists"] = False
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/start"))
        msg = handler.reply.call_args[0][1]
        assert "not found" in msg


class TestStopCommand:
    def test_creates_paused_flag(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/stop"))
        assert os.path.exists(bridge.SYNC_PAUSED_FILE)
        msg = handler.reply.call_args[0][1]
        assert "paused" in msg


class TestEscapeCommand:
    def test_sends_escape(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/escape"))
        # Check that tmux send-keys Escape was called
        escape_calls = [c for c in mock_tmux["calls"] if "Escape" in c]
        assert len(escape_calls) > 0
        msg = handler.reply.call_args[0][1]
        assert "Escape" in msg

    def test_tmux_missing(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        mock_tmux["exists"] = False
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/escape"))
        # Should still reply (escape is best-effort)
        handler.reply.assert_called_once()


class TestTerminateCommand:
    def test_creates_disabled_flag(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/terminate"))
        assert os.path.exists(bridge.SYNC_DISABLED_FILE)
        msg = handler.reply.call_args[0][1]
        assert "terminated" in msg


class TestContinueCommand:
    def test_clears_flags_and_finds_session(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        with open(bridge.SYNC_PAUSED_FILE, "w") as f:
            f.write("1")
        fake_session_files("-proj", [("cont-sess", 5)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/continue"))
        assert not os.path.exists(bridge.SYNC_PAUSED_FILE)
        msg = handler.reply.call_args[0][1]
        assert "Continuing" in msg

    def test_no_sessions(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/continue"))
        msg = handler.reply.call_args[0][1]
        assert "No sessions" in msg


class TestResumeCommand:
    def test_keyboard_with_sessions(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj", [("s1", 10), ("s2", 20)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/resume"))
        # Should send keyboard via telegram_api, not reply
        assert len(mock_telegram_api) > 0
        sent = mock_telegram_api[-1]
        assert sent["method"] == "sendMessage"
        assert "inline_keyboard" in sent["data"].get("reply_markup", {})

    def test_no_sessions(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/resume"))
        msg = handler.reply.call_args[0][1]
        assert "No sessions" in msg


class TestProjectsCommand:
    def test_keyboard_with_projects(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj-a", [("s1", 10)])
        fake_session_files("-proj-b", [("s2", 20)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/projects"))
        assert len(mock_telegram_api) > 0
        sent = mock_telegram_api[-1]
        assert sent["method"] == "sendMessage"
        assert "inline_keyboard" in sent["data"].get("reply_markup", {})

    def test_no_projects(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("/projects"))
        msg = handler.reply.call_args[0][1]
        assert "No projects" in msg


class TestRegularMessage:
    def test_active_sends_to_tmux(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj", [("sess-active", 5)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("Hello Claude"))
        # Check tmux send-keys was called with the message text
        send_calls = [c for c in mock_tmux["calls"]
                      if len(c) > 2 and "send-keys" in c and "Hello Claude" in c]
        assert len(send_calls) > 0

    def test_paused_rejects(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        with open(bridge.SYNC_PAUSED_FILE, "w") as f:
            f.write("1")
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("Hello"))
        msg = handler.reply.call_args[0][1]
        assert "paused" in msg

    def test_terminated_rejects(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        with open(bridge.SYNC_DISABLED_FILE, "w") as f:
            f.write("1")
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("Hello"))
        msg = handler.reply.call_args[0][1]
        assert "terminated" in msg

    def test_auto_binds_session(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj", [("auto-bind-sess", 5)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("Hello", chat_id=456))
        # Session should now be bound
        chat = bridge.get_chat_id_for_session("auto-bind-sess")
        assert chat == "456"


class TestAskAnswerCallback:
    """Tests for AskUserQuestion callback handling (askq: prefix)."""

    def _make_callback(self, data, chat_id=123):
        return {
            "id": "cb1",
            "message": {"chat": {"id": chat_id}},
            "data": data,
        }

    def test_askq_first_option(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """askq:0 sends Enter immediately (no Down keys)."""
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback("askq:0"))
        # Should send Enter but no Down
        down_calls = [c for c in mock_tmux["calls"] if "Down" in c]
        enter_calls = [c for c in mock_tmux["calls"] if "Enter" in c]
        assert len(down_calls) == 0
        assert len(enter_calls) > 0
        handler.reply.assert_called_once()
        assert "option 1" in handler.reply.call_args[0][1]

    def test_askq_third_option(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """askq:2 sends Down twice then Enter."""
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback("askq:2"))
        down_calls = [c for c in mock_tmux["calls"] if "Down" in c]
        enter_calls = [c for c in mock_tmux["calls"] if "Enter" in c]
        assert len(down_calls) == 2
        assert len(enter_calls) > 0
        assert "option 3" in handler.reply.call_args[0][1]

    def test_askq_no_tmux(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """askq without tmux replies error."""
        mock_tmux["exists"] = False
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback("askq:0"))
        msg = handler.reply.call_args[0][1]
        assert "not found" in msg

    def test_askq_invalid_index(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """askq with non-numeric index is silently ignored."""
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback("askq:abc"))
        handler.reply.assert_not_called()


class TestParseCallbackData:
    def test_valid(self):
        assert bridge.parse_callback_data("resume:abc123", "resume:") == "abc123"

    def test_empty_value(self):
        assert bridge.parse_callback_data("resume:", "resume:") is None

    def test_too_long(self):
        assert bridge.parse_callback_data("resume:" + "x" * 129, "resume:") is None

    def test_wrong_prefix(self):
        assert bridge.parse_callback_data("project:abc", "resume:") is None
