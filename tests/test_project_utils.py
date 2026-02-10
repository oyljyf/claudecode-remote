"""Tests for project utility functions in bridge.py."""

import bridge


class TestProjectHash:
    def test_returns_8_char_hex(self):
        h = bridge.project_hash("some-project")
        assert len(h) == 8
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        assert bridge.project_hash("foo") == bridge.project_hash("foo")

    def test_populates_cache(self):
        bridge._project_id_cache.clear()
        h = bridge.project_hash("bar-project")
        assert bridge._project_id_cache[h] == "bar-project"


class TestProjectFromHash:
    def test_found(self):
        bridge._project_id_cache.clear()
        h = bridge.project_hash("my-project")
        assert bridge.project_from_hash(h) == "my-project"

    def test_missing_returns_none(self):
        assert bridge.project_from_hash("nonexist") is None


class TestDecodeProjectPath:
    def _exists(self, *valid_paths):
        valid = set(valid_paths)
        return lambda p: p in valid

    def test_simple_path(self):
        result = bridge.decode_project_path(
            "-Users-foo-project",
            exists_fn=self._exists("/Users/foo/project"),
        )
        assert result == "/Users/foo/project"

    def test_hyphenated_dir(self):
        result = bridge.decode_project_path(
            "-Users-foo-my-app",
            exists_fn=self._exists("/Users/foo", "/Users/foo/my-app"),
        )
        assert result == "/Users/foo/my-app"

    def test_nested_hyphenated(self):
        result = bridge.decode_project_path(
            "-Users-foo-AIM-aim-skills",
            exists_fn=self._exists("/Users/foo", "/Users/foo/AIM", "/Users/foo/AIM/aim-skills"),
        )
        assert result == "/Users/foo/AIM/aim-skills"

    def test_no_match_returns_none(self):
        result = bridge.decode_project_path(
            "-no-such-path",
            exists_fn=lambda _: False,
        )
        assert result is None

    def test_empty_returns_none(self):
        result = bridge.decode_project_path("", exists_fn=lambda _: False)
        assert result is None


class TestFormatSessionMessage:
    def test_with_path(self):
        msg = bridge.format_session_message("✅ Resumed", "abcd1234-5678-abcd", "/Users/foo/bar")
        assert "✅ Resumed: abcd1234-5678-abcd" in msg
        assert "📁 /Users/foo/bar" in msg

    def test_without_path(self):
        msg = bridge.format_session_message("🟢 New session", "abcd1234-5678-abcd")
        assert "🟢 New session: abcd1234-5678-abcd" in msg
        assert "📁" not in msg

    def test_full_id_shown(self):
        full_id = "abcd1234-5678-abcd-ef01-234567890abc"
        msg = bridge.format_session_message("✅ OK", full_id)
        assert full_id in msg
