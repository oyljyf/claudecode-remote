"""Tests for /report command: token usage scanning and formatting."""

import json
import os
import time
from datetime import datetime, timedelta

import bridge


def _today_ts() -> str:
    """Return today's date as ISO timestamp at 10:00."""
    return f"{datetime.now().strftime('%Y-%m-%d')}T10:00:00Z"


def _make_assistant_entry(model, input_tokens, output_tokens, timestamp,
                          cache_read=0, cache_creation=0):
    """Build a JSONL assistant entry with usage data."""
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if cache_read:
        usage["cache_read_input_tokens"] = cache_read
    if cache_creation:
        usage["cache_creation_input_tokens"] = cache_creation
    return json.dumps({
        "type": "assistant",
        "timestamp": timestamp,
        "message": {"model": model, "usage": usage},
    })


def _make_user_entry(timestamp):
    return json.dumps({
        "type": "user",
        "timestamp": timestamp,
        "message": {"text": "hello"},
    })


def _make_session_file(tmp_claude_dir, project_name, session_id, entries):
    """Create a session JSONL file with the given entries (list of strings)."""
    proj = tmp_claude_dir / "projects" / project_name
    proj.mkdir(parents=True, exist_ok=True)
    f = proj / f"{session_id}.jsonl"
    f.write_text("\n".join(entries) + "\n")
    return f


def _empty_report(**overrides):
    """Build a report data dict with all-zero defaults, applying overrides."""
    data = {
        "totals": {
            "today": {"input": 0, "output": 0},
            "yesterday": {"input": 0, "output": 0},
            "7d": {"input": 0, "output": 0},
            "30d": {"input": 0, "output": 0},
        },
        "by_model": {},
        "by_model_7d": {},
        "by_model_30d": {},
        "by_project": {},
        "by_session": {},
        "session_project": {},
        "cache_today": {"read": 0, "creation": 0},
    }
    data.update(overrides)
    return data


class TestShortenModelName:
    """Test model ID to short display name conversion."""

    def test_known_opus(self):
        assert bridge.shorten_model_name("claude-opus-4-6") == "Opus 4.6"

    def test_known_haiku(self):
        assert bridge.shorten_model_name("claude-haiku-4-5-20251001") == "Haiku 4.5"

    def test_known_sonnet(self):
        assert bridge.shorten_model_name("claude-sonnet-4-5-20250929") == "Sonnet 4.5"

    def test_unknown_with_date_suffix(self):
        assert bridge.shorten_model_name("claude-future-model-20261231") == "Future Model"

    def test_unknown_without_date(self):
        assert bridge.shorten_model_name("claude-something-new") == "Something New"

    def test_non_claude_model(self):
        assert bridge.shorten_model_name("gpt-4o") == "Gpt 4O"


