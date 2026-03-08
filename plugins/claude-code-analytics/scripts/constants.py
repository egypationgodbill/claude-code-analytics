"""Constants and pure utility helpers for Claude Code analytics."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
STATS_FILE = CLAUDE_DIR / "stats-cache.json"

# Detect local timezone offset once at startup
LOCAL_UTC_OFFSET_HOURS = round(
    datetime.now(timezone.utc).astimezone().utcoffset().total_seconds() / 3600
)

STOPWORDS = frozenset(
    "the a an and or but in on at to for of is it this that with from by as be "
    "are was were been has have had do does did will would can could should may "
    "might shall not no yes i me my we our you your he she they them their its "
    "so if then else when how what which who whom where why all any each every "
    "some just also very too quite rather really still already only about into "
    "over after before between through during without above below up down out "
    "off again further more most other such than now here there please let make "
    "use like need want get got don't doesn't didn't won't can't couldn't "
    "shouldn't wouldn't file code run look thing way see".split()
)

# Known context window sizes per model family
MODEL_CONTEXT_WINDOWS = {
    "claude-opus-4": 200000,
    "claude-sonnet-4": 200000,
    "claude-haiku-4": 200000,
    "claude-3-5-sonnet": 200000,
    "claude-3-5-haiku": 200000,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
}


def get_context_window(model_name):
    """Get context window size for a model, defaulting to 200k."""
    if not model_name:
        return 200000
    for prefix, size in MODEL_CONTEXT_WINDOWS.items():
        if model_name.startswith(prefix):
            return size
    return 200000


def to_local_hour(utc_dt):
    """Convert UTC datetime to local hour (0-23)."""
    return (utc_dt.hour + LOCAL_UTC_OFFSET_HOURS) % 24


def to_local_weekday(utc_dt):
    """Convert UTC datetime to local weekday name."""
    local_dt = utc_dt + timedelta(hours=LOCAL_UTC_OFFSET_HOURS)
    return local_dt.strftime("%A")


def parse_timestamp(ts_str):
    """Parse ISO timestamp string to datetime (UTC)."""
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        if sys.version_info >= (3, 11):
            return datetime.fromisoformat(ts_str)
        if "+" in ts_str[10:]:
            ts_str = ts_str[:ts_str.rindex("+")]
        elif ts_str.endswith("+00:00"):
            ts_str = ts_str[:-6]
        return datetime.strptime(ts_str[:26], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None
