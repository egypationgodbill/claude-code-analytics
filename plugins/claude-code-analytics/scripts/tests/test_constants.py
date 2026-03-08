from pathlib import Path

from constants import (
    CLAUDE_DIR, PROJECTS_DIR, HISTORY_FILE, STATS_FILE,
    LOCAL_UTC_OFFSET_HOURS, STOPWORDS, MODEL_CONTEXT_WINDOWS,
    get_context_window, to_local_hour, to_local_weekday, parse_timestamp,
)
from datetime import datetime, timezone


def test_get_context_window_known_model():
    assert get_context_window("claude-opus-4-something") == 200000

def test_get_context_window_unknown_model():
    assert get_context_window("gpt-4") == 200000

def test_get_context_window_none():
    assert get_context_window(None) == 200000

def test_to_local_hour_returns_0_to_23():
    dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    h = to_local_hour(dt)
    assert 0 <= h <= 23

def test_to_local_weekday_returns_day_name():
    dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    day = to_local_weekday(dt)
    assert day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

def test_parse_timestamp_valid():
    ts = parse_timestamp("2024-01-15T12:00:00.000Z")
    assert ts is not None
    assert ts.year == 2024
    assert ts.month == 1
    assert ts.tzinfo is not None

def test_parse_timestamp_none():
    assert parse_timestamp(None) is None

def test_parse_timestamp_empty():
    assert parse_timestamp("") is None

def test_parse_timestamp_invalid():
    assert parse_timestamp("not-a-date") is None

def test_stopwords_is_frozenset():
    assert isinstance(STOPWORDS, frozenset)
    assert "the" in STOPWORDS

def test_claude_dir_is_path():
    assert isinstance(CLAUDE_DIR, Path)
