"""Tests for shell script consistency after common.sh refactoring.

Verifies that scripts correctly source common.sh and don't hardcode
paths that should come from the shared library.
"""

import re
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).parent.parent

# Variables that must be defined in common.sh
SHARED_VARS = [
    "CHAT_ID_FILE",
    "PENDING_FILE",
    "SESSION_CHAT_MAP_FILE",
    "CURRENT_SESSION_FILE",
    "SYNC_DISABLED_FILE",
    "SYNC_PAUSED_FILE",
    "PERM_PENDING_FILE",
    "PERM_RESPONSE_FILE",
    "LOG_DIR",
]

# State file paths that should not appear as hardcoded assignments
# outside of common.sh definitions
STATE_FILE_PATTERNS = [
    r'(?<!_FILE=)~/.claude/telegram_chat_id',
    r'(?<!_FILE=)~/.claude/telegram_pending',
    r'(?<!_FILE=)~/.claude/telegram_sync_disabled',
    r'(?<!_FILE=)~/.claude/telegram_sync_paused',
    r'(?<!_FILE=)~/.claude/current_session_id',
    r'(?<!_FILE=)~/.claude/session_chat_map\.json',
]


class TestScriptsLibCommon:
    """Verify scripts/lib/common.sh defines all shared variables."""

    def test_defines_shared_path_vars(self):
        content = (PROJECT_DIR / "scripts/lib/common.sh").read_text()
        for var in SHARED_VARS:
            assert f"{var}=" in content, f"scripts/lib/common.sh missing {var}"

    def test_defines_print_functions(self):
        content = (PROJECT_DIR / "scripts/lib/common.sh").read_text()
        for func in ["print_status", "print_error", "print_warning", "print_info"]:
            assert func in content, f"scripts/lib/common.sh missing {func}"


class TestHooksLibCommon:
    """Verify hooks/lib/common.sh defines all shared variables."""

    def test_defines_shared_path_vars(self):
        content = (PROJECT_DIR / "hooks/lib/common.sh").read_text()
        for var in SHARED_VARS:
            assert f"{var}=" in content, f"hooks/lib/common.sh missing {var}"

    def test_defines_telegram_token(self):
        content = (PROJECT_DIR / "hooks/lib/common.sh").read_text()
        assert "TELEGRAM_BOT_TOKEN" in content

    def test_defines_helper_functions(self):
        content = (PROJECT_DIR / "hooks/lib/common.sh").read_text()
        assert "get_chat_id()" in content
        assert "get_sync_disabled()" in content


class TestPathConsistency:
    """Verify both common.sh files define the same paths."""

    def _extract_assignments(self, filepath):
        content = filepath.read_text()
        assignments = {}
        for line in content.splitlines():
            match = re.match(r'^(\w+)=(.*)', line)
            if match:
                var, val = match.groups()
                assignments[var] = val
        return assignments

    def test_paths_match(self):
        scripts_vars = self._extract_assignments(PROJECT_DIR / "scripts/lib/common.sh")
        hooks_vars = self._extract_assignments(PROJECT_DIR / "hooks/lib/common.sh")
        for var in SHARED_VARS:
            assert var in scripts_vars, f"scripts/lib/common.sh missing {var}"
            assert var in hooks_vars, f"hooks/lib/common.sh missing {var}"
            assert scripts_vars[var] == hooks_vars[var], (
                f"{var} differs: scripts={scripts_vars[var]} hooks={hooks_vars[var]}"
            )


class TestHookScriptsSourceCommon:
    """Verify hook scripts source lib/common.sh."""

    @pytest.mark.parametrize("hook", [
        "hooks/send-to-telegram.sh",
        "hooks/send-input-to-telegram.sh",
        "hooks/play-alarm.sh",
        "hooks/handle-permission.sh",
    ])
    def test_sources_common(self, hook):
        content = (PROJECT_DIR / hook).read_text()
        assert 'source "$(dirname "$0")/lib/common.sh"' in content

    @pytest.mark.parametrize("hook", [
        "hooks/send-to-telegram.sh",
        "hooks/send-input-to-telegram.sh",
    ])
    def test_no_hardcoded_token(self, hook):
        content = (PROJECT_DIR / hook).read_text()
        assert "YOUR_BOT_TOKEN_HERE" not in content, (
            f"{hook} should not contain token placeholder (it's in lib/common.sh)"
        )


