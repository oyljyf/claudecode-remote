"""Tests for sync state management functions in bridge.py."""

import os

import bridge
from helpers import create_sync_flag


class TestGetSyncState:
    def test_no_flags_active(self, tmp_claude_dir):
        assert bridge.get_sync_state() == bridge.SYNC_STATE_ACTIVE

    def test_paused(self, tmp_claude_dir):
        create_sync_flag(bridge.SYNC_PAUSED_FILE)
        assert bridge.get_sync_state() == bridge.SYNC_STATE_PAUSED

    def test_terminated(self, tmp_claude_dir):
        create_sync_flag(bridge.SYNC_DISABLED_FILE)
        assert bridge.get_sync_state() == bridge.SYNC_STATE_TERMINATED

    def test_both_flags_returns_terminated(self, tmp_claude_dir):
        create_sync_flag(bridge.SYNC_PAUSED_FILE)
        create_sync_flag(bridge.SYNC_DISABLED_FILE)
        assert bridge.get_sync_state() == bridge.SYNC_STATE_TERMINATED


class TestClearSyncFlags:
    def test_both_exist(self, tmp_claude_dir):
        create_sync_flag(bridge.SYNC_PAUSED_FILE)
        create_sync_flag(bridge.SYNC_DISABLED_FILE)
        bridge.clear_sync_flags()
        assert not os.path.exists(bridge.SYNC_PAUSED_FILE)
        assert not os.path.exists(bridge.SYNC_DISABLED_FILE)

    def test_one_exists(self, tmp_claude_dir):
        create_sync_flag(bridge.SYNC_PAUSED_FILE)
        bridge.clear_sync_flags()
        assert not os.path.exists(bridge.SYNC_PAUSED_FILE)
        assert not os.path.exists(bridge.SYNC_DISABLED_FILE)

    def test_none_exist(self, tmp_claude_dir):
        # Should not raise
        bridge.clear_sync_flags()
