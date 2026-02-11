"""Tests for the HTTP handler in bridge.py."""

import os
from unittest.mock import MagicMock

import bridge
from helpers import create_sync_flag


def _make_update(text, chat_id=123, message_id=1):
    """Build a Telegram update dict."""
    return {
        "message": {
            "text": text,
            "chat": {"id": chat_id},
            "message_id": message_id,
        }
    }


def _make_callback(data, chat_id=123):
    """Build a Telegram callback_query dict."""
    return {
        "id": "cb1",
        "message": {"chat": {"id": chat_id}},
        "data": data,
    }


def _make_handler(mock_tmux, mock_telegram_api):
    """Create a Handler instance with mocked I/O."""
    handler = bridge.Handler.__new__(bridge.Handler)
    handler.reply = MagicMock()
    handler.reply_keyboard = MagicMock()
    return handler


def _send_command(handler, text, chat_id=123) -> str:
    """Send a command and return the reply text."""
    handler.handle_message(_make_update(text, chat_id=chat_id))
    return handler.reply.call_args[0][1] if handler.reply.called else ""


class TestStatusCommand:
    def test_tmux_up_active(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj", [("sess1", 5)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/status")
        assert "running" in msg
        assert "active" in msg

    def test_tmux_down(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        mock_tmux["exists"] = False
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/status")
        assert "not found" in msg

    def test_paused(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        create_sync_flag(bridge.SYNC_PAUSED_FILE)
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/status")
        assert "paused" in msg

    def test_terminated(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        create_sync_flag(bridge.SYNC_DISABLED_FILE)
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/status")
        assert "terminated" in msg


class TestStartCommand:
    def test_tmux_exists(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj", [("newsess", 1)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/start")
        assert "New session" in msg or "Starting" in msg

    def test_tmux_missing(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        mock_tmux["exists"] = False
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/start")
        assert "not found" in msg


class TestStopCommand:
    def test_creates_paused_flag(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/stop")
        assert os.path.exists(bridge.SYNC_PAUSED_FILE)
        assert "paused" in msg


class TestEscapeCommand:
    def test_sends_escape(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/escape")
        escape_calls = [c for c in mock_tmux["calls"] if "Escape" in c]
        assert len(escape_calls) > 0
        assert "Interrupted" in msg

    def test_tmux_missing(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        mock_tmux["exists"] = False
        handler = _make_handler(mock_tmux, mock_telegram_api)
        _send_command(handler, "/escape")
        handler.reply.assert_called_once()


class TestTerminateCommand:
    def test_creates_disabled_flag(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/terminate")
        assert os.path.exists(bridge.SYNC_DISABLED_FILE)
        assert "terminated" in msg


class TestContinueCommand:
    def test_clears_flags_and_finds_session(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        create_sync_flag(bridge.SYNC_PAUSED_FILE)
        fake_session_files("-proj", [("cont-sess", 5)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/continue")
        assert not os.path.exists(bridge.SYNC_PAUSED_FILE)
        assert "Continuing" in msg

    def test_no_sessions(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/continue")
        assert "No sessions" in msg


class TestResumeCommand:
    def test_keyboard_with_sessions(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj", [("s1", 10), ("s2", 20)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        _send_command(handler, "/resume")
        handler.reply_keyboard.assert_called_once()
        args = handler.reply_keyboard.call_args[0]
        assert "resume" in args[1].lower()

    def test_no_sessions(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/resume")
        assert "No sessions" in msg


class TestProjectsCommand:
    def test_keyboard_with_projects(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj-a", [("s1", 10)])
        fake_session_files("-proj-b", [("s2", 20)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        _send_command(handler, "/projects")
        handler.reply_keyboard.assert_called_once()
        args = handler.reply_keyboard.call_args[0]
        assert "project" in args[1].lower()

    def test_no_projects(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "/projects")
        assert "No projects" in msg


class TestRegularMessage:
    def test_active_sends_to_tmux(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj", [("sess-active", 5)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("Hello Claude"))
        send_calls = [c for c in mock_tmux["calls"]
                      if len(c) > 2 and "send-keys" in c and "Hello Claude" in c]
        assert len(send_calls) > 0

    def test_paused_rejects(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        create_sync_flag(bridge.SYNC_PAUSED_FILE)
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "Hello")
        assert "paused" in msg

    def test_terminated_rejects(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        create_sync_flag(bridge.SYNC_DISABLED_FILE)
        handler = _make_handler(mock_tmux, mock_telegram_api)
        msg = _send_command(handler, "Hello")
        assert "terminated" in msg

    def test_auto_binds_session(self, tmp_claude_dir, mock_tmux, mock_telegram_api, fake_session_files):
        fake_session_files("-proj", [("auto-bind-sess", 5)])
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_message(_make_update("Hello", chat_id=456))
        chat = bridge.get_chat_id_for_session("auto-bind-sess")
        assert chat == "456"


class TestAskAnswerCallback:
    """Tests for AskUserQuestion callback handling (askq: prefix)."""

    def test_askq_first_option(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """askq:0 sends Enter immediately (no Down keys)."""
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(_make_callback("askq:0"))
        down_calls = [c for c in mock_tmux["calls"] if "Down" in c]
        enter_calls = [c for c in mock_tmux["calls"] if "Enter" in c]
        assert len(down_calls) == 0
        assert len(enter_calls) > 0
        handler.reply.assert_called_once()
        assert "option 1" in handler.reply.call_args[0][1]

    def test_askq_third_option(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """askq:2 sends Down twice then Enter."""
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(_make_callback("askq:2"))
        down_calls = [c for c in mock_tmux["calls"] if "Down" in c]
        enter_calls = [c for c in mock_tmux["calls"] if "Enter" in c]
        assert len(down_calls) == 2
        assert len(enter_calls) > 0
        assert "option 3" in handler.reply.call_args[0][1]

    def test_askq_no_tmux(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """askq without tmux replies error."""
        mock_tmux["exists"] = False
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(_make_callback("askq:0"))
        msg = handler.reply.call_args[0][1]
        assert "not found" in msg

    def test_askq_invalid_index(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """askq with non-numeric index is silently ignored."""
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(_make_callback("askq:abc"))
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
