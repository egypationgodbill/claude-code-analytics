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
    assert result["avg_words"] == 6
    assert "distribution" in result
    assert "timeline" in result


def test_compute_prompt_metrics_empty():
    result = compute_prompt_metrics({})
    assert result.get("empty") is True


def test_compute_tool_metrics_basic():
    sessions = _sessions_dict(_make_session())
    result = compute_tool_metrics(sessions)
    assert result["total_tool_calls"] == 1
    assert "Read" in result["tool_frequency"]


def test_compute_efficiency_metrics_basic():
    sessions = _sessions_dict(_make_session())
    result = compute_efficiency_metrics(sessions)
    assert result["total_sessions"] == 1
    assert len(result["sessions"]) == 1


def test_compute_temporal_metrics_basic():
    sessions = _sessions_dict(_make_session())
    result = compute_temporal_metrics(sessions)
    assert "hour_counts" in result
    assert "day_counts" in result
    assert "heatmap" in result


def test_compute_model_metrics_basic():
    sessions = _sessions_dict(_make_session())
    result = compute_model_metrics(sessions)
    assert "model_summary" in result
    assert "context_utilization_distribution" in result


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
