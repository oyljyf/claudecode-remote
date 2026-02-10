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
