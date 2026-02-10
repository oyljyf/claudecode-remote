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


class TestPermissionCallback:
    """Tests for permission request callback handling."""

    def _make_callback(self, data, chat_id=123):
        return {
            "id": "cb1",
            "message": {"chat": {"id": chat_id}},
            "data": data,
        }

    def test_perm_allow(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        # Write pending permission
        import json
        pending = {"id": "abcd1234", "tool_name": "Bash", "timestamp": 1000}
        with open(bridge.PERM_PENDING_FILE, "w") as f:
            json.dump(pending, f)

        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback("perm_allow:abcd1234"))

        # Verify response file was written
        assert os.path.exists(bridge.PERM_RESPONSE_FILE)
        with open(bridge.PERM_RESPONSE_FILE) as f:
            resp = json.load(f)
        assert resp["id"] == "abcd1234"
        assert resp["behavior"] == "allow"
        # Verify reply
        handler.reply.assert_called_once()
        msg = handler.reply.call_args[0][1]
        assert "Allow" in msg
        assert "Bash" in msg

    def test_perm_deny(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        import json
        pending = {"id": "abcd1234", "tool_name": "Write", "timestamp": 1000}
        with open(bridge.PERM_PENDING_FILE, "w") as f:
            json.dump(pending, f)

        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback("perm_deny:abcd1234"))

        assert os.path.exists(bridge.PERM_RESPONSE_FILE)
        with open(bridge.PERM_RESPONSE_FILE) as f:
            resp = json.load(f)
        assert resp["id"] == "abcd1234"
        assert resp["behavior"] == "deny"
        handler.reply.assert_called_once()
        msg = handler.reply.call_args[0][1]
        assert "Deny" in msg

    def test_perm_expired(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """Pending ID does not match callback ID."""
        import json
        pending = {"id": "different", "tool_name": "Bash", "timestamp": 1000}
        with open(bridge.PERM_PENDING_FILE, "w") as f:
            json.dump(pending, f)

        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback("perm_allow:abcd1234"))

        # Should not write response file
        assert not os.path.exists(bridge.PERM_RESPONSE_FILE)
        handler.reply.assert_called_once()
        msg = handler.reply.call_args[0][1]
        assert "expired" in msg or "mismatched" in msg

    def test_perm_no_pending(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """No pending permission file exists."""
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback("perm_allow:abcd1234"))

        assert not os.path.exists(bridge.PERM_RESPONSE_FILE)
        handler.reply.assert_called_once()
        msg = handler.reply.call_args[0][1]
        assert "No pending" in msg

    def test_perm_allow_no_tmux_needed(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """Permission callback works even when tmux is down (file IPC only)."""
        mock_tmux["exists"] = False
        pending = {"id": "notmux1", "tool_name": "Bash", "timestamp": 1000}
        with open(bridge.PERM_PENDING_FILE, "w") as f:
            json.dump(pending, f)

        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback("perm_allow:notmux1"))

        # Should still work — permission doesn't need tmux
        assert os.path.exists(bridge.PERM_RESPONSE_FILE)
        with open(bridge.PERM_RESPONSE_FILE) as f:
            resp = json.load(f)
        assert resp["behavior"] == "allow"


