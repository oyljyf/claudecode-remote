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


class TestHookCopyIntegration:
    """Verify install.sh and start.sh copy all hooks and sounds."""

    @pytest.mark.parametrize("script,pattern", [
        ("scripts/install.sh", "play-alarm.sh"),
        ("scripts/start.sh", "play-alarm.sh"),
        ("scripts/install.sh", "~/.claude/sounds"),
        ("scripts/start.sh", "~/.claude/sounds"),
        ("scripts/install.sh", "handle-permission.sh"),
        ("scripts/start.sh", "handle-permission.sh"),
        ("scripts/install.sh", "send-notification-to-telegram.sh"),
        ("scripts/start.sh", "send-notification-to-telegram.sh"),
    ])
    def test_script_copies_hook(self, script, pattern):
        content = (PROJECT_DIR / script).read_text()
        assert pattern in content, f"{script} should reference {pattern}"

    @pytest.mark.parametrize("script,pattern", [
        ("scripts/install.sh", "play-alarm.sh done"),
        ("scripts/start.sh", "play-alarm.sh done"),
        ("scripts/install.sh", "play-alarm.sh alert"),
        ("scripts/start.sh", "play-alarm.sh alert"),
        ("scripts/install.sh", '"Notification"'),
        ("scripts/start.sh", '"Notification"'),
        ("scripts/install.sh", '"PermissionRequest"'),
        ("scripts/start.sh", '"PermissionRequest"'),
        ("scripts/install.sh", '"timeout": 120'),
        ("scripts/start.sh", '"timeout": 120'),
    ])
    def test_settings_config_includes(self, script, pattern):
        content = (PROJECT_DIR / script).read_text()
        assert pattern in content, f"{script} settings config missing {pattern}"

    @pytest.mark.parametrize("script", [
        "scripts/install.sh",
        "scripts/start.sh",
    ])
    def test_notification_config_alarm_only(self, script):
        """Notification config only has play-alarm.sh, not send-notification-to-telegram.sh.

        AskUserQuestion is handled by handle-permission.sh (PermissionRequest hook).
        Having send-notification-to-telegram.sh in Notification would cause duplicates
        or stale AskUserQuestion entries from transcript.
        """
        content = (PROJECT_DIR / script).read_text()
        # Find Notification section in settings config
        import re
        # In the JSON config block, Notification should NOT reference notification hook
        notification_sections = re.findall(
            r'"Notification".*?(?="UserPromptSubmit"|"PermissionRequest")',
            content, re.DOTALL,
        )
        for section in notification_sections:
            assert "send-notification-to-telegram" not in section, (
                f"{script} Notification config should not include send-notification-to-telegram.sh"
            )


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
        assert "SOUND_DONE" in content
        assert "SOUND_ALERT" in content

    def test_play_alarm_checks_disabled(self):
        content = (PROJECT_DIR / "hooks/play-alarm.sh").read_text()
        assert "alarm_disabled" in content
        assert "ALARM_ENABLED" in content

    def test_play_alarm_runs_in_background(self):
        content = (PROJECT_DIR / "hooks/play-alarm.sh").read_text()
        # afplay/aplay/paplay should run with & (background)
        assert "afplay" in content and "&" in content

    def test_uninstall_removes_alarm_hook(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "play-alarm.sh" in content

    def test_uninstall_removes_sounds(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "~/.claude/sounds" in content

    def test_uninstall_removes_alarm_disabled(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "alarm_disabled" in content

    def test_config_env_has_sound_defaults(self):
        """config.env defines DEFAULT_SOUND_DONE, DEFAULT_SOUND_ALERT, DEFAULT_SOUND_DIR, DEFAULT_ALARM_VOLUME."""
        content = (PROJECT_DIR / "config.env").read_text()
        assert "DEFAULT_SOUND_DONE=" in content
        assert "DEFAULT_SOUND_ALERT=" in content
        assert "DEFAULT_SOUND_DIR=" in content
        assert "DEFAULT_ALARM_VOLUME=" in content

    def test_hooks_common_has_sound_vars(self):
        """hooks/lib/common.sh defines SOUND_DIR, SOUND_DONE, SOUND_ALERT, ALARM_VOLUME."""
        content = (PROJECT_DIR / "hooks/lib/common.sh").read_text()
        assert "SOUND_DIR=" in content
        assert "SOUND_DONE=" in content
        assert "SOUND_ALERT=" in content
        assert "ALARM_VOLUME=" in content

    def test_play_alarm_supports_done_arg(self):
        """play-alarm.sh handles 'done' argument to select done sound."""
        content = (PROJECT_DIR / "hooks/play-alarm.sh").read_text()
        assert "done)" in content or "SOUND_DONE" in content

    def test_play_alarm_supports_alert_arg(self):
        """play-alarm.sh handles 'alert' argument to select alert sound."""
        content = (PROJECT_DIR / "hooks/play-alarm.sh").read_text()
        assert "alert)" in content
        assert "SOUND_ALERT" in content

    def test_play_alarm_default_is_done(self):
        """play-alarm.sh defaults to 'done' when no argument is given."""
        content = (PROJECT_DIR / "hooks/play-alarm.sh").read_text()
        assert "${1:-done}" in content

    def test_play_alarm_no_hardcoded_alarm_mp3(self):
        """play-alarm.sh should not hardcode alarm.mp3."""
        content = (PROJECT_DIR / "hooks/play-alarm.sh").read_text()
        assert "alarm.mp3" not in content

    def test_play_alarm_uses_sound_dir_var(self):
        """play-alarm.sh uses $SOUND_DIR variable for sound directory."""
        content = (PROJECT_DIR / "hooks/play-alarm.sh").read_text()
        assert "$SOUND_DIR/" in content


class TestPermissionHookIntegration:
    """Verify permission hook is properly integrated into install/setup/uninstall."""

    def test_handle_permission_exists(self):
        assert (PROJECT_DIR / "hooks/handle-permission.sh").exists()

    def test_handle_permission_reads_stdin(self):
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "INPUT=$(cat)" in content

    def test_handle_permission_checks_sync(self):
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "get_sync_disabled" in content

    def test_handle_permission_uses_jq(self):
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "jq" in content
        assert "tool_name" in content

    def test_handle_permission_handles_all_tools(self):
        """Hook sends to Telegram for all tools, not just AskUserQuestion."""
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "AskUserQuestion" in content
        # No early exit for non-AskUserQuestion tools
        assert 'TOOL_NAME" != "AskUserQuestion"' not in content
        assert "hookSpecificOutput" not in content

    def test_handle_permission_askq_inline_keyboard(self):
        """AskUserQuestion is formatted as inline keyboard with askq: callbacks."""
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "askq:" in content
        assert "inline_keyboard" in content

    def test_uninstall_removes_permission_hook(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "handle-permission.sh" in content

    def test_uninstall_removes_permission_settings(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "del(.hooks.PermissionRequest)" in content

    def test_uninstall_removes_permission_state_files(self):
        content = (PROJECT_DIR / "scripts/uninstall.sh").read_text()
        assert "pending_permission.json" in content
        assert "permission_response.json" in content


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


class TestPyprojectConfig:
    """Verify pyproject.toml has correct setuptools config to prevent build errors."""

    def test_py_modules_defined(self):
        """pyproject.toml must explicitly set py-modules to avoid flat-layout discovery error."""
        content = (PROJECT_DIR / "pyproject.toml").read_text()
        assert "[tool.setuptools]" in content, (
            "pyproject.toml missing [tool.setuptools] section"
        )
        assert 'py-modules = ["bridge"]' in content, (
            "pyproject.toml must set py-modules = [\"bridge\"] to prevent "
            "setuptools from discovering hooks/ and sounds/ as packages"
        )

    def test_non_python_dirs_not_treated_as_packages(self):
        """Directories like hooks/ and sounds/ must not be auto-discovered as Python packages."""
        import tomllib

        with open(PROJECT_DIR / "pyproject.toml", "rb") as f:
            config = tomllib.load(f)

        # If py-modules is set, setuptools won't auto-discover packages
        py_modules = config.get("tool", {}).get("setuptools", {}).get("py-modules", [])
        assert "bridge" in py_modules, "bridge must be in py-modules"

        # Ensure hooks and sounds are NOT listed as packages
        packages = config.get("tool", {}).get("setuptools", {}).get("packages", [])
        for name in ["hooks", "sounds", "scripts", "tests"]:
            assert name not in packages, (
                f"{name}/ should not be listed as a Python package"
            )


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


class TestStartSyncOptions:
    """Verify start.sh supports --stop-sync and --resume-sync options."""

    def test_start_stop_sync_option(self):
        """start.sh parses --stop-sync flag."""
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        assert "--stop-sync)" in content
        assert "STOP_SYNC=true" in content

    def test_start_resume_sync_option(self):
        """start.sh parses --resume-sync flag."""
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        assert "--resume-sync)" in content
        assert "RESUME_SYNC=true" in content

    def test_stop_sync_creates_paused_file(self):
        """--stop-sync creates SYNC_PAUSED_FILE."""
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        assert 'SYNC_PAUSED_FILE' in content
        # The stop-sync block should write to SYNC_PAUSED_FILE
        assert '> "$SYNC_PAUSED_FILE"' in content

    def test_resume_sync_removes_both_flags(self):
        """--resume-sync removes both SYNC_PAUSED_FILE and SYNC_DISABLED_FILE."""
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        # Should remove both flag files
        assert '"$SYNC_PAUSED_FILE" "$SYNC_DISABLED_FILE"' in content

    def test_stop_sync_removes_pending(self):
        """--stop-sync removes PENDING_FILE."""
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        # Find the stop-sync block and check it removes pending file
        stop_idx = content.index("Stop Sync")
        resume_idx = content.index("Resume Sync")
        stop_block = content[stop_idx:resume_idx]
        assert "PENDING_FILE" in stop_block

    def test_help_includes_sync_options(self):
        """Help text includes --stop-sync and --resume-sync."""
        content = (PROJECT_DIR / "scripts/start.sh").read_text()
        assert "--stop-sync" in content
        assert "--resume-sync" in content


class TestPermissionHookFormatting:
    """Verify handle-permission.sh: all tools → inline keyboard with askq: callbacks."""

    def test_handle_permission_no_decision_output(self):
        """Hook exits without outputting a decision — CC falls back to terminal dialog."""
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "hookSpecificOutput" not in content

    def test_handle_permission_askq_inline_keyboard(self):
        """AskUserQuestion is formatted as inline keyboard with askq: callbacks."""
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "askq:" in content
        assert "inline_keyboard" in content

    def test_handle_permission_sends_keyboard_for_all_tools(self):
        """Non-AskUserQuestion tools get 3-button inline keyboard (Yes/Yes to all/No)."""
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        # No early exit for non-AskUserQuestion
        assert 'TOOL_NAME" != "AskUserQuestion"' not in content
        # 3-button keyboard for tool permissions
        assert '"Yes"' in content
        assert '"Yes to all"' in content
        assert '"No"' in content

    def test_handle_permission_formats_edit_tool(self):
        """Edit tool shows file_path in permission message."""
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "Edit" in content
        assert "file_path" in content

    def test_handle_permission_formats_bash_tool(self):
        """Bash tool shows command in permission message (truncated to 300 chars)."""
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert "Bash" in content
        assert "command" in content
        assert "300" in content

    def test_handle_permission_formats_write_tool(self):
        """Write tool shows file_path in permission message."""
        content = (PROJECT_DIR / "hooks/handle-permission.sh").read_text()
        assert '"Write"' in content


class TestHooksIndependentOfBridge:
    """Verify hooks can send to Telegram directly without bridge."""

    HOOK_FILES = [
        "hooks/send-to-telegram.sh",
        "hooks/send-input-to-telegram.sh",
        "hooks/handle-permission.sh",
    ]

    @pytest.mark.parametrize("hook", HOOK_FILES)
    def test_hooks_call_telegram_api_directly(self, hook):
        """Hooks call api.telegram.org directly, not via bridge."""
        content = (PROJECT_DIR / hook).read_text()
        assert "api.telegram.org" in content

    @pytest.mark.parametrize("hook", HOOK_FILES)
    def test_hooks_do_not_depend_on_bridge(self, hook):
        """Hooks don't reference bridge localhost or bridge.py."""
        content = (PROJECT_DIR / hook).read_text()
        assert "localhost" not in content
        assert "bridge.py" not in content

    @pytest.mark.parametrize("hook", HOOK_FILES)
    def test_hooks_use_token_from_common(self, hook):
        """Hooks use $TELEGRAM_BOT_TOKEN from common.sh, not hardcoded."""
        content = (PROJECT_DIR / hook).read_text()
        assert "TELEGRAM_BOT_TOKEN" in content


class TestSyncFlagConsistency:
    """Verify Telegram commands and local commands use the same flag files."""

    def test_tg_stop_and_local_stop_sync_use_same_flag(self):
        """TG /stop and start.sh --stop-sync both write telegram_sync_paused."""
        bridge_content = (PROJECT_DIR / "bridge.py").read_text()
        start_content = (PROJECT_DIR / "scripts/start.sh").read_text()
        # Bridge: /stop creates SYNC_PAUSED_FILE
        assert "SYNC_PAUSED_FILE" in bridge_content
        # start.sh: --stop-sync creates $SYNC_PAUSED_FILE
        assert "SYNC_PAUSED_FILE" in start_content

    def test_tg_terminate_and_local_terminate_use_same_flag(self):
        """TG /terminate and start.sh --terminate both write telegram_sync_disabled."""
        bridge_content = (PROJECT_DIR / "bridge.py").read_text()
        start_content = (PROJECT_DIR / "scripts/start.sh").read_text()
        # Bridge: /terminate creates SYNC_DISABLED_FILE
        assert "SYNC_DISABLED_FILE" in bridge_content
        # start.sh: --terminate creates $SYNC_DISABLED_FILE
        assert "SYNC_DISABLED_FILE" in start_content

    def test_hook_and_bridge_check_same_flags(self):
        """hooks get_sync_disabled() and bridge get_sync_state() check same files."""
        hook_common = (PROJECT_DIR / "hooks/lib/common.sh").read_text()
        bridge_content = (PROJECT_DIR / "bridge.py").read_text()
        # Both reference the same two flag files
        for flag in ["telegram_sync_disabled", "telegram_sync_paused"]:
            assert flag in hook_common, f"hooks/lib/common.sh missing {flag}"
            assert flag in bridge_content, f"bridge.py missing {flag}"

    def test_flag_filenames_match_across_sources(self):
        """The actual filenames are identical in hooks and bridge."""
        hook_common = (PROJECT_DIR / "hooks/lib/common.sh").read_text()
        script_common = (PROJECT_DIR / "scripts/lib/common.sh").read_text()
        bridge_content = (PROJECT_DIR / "bridge.py").read_text()
        for flag in ["telegram_sync_disabled", "telegram_sync_paused"]:
            assert f"~/.claude/{flag}" in hook_common
            assert f"~/.claude/{flag}" in script_common
            assert f"~/.claude/{flag}" in bridge_content


class TestNotificationHookIntegration:
    """Verify notification hook handles AskUserQuestion with inline keyboard."""

    def test_notification_hook_handles_ask_user_question(self):
        """Notification hook handles AskUserQuestion with inline keyboard."""
        content = (PROJECT_DIR / "hooks/send-notification-to-telegram.sh").read_text()
        assert "AskUserQuestion" in content
        assert "questions" in content
        assert "options" in content

    def test_notification_hook_askq_inline_keyboard(self):
        """Notification hook formats AskUserQuestion as inline keyboard with askq: callbacks."""
        content = (PROJECT_DIR / "hooks/send-notification-to-telegram.sh").read_text()
        assert "askq:" in content
        assert "inline_keyboard" in content
        assert "reply_markup" not in content or "inline_keyboard" in content