class TestScanTokenUsage:
    """Test session JSONL scanning for token usage."""

    def test_empty_projects(self, tmp_claude_dir):
        result = bridge.scan_token_usage()
        assert result["totals"]["today"]["input"] == 0
        assert result["totals"]["today"]["output"] == 0
        assert result["by_model"] == {}
        assert result["by_project"] == {}
        assert result["by_session"] == {}

    def test_today_totals(self, tmp_claude_dir):
        ts = _today_ts()
        _make_session_file(tmp_claude_dir, "-Users-test-myapp", "abc123", [
            _make_assistant_entry("claude-opus-4-6", 1000, 200, ts),
            _make_assistant_entry("claude-opus-4-6", 500, 100, ts),
        ])
        result = bridge.scan_token_usage()
        assert result["totals"]["today"]["input"] == 1500
        assert result["totals"]["today"]["output"] == 300
        assert result["totals"]["7d"]["input"] == 1500
        assert result["totals"]["30d"]["input"] == 1500

    def test_7d_excludes_old(self, tmp_claude_dir):
        today = datetime.now()
        old_day = (today - timedelta(days=10)).strftime("%Y-%m-%d")
        ts_old = f"{old_day}T10:00:00Z"
        ts_today = _today_ts()
        _make_session_file(tmp_claude_dir, "-Users-test-proj", "sess1", [
            _make_assistant_entry("claude-opus-4-6", 1000, 100, ts_old),
            _make_assistant_entry("claude-opus-4-6", 500, 50, ts_today),
        ])
        result = bridge.scan_token_usage()
        assert result["totals"]["7d"]["input"] == 500
        assert result["totals"]["30d"]["input"] == 1500

    def test_30d_includes_within_range(self, tmp_claude_dir):
        day20 = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        ts = f"{day20}T10:00:00Z"
        _make_session_file(tmp_claude_dir, "-Users-test-proj2", "sess2", [
            _make_assistant_entry("claude-opus-4-6", 2000, 300, ts),
        ])
        result = bridge.scan_token_usage()
        assert result["totals"]["today"]["input"] == 0
        assert result["totals"]["7d"]["input"] == 0
        assert result["totals"]["30d"]["input"] == 2000

    def test_by_model_today(self, tmp_claude_dir):
        ts = _today_ts()
        _make_session_file(tmp_claude_dir, "-Users-test-proj3", "sess3", [
            _make_assistant_entry("claude-opus-4-6", 1000, 200, ts),
            _make_assistant_entry("claude-haiku-4-5-20251001", 500, 100, ts),
        ])
        result = bridge.scan_token_usage()
        assert result["by_model"]["claude-opus-4-6"]["input"] == 1000
        assert result["by_model"]["claude-opus-4-6"]["output"] == 200
        assert result["by_model"]["claude-haiku-4-5-20251001"]["input"] == 500
        assert result["by_model"]["claude-haiku-4-5-20251001"]["output"] == 100

    def test_by_model_7d_and_30d(self, tmp_claude_dir):
        """by_model_7d and by_model_30d aggregate model data for cost estimation."""
        today = datetime.now()
        ts_today = _today_ts()
        ts_3d = f"{(today - timedelta(days=3)).strftime('%Y-%m-%d')}T10:00:00Z"
        ts_20d = f"{(today - timedelta(days=20)).strftime('%Y-%m-%d')}T10:00:00Z"
        _make_session_file(tmp_claude_dir, "-Users-test-model-periods", "mp1", [
            _make_assistant_entry("claude-opus-4-6", 1000, 200, ts_today),
            _make_assistant_entry("claude-opus-4-6", 2000, 400, ts_3d),
            _make_assistant_entry("claude-haiku-4-5-20251001", 3000, 600, ts_20d),
        ])
        result = bridge.scan_token_usage()
        assert result["by_model"]["claude-opus-4-6"]["input"] == 1000
        assert result["by_model_7d"]["claude-opus-4-6"]["input"] == 3000
        assert "claude-haiku-4-5-20251001" not in result["by_model_7d"]
        assert result["by_model_30d"]["claude-opus-4-6"]["input"] == 3000
        assert result["by_model_30d"]["claude-haiku-4-5-20251001"]["input"] == 3000

    def test_by_project_today(self, tmp_claude_dir):
        ts = _today_ts()
        for pname in ["-Users-test-proj-a", "-Users-test-proj-b"]:
            _make_session_file(tmp_claude_dir, pname, "sess", [
                _make_assistant_entry("claude-opus-4-6", 800, 200, ts),
            ])
        result = bridge.scan_token_usage()
        assert result["by_project"]["-Users-test-proj-a"] == 1000
        assert result["by_project"]["-Users-test-proj-b"] == 1000

    def test_by_session(self, tmp_claude_dir):
        ts = _today_ts()
        for sid in ["aaa111", "bbb222"]:
            _make_session_file(tmp_claude_dir, "-Users-test-proj-s", sid, [
                _make_assistant_entry("claude-opus-4-6", 600, 100, ts),
            ])
        result = bridge.scan_token_usage()
        assert result["by_session"]["aaa111"] == 700
        assert result["by_session"]["bbb222"] == 700

    def test_skips_synthetic(self, tmp_claude_dir):
        ts = _today_ts()
        _make_session_file(tmp_claude_dir, "-Users-test-syn", "syn1", [
            _make_assistant_entry("<synthetic>", 1000, 200, ts),
            _make_assistant_entry("claude-opus-4-6", 500, 100, ts),
        ])
        result = bridge.scan_token_usage()
        assert result["totals"]["today"]["input"] == 500
        assert "<synthetic>" not in result["by_model"]

    def test_skips_old_mtime(self, tmp_claude_dir):
        ts = _today_ts()
        f = _make_session_file(tmp_claude_dir, "-Users-test-old", "old1", [
            _make_assistant_entry("claude-opus-4-6", 1000, 200, ts),
        ])
        old_time = time.time() - 40 * 86400
        os.utime(f, (old_time, old_time))
        result = bridge.scan_token_usage()
        assert result["totals"]["today"]["input"] == 0

    def test_skips_user_entries(self, tmp_claude_dir):
        ts = _today_ts()
        _make_session_file(tmp_claude_dir, "-Users-test-user", "u1", [
            _make_user_entry(ts),
            _make_assistant_entry("claude-opus-4-6", 500, 100, ts),
        ])
        result = bridge.scan_token_usage()
        assert result["totals"]["today"]["input"] == 500

    def test_cache_tokens(self, tmp_claude_dir):
        ts = _today_ts()
        _make_session_file(tmp_claude_dir, "-Users-test-cache", "c1", [
            _make_assistant_entry("claude-opus-4-6", 1000, 200, ts,
                                 cache_read=5000, cache_creation=1000),
        ])
        result = bridge.scan_token_usage()
        assert result["cache_today"]["read"] == 5000
        assert result["cache_today"]["creation"] == 1000

    def test_yesterday_totals(self, tmp_claude_dir):
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        ts = f"{yesterday}T10:00:00Z"
        _make_session_file(tmp_claude_dir, "-Users-test-yest", "y1", [
            _make_assistant_entry("claude-opus-4-6", 800, 200, ts),
        ])
        result = bridge.scan_token_usage()
        assert result["totals"]["yesterday"]["input"] == 800
        assert result["totals"]["yesterday"]["output"] == 200
        assert result["totals"]["today"]["input"] == 0

    def test_session_project_mapping(self, tmp_claude_dir):
        ts = _today_ts()
        _make_session_file(tmp_claude_dir, "-Users-test-myapp", "sess-abc", [
            _make_assistant_entry("claude-opus-4-6", 500, 100, ts),
        ])
        result = bridge.scan_token_usage()
        assert result["session_project"]["sess-abc"] == "-Users-test-myapp"


