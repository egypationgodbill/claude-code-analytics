import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from metrics import (
    compute_prompt_metrics,
    compute_tool_metrics,
    compute_efficiency_metrics,
    compute_temporal_metrics,
    compute_model_metrics,
    _short_model_name,
    compute_thematic_analysis,
    compute_history_metrics,
)


def _make_session(**overrides):
    """Create a minimal valid session dict."""
    base = {
        "id": "test-sid",
        "project": "test-project",
        "slug": "test session",
        "human_messages": [
            {
                "text": "Fix the bug in auth.py",
                "timestamp": datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
                "word_count": 6,
                "char_count": 22,
            }
        ],
        "assistant_tool_calls": [
            {"name": "Read", "timestamp": datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc), "input_summary": "auth.py"},
        ],
        "total_assistant_blocks": 2,
        "subagent_types": [],
        "all_timestamps": [datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)],
        "start_time": datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        "end_time": datetime(2024, 1, 15, 12, 30, tzinfo=timezone.utc),
        "duration_minutes": 30,
        "models_used": ["claude-sonnet-4-6"],
        "model_usage": [
            {
                "model": "claude-sonnet-4-6",
                "input_tokens": 1000,
                "cache_read": 500,
                "cache_creation": 0,
                "output_tokens": 200,
                "total_context": 1500,
                "context_window": 200000,
                "utilization_pct": 0.75,
                "timestamp": "2024-01-15T12:00:00+00:00",
            }
        ],
        "cwd": "/tmp",
        "version": "1.0",
    }
    base.update(overrides)
    return base


def _sessions_dict(*sessions):
    return {s["id"]: s for s in sessions}


def test_compute_prompt_metrics_basic():
    sessions = _sessions_dict(_make_session())
    result = compute_prompt_metrics(sessions)
    assert result["total_prompts"] == 1
    assert result["avg_words"] == 6.0
    assert result["median_words"] == 6
    assert result["avg_chars"] == 22.0
    assert result["max_words"] == 6
    assert result["min_words"] == 6
    assert result["distribution"]["1-5"] == 0
    assert result["distribution"]["6-15"] == 1
    assert len(result["timeline"]) == 1


def test_compute_prompt_metrics_empty():
    result = compute_prompt_metrics({})
    assert result.get("empty") is True


def test_compute_tool_metrics_basic():
    sessions = _sessions_dict(_make_session())
    result = compute_tool_metrics(sessions)
    assert result["total_tool_calls"] == 1
    assert result["tool_frequency"]["Read"] == 1
    assert result["tools_per_message"] == 1.0
    assert result["unique_tools_used"] == 1


def test_compute_efficiency_metrics_basic():
    sessions = _sessions_dict(_make_session())
    result = compute_efficiency_metrics(sessions)
    assert result["total_sessions"] == 1
    assert result["avg_duration"] == 30.0
    assert result["avg_messages_per_session"] == 1.0
    s = result["sessions"][0]
    assert s["tools_per_message"] == 1.0
    assert s["avg_prompt_words"] == 6.0


def test_compute_temporal_metrics_basic():
    sessions = _sessions_dict(_make_session())
    result = compute_temporal_metrics(sessions)
    assert sum(result["hour_counts"].values()) == 1
    assert sum(result["day_counts"].values()) == 1
    assert len(result["heatmap"]) == 1
    assert len(result["daily_avg_prompt_length"]) == 1


def test_compute_model_metrics_basic():
    sessions = _sessions_dict(_make_session())
    result = compute_model_metrics(sessions)
    assert "Sonnet 4.6" in result["model_summary"]
    summary = result["model_summary"]["Sonnet 4.6"]
    assert summary["messages"] == 1
    assert summary["input_tokens"] == 1000
    assert summary["output_tokens"] == 200
    assert summary["cache_read"] == 500
    assert result["context_utilization_distribution"]["0-25%"] == 1


def test_compute_thematic_analysis_debugging():
    s = _make_session(
        id="debug-sid",
        human_messages=[
            {
                "text": "debug the error in auth module traceback",
                "timestamp": datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
                "word_count": 7,
                "char_count": 40,
            }
        ]
    )
    sessions = _sessions_dict(s)
    result = compute_thematic_analysis(sessions)
    assert "category_counts" in result
    cats = result["session_categories"]
    assert len(cats) == 1
    assert cats[0]["category"] == "debugging"


def test_short_model_name():
    assert _short_model_name("claude-opus-4-6") == "Opus 4.6"
    assert _short_model_name("claude-sonnet-4-5-20250929") == "Sonnet 4.5"
    assert _short_model_name("claude-sonnet-4-6") == "Sonnet 4.6"
    assert _short_model_name("claude-haiku-4-5-20251001") == "Haiku 4.5"
    assert _short_model_name("") == "unknown"
    assert _short_model_name(None) == "unknown"


def test_compute_thematic_analysis_uncategorized():
    s = _make_session(
        id="generic-sid",
        human_messages=[
            {
                "text": "hello",
                "timestamp": datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
                "word_count": 1,
                "char_count": 5,
            }
        ],
        assistant_tool_calls=[],
    )
    sessions = _sessions_dict(s)
    result = compute_thematic_analysis(sessions)
    assert result["session_categories"][0]["category"] == "uncategorized"


def test_compute_history_metrics_basic():
    entries = [
        {"display": "/commit fix auth", "timestamp": 1000},
        {"display": "/analytics --days 7", "timestamp": 2000},
        {"display": "regular prompt", "timestamp": 3000},
    ]
    result = compute_history_metrics(entries)
    assert result["total_history_entries"] == 3
    assert "/commit" in result["slash_commands"]
    assert "/analytics" in result["slash_commands"]
