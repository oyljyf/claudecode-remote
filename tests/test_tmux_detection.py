"""Tests for tmux detection functions in bridge.py."""

import bridge


class TestIsShellPrompt:
    def test_dollar_prompt(self):
        assert bridge.is_shell_prompt("user@host $") is True

    def test_percent_prompt(self):
        assert bridge.is_shell_prompt("~ %") is True

    def test_hash_prompt(self):
        assert bridge.is_shell_prompt("root #") is True

    def test_starship_prompt(self):
        assert bridge.is_shell_prompt("some line\n❯") is True

    def test_oh_my_zsh_prompt(self):
        assert bridge.is_shell_prompt("➜ project") is True

    def test_claude_output(self):
        assert bridge.is_shell_prompt("Claude is thinking...") is False

    def test_empty(self):
        assert bridge.is_shell_prompt("") is False

    def test_all_blanks(self):
        assert bridge.is_shell_prompt("   \n   \n   ") is False

    def test_multiline_last_line_prompt(self):
        content = "some output\nmore output\nuser@host $"
        assert bridge.is_shell_prompt(content) is True

    def test_multiline_last_line_not_prompt(self):
        content = "user@host $\nClaude processing"
        assert bridge.is_shell_prompt(content) is False

    def test_blank_lines_after_prompt(self):
        content = "user@host $\n\n"
        assert bridge.is_shell_prompt(content) is True

    def test_prompt_with_path(self):
        assert bridge.is_shell_prompt("/home/user $") is True


class TestFilterWindowTitle:
    def test_uuid_returns(self):
        title = "abc12345-6789-abcd-ef01-234567890abc"
        assert bridge.filter_window_title(title) == title

    def test_bash_returns_none(self):
        assert bridge.filter_window_title("bash") is None

    def test_zsh_returns_none(self):
        assert bridge.filter_window_title("zsh") is None

    def test_sh_returns_none(self):
        assert bridge.filter_window_title("sh") is None

    def test_python_returns_none(self):
        assert bridge.filter_window_title("python") is None

    def test_empty_returns_none(self):
        assert bridge.filter_window_title("") is None

    def test_meaningful_title(self):
        assert bridge.filter_window_title("my-session") == "my-session"