class TestPermissionEndToEnd:
    """End-to-end: simulate hook writes pending → bridge callback → hook reads response."""

    def _make_callback(self, data, chat_id=123):
        return {
            "id": "cb1",
            "message": {"chat": {"id": chat_id}},
            "data": data,
        }

    def _hook_read_response(self, perm_id):
        """Simulate what handle-permission.sh's Python code does after bridge writes response."""
        if not os.path.exists(bridge.PERM_RESPONSE_FILE):
            return None
        with open(bridge.PERM_RESPONSE_FILE) as f:
            resp = json.load(f)
        if resp.get("id") != perm_id:
            return None
        behavior = resp.get("behavior", "deny")
        if behavior == "allow":
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": "allow"},
                }
            }
        else:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "deny",
                        "message": "Denied via Telegram",
                    },
                }
            }

    def test_allow_produces_correct_claude_json(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """Full flow: pending → Allow callback → hook output matches Claude's expected format."""
        perm_id = "e2e_allow"
        pending = {"id": perm_id, "tool_name": "Bash", "timestamp": time.time()}
        with open(bridge.PERM_PENDING_FILE, "w") as f:
            json.dump(pending, f)

        # Bridge handles callback
        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback(f"perm_allow:{perm_id}"))

        # Hook reads response
        output = self._hook_read_response(perm_id)
        assert output is not None
        assert output["hookSpecificOutput"]["hookEventName"] == "PermissionRequest"
        assert output["hookSpecificOutput"]["decision"]["behavior"] == "allow"

    def test_deny_produces_correct_claude_json(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """Full flow: pending → Deny callback → hook output matches Claude's expected format."""
        perm_id = "e2e_deny"
        pending = {"id": perm_id, "tool_name": "Write", "timestamp": time.time()}
        with open(bridge.PERM_PENDING_FILE, "w") as f:
            json.dump(pending, f)

        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback(f"perm_deny:{perm_id}"))

        output = self._hook_read_response(perm_id)
        assert output is not None
        assert output["hookSpecificOutput"]["decision"]["behavior"] == "deny"
        assert "Denied via Telegram" in output["hookSpecificOutput"]["decision"]["message"]

    def test_response_file_cleaned_after_read(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """Hook should clean up response file after reading (simulated)."""
        perm_id = "e2e_clean"
        pending = {"id": perm_id, "tool_name": "Edit", "timestamp": time.time()}
        with open(bridge.PERM_PENDING_FILE, "w") as f:
            json.dump(pending, f)

        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback(f"perm_allow:{perm_id}"))

        # Response file exists before hook reads it
        assert os.path.exists(bridge.PERM_RESPONSE_FILE)

        # Simulate hook cleanup (what handle-permission.sh does after reading)
        output = self._hook_read_response(perm_id)
        assert output is not None
        os.remove(bridge.PERM_RESPONSE_FILE)
        os.remove(bridge.PERM_PENDING_FILE)
        assert not os.path.exists(bridge.PERM_RESPONSE_FILE)
        assert not os.path.exists(bridge.PERM_PENDING_FILE)

    def test_stale_response_ignored(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """If response file has wrong ID, hook ignores it (simulates stale response)."""
        # Write a stale response from a previous request
        with open(bridge.PERM_RESPONSE_FILE, "w") as f:
            json.dump({"id": "old_request", "behavior": "allow"}, f)

        # Hook polls with current perm_id — should not match
        output = self._hook_read_response("new_request")
        assert output is None

    def test_telegram_confirmation_message(self, tmp_claude_dir, mock_tmux, mock_telegram_api):
        """Bridge sends confirmation message back to Telegram after Allow/Deny."""
        perm_id = "e2e_confirm"
        pending = {"id": perm_id, "tool_name": "Bash", "timestamp": time.time()}
        with open(bridge.PERM_PENDING_FILE, "w") as f:
            json.dump(pending, f)

        handler = _make_handler(mock_tmux, mock_telegram_api)
        handler.handle_callback(self._make_callback(f"perm_allow:{perm_id}"))

        # Bridge should reply with confirmation
        handler.reply.assert_called_once()
        msg = handler.reply.call_args[0][1]
        assert "Allow" in msg
        assert "Bash" in msg


class TestParseCallbackData:
    def test_valid(self):
        assert bridge.parse_callback_data("resume:abc123", "resume:") == "abc123"

    def test_empty_value(self):
        assert bridge.parse_callback_data("resume:", "resume:") is None

    def test_too_long(self):
        assert bridge.parse_callback_data("resume:" + "x" * 129, "resume:") is None

    def test_wrong_prefix(self):
        assert bridge.parse_callback_data("project:abc", "resume:") is None
