"""Tests for session management functions in bridge.py."""

import json
import time
from pathlib import Path

import bridge


class TestIsValidSession:
    def test_valid(self, tmp_path):
        p = tmp_path / "test.jsonl"
        p.write_text(json.dumps({"type": "user"}) + "\n")
        assert bridge.is_valid_session(p) is True

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        assert bridge.is_valid_session(p) is False

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.jsonl"
        p.write_text("not json\n")
        assert bridge.is_valid_session(p) is False

    def test_old_file(self, tmp_path):
        p = tmp_path / "old.jsonl"
        p.write_text(json.dumps({"type": "user"}) + "\n")
        old_time = time.time() - (31 * 86400)
        import os
        os.utime(p, (old_time, old_time))
        assert bridge.is_valid_session(p) is False

    def test_nonexistent(self, tmp_path):
        p = tmp_path / "missing.jsonl"
        assert bridge.is_valid_session(p) is False


class TestGetRecentSessionsFromFiles:
    def test_sorted_by_mtime(self, tmp_claude_dir, fake_session_files):
        now = time.time()
        fake_session_files("-proj-a", [
            ("sess-old", 100),
            ("sess-new", 10),
        ], base_time=now)
        sessions = bridge.get_recent_sessions_from_files(limit=10)
        assert len(sessions) == 2
        assert sessions[0]["session_id"] == "sess-new"
        assert sessions[1]["session_id"] == "sess-old"

    def test_empty_dir(self, tmp_claude_dir):
        sessions = bridge.get_recent_sessions_from_files()
        assert sessions == []

    def test_filters_invalid(self, tmp_claude_dir):
        proj = tmp_claude_dir / "projects" / "-proj-b"
        proj.mkdir(parents=True)
        # Empty file should be filtered
        (proj / "empty.jsonl").write_text("")
        # Valid file
        (proj / "valid.jsonl").write_text(json.dumps({"type": "user"}) + "\n")
        sessions = bridge.get_recent_sessions_from_files()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "valid"


class TestGetSessionsForProject:
    def test_sorted_and_limited(self, tmp_claude_dir, fake_session_files):
        now = time.time()
        fake_session_files("-proj-c", [
            ("a", 300),
            ("b", 200),
            ("c", 100),
        ], base_time=now)
        sessions = bridge.get_sessions_for_project("-proj-c", limit=2)
        assert len(sessions) == 2
        assert sessions[0]["session_id"] == "c"
        assert sessions[1]["session_id"] == "b"

    def test_filters_invalid(self, tmp_claude_dir, fake_session_files):
        now = time.time()
        fake_session_files("-proj-d", [("valid", 10)], base_time=now)
        proj = tmp_claude_dir / "projects" / "-proj-d"
        (proj / "empty.jsonl").write_text("")
        sessions = bridge.get_sessions_for_project("-proj-d")
        assert len(sessions) == 1


class TestGetProjects:
    def test_counts_and_sorted(self, tmp_claude_dir, fake_session_files):
        now = time.time()
        fake_session_files("-proj-x", [("s1", 300), ("s2", 200)], base_time=now)
        fake_session_files("-proj-y", [("s3", 10)], base_time=now)
        projects = bridge.get_projects(limit=10)
        assert len(projects) == 2
        # proj-y has the most recent session
        assert projects[0]["encoded_name"] == "-proj-y"
        assert projects[0]["session_count"] == 1
        assert projects[1]["encoded_name"] == "-proj-x"
        assert projects[1]["session_count"] == 2

    def test_limit(self, tmp_claude_dir, fake_session_files):
        now = time.time()
        for i in range(5):
            fake_session_files(f"-proj-{i}", [(f"s{i}", i * 10)], base_time=now)
        projects = bridge.get_projects(limit=3)
        assert len(projects) == 3

    def test_sorted_by_activity(self, tmp_claude_dir, fake_session_files):
        now = time.time()
        fake_session_files("-old-proj", [("s1", 1000)], base_time=now)
        fake_session_files("-new-proj", [("s2", 5)], base_time=now)
        projects = bridge.get_projects()
        assert projects[0]["encoded_name"] == "-new-proj"