class TestScriptsSourceCommon:
    """Verify scripts source scripts/lib/common.sh."""

    @pytest.mark.parametrize("script", [
        "scripts/start.sh",
        "scripts/install.sh",
        "scripts/uninstall.sh",
        "scripts/clean-logs.sh",
    ])
    def test_sources_common(self, script):
        content = (PROJECT_DIR / script).read_text()
        assert 'lib/common.sh' in content, f"{script} does not source lib/common.sh"


class TestTokenReplacementTarget:
    """Verify token replacement targets hooks/lib/common.sh, not hook scripts."""

    def test_install_replaces_in_common(self):
        content = (PROJECT_DIR / "scripts/install.sh").read_text()
        # Should replace in common.sh
        assert "hooks/lib/common.sh" in content
        # Should NOT replace directly in hook scripts
        lines = content.splitlines()
        for line in lines:
            if "sed" in line and "YOUR_BOT_TOKEN_HERE" in line:
                assert "lib/common.sh" in line, (
                    f"install.sh sed targets wrong file: {line.strip()}"
                )

    def test_start_setup_hook_replaces_in_common(self):
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        lines = content.splitlines()
        for line in lines:
            if "sed" in line and "YOUR_BOT_TOKEN_HERE" in line:
                assert "lib/common.sh" in line, (
                    f"start.sh sed targets wrong file: {line.strip()}"
                )

    def test_start_check_config_checks_common(self):
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        lines = content.splitlines()
        for line in lines:
            if "grep" in line and "YOUR_BOT_TOKEN_HERE" in line:
                assert "lib/common.sh" in line, (
                    f"start.sh token check targets wrong file: {line.strip()}"
                )

    def test_install_check_status_checks_common(self):
        content = (PROJECT_DIR / "scripts/install.sh").read_text()
        lines = content.splitlines()
        for line in lines:
            if "grep" in line and "YOUR_BOT_TOKEN_HERE" in line:
                assert "lib/common.sh" in line, (
                    f"install.sh token check targets wrong file: {line.strip()}"
                )