class TestHelperFunctions:
    """Test helper functions for report formatting."""

    def test_bar_full(self):
        assert bridge._bar(1.0) == "██████"

    def test_bar_empty(self):
        assert bridge._bar(0.0) == "░░░░░░"

    def test_bar_half(self):
        result = bridge._bar(0.5)
        assert "█" in result
        assert "░" in result

    def test_change_indicator_up(self):
        result = bridge._change_indicator(200, 100)
        assert "↑" in result
        assert "100%" in result

    def test_change_indicator_down(self):
        result = bridge._change_indicator(50, 100)
        assert "↓" in result
        assert "50%" in result

    def test_change_indicator_stable(self):
        assert "→" in bridge._change_indicator(100, 100)

    def test_change_indicator_no_yesterday(self):
        assert bridge._change_indicator(100, 0) == ""

    def test_estimate_cost_opus(self):
        cost = bridge._estimate_cost("claude-opus-4-6", 1_000_000, 100_000)
        assert abs(cost - 22.5) < 0.01

    def test_estimate_cost_sonnet(self):
        cost = bridge._estimate_cost("claude-sonnet-4-5-20250929", 1_000_000, 1_000_000)
        assert abs(cost - 18.0) < 0.01

    def test_estimate_cost_haiku(self):
        cost = bridge._estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
        assert abs(cost - 1.5) < 0.01

    def test_estimate_cost_unknown(self):
        assert bridge._estimate_cost("unknown-model", 1_000_000, 1_000_000) == 0.0

    def test_model_cost_key(self):
        assert bridge._model_cost_key("claude-opus-4-6") == "opus"
        assert bridge._model_cost_key("claude-sonnet-4-5-20250929") == "sonnet"
        assert bridge._model_cost_key("claude-haiku-4-5-20251001") == "haiku"
        assert bridge._model_cost_key("unknown") == ""