class TestNoHardcodedStateFiles:
    """Verify scripts don't hardcode state file paths (except common.sh and display text)."""

    @pytest.mark.parametrize("script", [
        "scripts/start.sh",
        "scripts/uninstall.sh",
    ])
    def test_no_hardcoded_sync_disabled_assignment(self, script):
        content = (PROJECT_DIR / script).read_text()
        # Should not have SYNC_DISABLED_FILE=~/.claude/... (that's in common.sh)
        assert re.search(r'^\s*SYNC_DISABLED_FILE=', content, re.MULTILINE) is None, (
            f"{script} has hardcoded SYNC_DISABLED_FILE assignment"
        )

    @pytest.mark.parametrize("script", [
        "scripts/start.sh",
        "scripts/uninstall.sh",
    ])
    def test_no_hardcoded_pending_assignment(self, script):
        content = (PROJECT_DIR / script).read_text()
        assert re.search(r'^\s*PENDING_FILE=', content, re.MULTILINE) is None, (
            f"{script} has hardcoded PENDING_FILE assignment"
        )

    def test_clean_logs_no_hardcoded_log_dir(self):
        content = (PROJECT_DIR / "scripts/clean-logs.sh").read_text()
        assert re.search(r'^\s*LOG_DIR=', content, re.MULTILINE) is None, (
            "clean-logs.sh has hardcoded LOG_DIR assignment"
        )

    def test_uninstall_uses_variables_for_state_files(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        # The state_files array should use $VARIABLE not hardcoded paths
        # Find the state_files array
        match = re.search(r'state_files=\((.*?)\)', content, re.DOTALL)
        assert match, "uninstall.sh missing state_files array"
        array_content = match.group(1)
        assert "~/.claude/telegram" not in array_content, (
            "uninstall.sh state_files array should use variables, not hardcoded paths"
        )


class TestSetupHookCopiesLib:
    """Verify setup functions copy hooks/lib/ directory."""

    def test_install_copies_lib(self):
        content = (PROJECT_DIR / "scripts/install.sh").read_text()
        assert "hooks/lib" in content
        assert "mkdir -p ~/.claude/hooks/lib" in content

    def test_start_setup_hook_copies_lib(self):
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        assert "mkdir -p ~/.claude/hooks/lib" in content
        assert "hooks/lib/common.sh" in content


class TestAlarmHookIntegration:
    """Verify alarm hook is properly integrated into install/setup/uninstall."""

    def test_play_alarm_exists(self):
        assert (PROJECT_DIR / "hooks/play-alarm.sh").exists()

    def test_sounds_dir_exists(self):
        assert (PROJECT_DIR / "sounds").is_dir()

    def test_play_alarm_is_executable_script(self):
        content = (PROJECT_DIR / "hooks/play-alarm.sh").read_text()
        assert content.startswith("#!/bin/bash")
        assert "afplay" in content
        assert "alarm.mp3" in content

    def test_play_alarm_checks_disabled(self):
        content = (PROJECT_DIR / "hooks/play-alarm.sh").read_text()
        assert "alarm_disabled" in content
        assert "ALARM_ENABLED" in content

    def test_play_alarm_runs_in_background(self):
        content = (PROJECT_DIR / "hooks/play-alarm.sh").read_text()
        # afplay/aplay/paplay should run with & (background)
        assert "afplay" in content and "&" in content

    def test_install_copies_alarm_hook(self):
        content = (PROJECT_DIR / "scripts/install.sh").read_text()
        assert "play-alarm.sh" in content

    def test_install_copies_sounds(self):
        content = (PROJECT_DIR / "scripts/install.sh").read_text()
        assert "~/.claude/sounds" in content

    def test_start_setup_copies_alarm_hook(self):
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        assert "play-alarm.sh" in content

    def test_start_setup_copies_sounds(self):
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        assert "~/.claude/sounds" in content

    def test_settings_config_includes_alarm(self):
        """Both install.sh and start.sh settings.json config include play-alarm."""
        for script in ["scripts/install.sh", "scripts/start.sh"]:
            content = (PROJECT_DIR / script).read_text()
            assert "play-alarm.sh" in content, (
                f"{script} settings.json config missing play-alarm.sh"
            )

    def test_settings_config_includes_notification_alarm(self):
        """Both install.sh and start.sh settings.json config include Notification hook."""
        for script in ["scripts/install.sh", "scripts/start.sh"]:
            content = (PROJECT_DIR / script).read_text()
            assert '"Notification"' in content, (
                f"{script} settings.json config missing Notification hook for alarm"
            )

    def test_uninstall_removes_alarm_hook(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "play-alarm.sh" in content

    def test_uninstall_removes_sounds(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "~/.claude/sounds" in content

    def test_uninstall_removes_alarm_disabled(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "alarm_disabled" in content


class TestPermissionHookIntegration:
    """Verify permission hook is properly integrated into install/setup/uninstall."""

    def test_handle_permission_exists(self):
        assert (PROJECT_DIR / "hooks/handle-permission.sh").exists()

    def test_handle_permission_sources_common(self):
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert 'source "$(dirname "$0")/lib/common.sh"' in content

    def test_handle_permission_checks_sync(self):
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "get_sync_disabled" in content

    def test_handle_permission_reads_stdin(self):
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "INPUT=$(cat)" in content

    def test_handle_permission_uses_jq(self):
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "jq" in content
        assert "tool_name" in content

    def test_install_copies_permission_hook(self):
        content = (PROJECT_DIR / "scripts/install.sh").read_text()
        assert "handle-permission.sh" in content

    def test_start_setup_copies_permission_hook(self):
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        assert "handle-permission.sh" in content

    def test_settings_config_includes_permission(self):
        """Both install.sh and start.sh settings.json config include PermissionRequest."""
        for script in ["scripts/install.sh", "scripts/start.sh"]:
            content = (PROJECT_DIR / script).read_text()
            assert '"PermissionRequest"' in content, (
                f"{script} settings.json config missing PermissionRequest"
            )

    def test_settings_config_permission_timeout(self):
        """PermissionRequest hook has timeout: 120."""
        for script in ["scripts/install.sh", "scripts/start.sh"]:
            content = (PROJECT_DIR / script).read_text()
            assert '"timeout": 120' in content, (
                f"{script} settings.json config missing timeout for PermissionRequest"
            )

    def test_uninstall_removes_permission_hook(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "handle-permission.sh" in content

    def test_uninstall_removes_permission_settings(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "del(.hooks.PermissionRequest)" in content

    def test_uninstall_removes_permission_state_files(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "$PERM_PENDING_FILE" in content
        assert "$PERM_RESPONSE_FILE" in content


class TestUninstallComponentFlags:
    """Uninstall supports --telegram and --alarm flags for selective removal."""

    def test_uninstall_supports_telegram_flag(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "--telegram)" in content

    def test_uninstall_supports_alarm_flag(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "--alarm)" in content

    def test_uninstall_supports_all_flag(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "--all)" in content

    def test_uninstall_supports_keep_deps_flag(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "--keep-deps)" in content

    def test_uninstall_supports_force_flag(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "--force)" in content

    def test_uninstall_interactive_chooser(self):
        """Default mode (no flags) shows interactive component chooser."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "Telegram only" in content
        assert "Alarm only" in content
        assert "Both" in content

    def test_uninstall_force_defaults_both(self):
        """--force without component flags removes both."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "# --force without component flags: remove both" in content

    def test_uninstall_telegram_guard(self):
        """Telegram sections are guarded by REMOVE_TELEGRAM flag."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "if $REMOVE_TELEGRAM" in content

    def test_uninstall_alarm_guard(self):
        """Alarm sections are guarded by REMOVE_ALARM flag."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "if $REMOVE_ALARM" in content

    def test_uninstall_lib_only_when_both(self):
        """hooks/lib/ is only removed when both components are removed."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "if $REMOVE_TELEGRAM && $REMOVE_ALARM" in content

    def test_uninstall_selective_jq_telegram(self):
        """--telegram only: jq filters out send-to-telegram, keeps play-alarm."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert 'contains("send-to-telegram") | not' in content

    def test_uninstall_selective_jq_alarm(self):
        """--alarm only: jq filters out play-alarm, keeps send-to-telegram."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert 'contains("play-alarm") | not' in content

    def test_uninstall_removes_notification_hooks(self):
        """Uninstall alarm also removes Notification hooks."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert 'del(.hooks.Notification)' in content

    def test_uninstall_processes_under_telegram_guard(self):
        """Process cleanup (bridge, cloudflared, webhook) is telegram-specific."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        telegram_idx = content.index("# Stop Running Processes (Telegram-specific)")
        bridge_idx = content.index("kill_bridge")
        assert bridge_idx > telegram_idx
        assert "deleteWebhook" in content

    def test_uninstall_env_vars_under_telegram_guard(self):
        """TELEGRAM_BOT_TOKEN removal is telegram-specific."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        env_idx = content.index("TELEGRAM_BOT_TOKEN from Shell Config (Telegram-specific)")
        token_del_idx = content.index("TELEGRAM_BOT_TOKEN/d")
        assert token_del_idx > env_idx

    def test_uninstall_all_removes_logs(self):
        """--all flag removes logs directory."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "if $REMOVE_ALL" in content
        assert "~/.claude/logs" in content
        assert "history.jsonl" in content

    def test_uninstall_deps_only_with_telegram(self):
        """System deps removal only offered when removing telegram."""
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "if $REMOVE_TELEGRAM && ! $KEEP_DEPS" in content


class TestCleanLogsScript:
    """Verify clean-logs.sh uses correct find options."""

    def test_uses_mmin_not_mtime(self):
        """clean-logs.sh should use -mmin for precise day calculation."""
        content = (PROJECT_DIR / "scripts/clean-logs.sh").read_text()
        assert "-mmin" in content, "clean-logs.sh should use -mmin for precise timing"
        assert "-mtime" not in content, "clean-logs.sh should not use -mtime (rounding issue)"

    def test_mmin_calculation(self):
        """Verify -mmin uses DAYS * 1440 (minutes per day)."""
        content = (PROJECT_DIR / "scripts/clean-logs.sh").read_text()
        assert "DAYS * 1440" in content, "clean-logs.sh should convert days to minutes via DAYS * 1440"

    def test_targets_cc_log_pattern(self):
        content = (PROJECT_DIR / "scripts/clean-logs.sh").read_text()
        assert 'cc_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].log' in content

    def test_also_cleans_debug_log(self):
        content = (PROJECT_DIR / "scripts/clean-logs.sh").read_text()
        assert "debug.log" in content

    def test_default_days_is_30(self):
        content = (PROJECT_DIR / "scripts/clean-logs.sh").read_text()
        assert "${1:-30}" in content