class TestFormatTokenReport:
    """Test report formatting output."""

    def test_empty_data(self):
        result = bridge.format_token_report({})
        assert "📊 Token Usage Report" in result
        assert "Today: -" in result

    def test_basic_format(self):
        data = _empty_report(totals={
            "today": {"input": 210100, "output": 35200},
            "yesterday": {"input": 0, "output": 0},
            "7d": {"input": 1000000, "output": 200500},
            "30d": {"input": 4900000, "output": 891200},
        })
        result = bridge.format_token_report(data)
        assert "Today: 245.3K" in result
        assert "Week: 1.2M" in result
        assert "Month: 5.8M" in result

    def test_k_suffix(self):
        assert bridge._format_tokens(1500) == "1.5K"
        assert bridge._format_tokens(245300) == "245.3K"

    def test_m_suffix(self):
        assert bridge._format_tokens(1200500) == "1.2M"
        assert bridge._format_tokens(5791200) == "5.8M"

    def test_zero_shows_dash(self):
        assert bridge._format_tokens(0) == "-"

    def test_small_number(self):
        assert bridge._format_tokens(500) == "500"

    def test_model_section_with_bars(self):
        data = _empty_report(by_model={
            "claude-opus-4-6": {"input": 150000, "output": 50100},
            "claude-haiku-4-5-20251001": {"input": 40000, "output": 5200},
        })
        result = bridge.format_token_report(data)
        assert "📦 By Model (today)" in result
        assert "Opus 4.6: 200.1K" in result
        assert "Haiku 4.5: 45.2K" in result
        assert "█" in result
        assert "%" in result

    def test_model_cost_estimation(self):
        data = _empty_report(
            totals={
                "today": {"input": 1000000, "output": 100000},
                "yesterday": {"input": 0, "output": 0},
                "7d": {"input": 2000000, "output": 200000},
                "30d": {"input": 5000000, "output": 500000},
            },
            by_model={"claude-opus-4-6": {"input": 1000000, "output": 100000}},
            by_model_7d={"claude-opus-4-6": {"input": 2000000, "output": 200000}},
            by_model_30d={"claude-opus-4-6": {"input": 5000000, "output": 500000}},
        )
        result = bridge.format_token_report(data)
        assert "Today:" in result and "$22.50" in result
        assert "Week:" in result and "$45.00" in result
        assert "Month:" in result and "$112.50" in result

    def test_session_top3(self):
        sessions = {f"session-{i:04d}-abcd-efgh": (6 - i) * 10000 for i in range(6)}
        data = _empty_report(by_session=sessions)
        result = bridge.format_token_report(data)
        assert "🔗 By Session (today, top 3)" in result
        session_lines = [l for l in result.split("\n") if "…" in l]
        assert len(session_lines) == 3

    def test_session_with_project_name(self):
        data = _empty_report(
            by_session={"abc12345-uuid": 10000},
            session_project={"abc12345-uuid": "-Users-test-myapp"},
        )
        result = bridge.format_token_report(data)
        assert "[" in result
        assert "]" in result

    def test_cache_with_hit_rate(self):
        data = _empty_report(
            totals={
                "today": {"input": 100000, "output": 50000},
                "yesterday": {"input": 0, "output": 0},
                "7d": {"input": 0, "output": 0},
                "30d": {"input": 0, "output": 0},
            },
            cache_today={"read": 400000, "creation": 50000},
        )
        result = bridge.format_token_report(data)
        assert "Cache today:" in result
        assert "hit 80%" in result

    def test_yesterday_comparison_up(self):
        data = _empty_report(totals={
            "today": {"input": 200000, "output": 50000},
            "yesterday": {"input": 100000, "output": 25000},
            "7d": {"input": 0, "output": 0},
            "30d": {"input": 0, "output": 0},
        })
        result = bridge.format_token_report(data)
        assert "↑" in result
        assert "100%" in result

    def test_yesterday_comparison_down(self):
        data = _empty_report(totals={
            "today": {"input": 50000, "output": 10000},
            "yesterday": {"input": 200000, "output": 50000},
            "7d": {"input": 0, "output": 0},
            "30d": {"input": 0, "output": 0},
        })
        result = bridge.format_token_report(data)
        assert "↓" in result
