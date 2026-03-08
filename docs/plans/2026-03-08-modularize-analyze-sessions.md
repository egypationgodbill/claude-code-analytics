# Modularize analyze_sessions.py

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split the 1090-line monolith `analyze_sessions.py` into 6 focused modules with single responsibilities.

**Architecture:** Extract constants, parsers, metrics, suggestions, and report generation into separate modules. The entry point (`analyze_sessions.py`) becomes a thin CLI orchestrator. All modules live in `scripts/` as sibling files — no package/`__init__.py` needed since the script is invoked via `python3 path/to/analyze_sessions.py`.

**Tech Stack:** Python 3.7+, no external dependencies (stdlib only).

---

### Task 1: Create constants.py — constants and pure utility helpers

**Files:**
- Create: `plugins/claude-code-analytics/scripts/constants.py`
- Test: `plugins/claude-code-analytics/scripts/tests/test_constants.py`

**Step 1: Write the failing tests**

Create test directory and test file:

```bash
mkdir -p plugins/claude-code-analytics/scripts/tests
```

```python
# tests/test_constants.py
import sys
from pathlib import Path

# Allow imports from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)  # Monday UTC
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
```

**Step 2: Run tests to verify they fail**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_constants.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'constants'`

**Step 3: Write constants.py**

Extract from `analyze_sessions.py` lines 1-70 (imports, constants, and the 4 helper functions: `get_context_window`, `to_local_hour`, `to_local_weekday`, `parse_timestamp`):

```python
"""
Constants and pure utility helpers for the Claude Code analytics pipeline.
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
STATS_FILE = CLAUDE_DIR / "stats-cache.json"

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
```

**Step 4: Run tests to verify they pass**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_constants.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add plugins/claude-code-analytics/scripts/constants.py plugins/claude-code-analytics/scripts/tests/
git commit -m "refactor: extract constants.py from analyze_sessions"
```

---

### Task 2: Create parsers.py — session/history/stats file parsing

**Files:**
- Create: `plugins/claude-code-analytics/scripts/parsers.py`
- Test: `plugins/claude-code-analytics/scripts/tests/test_parsers.py`

**Step 1: Write the failing tests**

```python
# tests/test_parsers.py
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parsers import (
    parse_session_file,
    _process_assistant_content,
    _summarize_tool_input,
    load_history,
    load_stats_cache,
)


def _write_jsonl(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_parse_session_file_basic():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        records = [
            {
                "type": "user",
                "timestamp": "2024-01-15T12:00:00.000Z",
                "message": {"content": "Hello world test prompt"},
            },
            {
                "type": "assistant",
                "uuid": "abc-123",
                "timestamp": "2024-01-15T12:00:05.000Z",
                "message": {
                    "content": [{"type": "text", "text": "Hi there"}],
                    "model": "claude-sonnet-4-6",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            },
        ]
        _write_jsonl(f.name, records)
        session = parse_session_file(Path(f.name), "test-sid", "test-project", None)

    assert session is not None
    assert len(session["human_messages"]) == 1
    assert session["human_messages"][0]["text"] == "Hello world test prompt"
    assert session["project"] == "test-project"
    assert "claude-sonnet-4-6" in session["models_used"]


def test_parse_session_file_skips_meta():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        records = [
            {
                "type": "user",
                "timestamp": "2024-01-15T12:00:00.000Z",
                "isMeta": True,
                "message": {"content": "meta message"},
            },
            {
                "type": "user",
                "timestamp": "2024-01-15T12:00:01.000Z",
                "message": {"content": "real message"},
            },
        ]
        _write_jsonl(f.name, records)
        session = parse_session_file(Path(f.name), "sid", "proj", None)

    assert len(session["human_messages"]) == 1
    assert session["human_messages"][0]["text"] == "real message"


def test_parse_session_file_deduplicates_uuid():
    """Streaming creates partial records with same uuid — only last should be kept."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        records = [
            {
                "type": "user",
                "timestamp": "2024-01-15T12:00:00.000Z",
                "message": {"content": "prompt"},
            },
            {
                "type": "assistant",
                "uuid": "same-uuid",
                "timestamp": "2024-01-15T12:00:01.000Z",
                "message": {
                    "content": [{"type": "text", "text": "partial"}],
                    "model": "claude-sonnet-4-6",
                    "usage": {"input_tokens": 50, "output_tokens": 10},
                },
            },
            {
                "type": "assistant",
                "uuid": "same-uuid",
                "timestamp": "2024-01-15T12:00:02.000Z",
                "message": {
                    "content": [{"type": "text", "text": "complete"}],
                    "model": "claude-sonnet-4-6",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            },
        ]
        _write_jsonl(f.name, records)
        session = parse_session_file(Path(f.name), "sid", "proj", None)

    assert session["total_assistant_blocks"] == 1
    assert session["model_usage"][0]["input_tokens"] == 100


def test_summarize_tool_input_read():
    assert _summarize_tool_input("Read", {"file_path": "/foo/bar.py"}) == "/foo/bar.py"


def test_summarize_tool_input_bash():
    assert _summarize_tool_input("Bash", {"command": "ls -la"}) == "ls -la"


def test_summarize_tool_input_unknown():
    result = _summarize_tool_input("CustomTool", {"key": "value"})
    assert isinstance(result, str)


def test_load_history_empty(tmp_path):
    """load_history returns [] when file doesn't exist."""
    import parsers
    original = parsers.HISTORY_FILE
    parsers.HISTORY_FILE = tmp_path / "nonexistent.jsonl"
    result = load_history(30, None, False)
    parsers.HISTORY_FILE = original
    assert result == []


def test_load_stats_cache_missing(tmp_path):
    """load_stats_cache returns {} when file doesn't exist."""
    import parsers
    original = parsers.STATS_FILE
    parsers.STATS_FILE = tmp_path / "nonexistent.json"
    result = load_stats_cache()
    parsers.STATS_FILE = original
    assert result == {}
```

**Step 2: Run tests to verify they fail**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_parsers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'parsers'`

**Step 3: Write parsers.py**

Extract from `analyze_sessions.py`: `collect_sessions`, `parse_session_file`, `_process_assistant_content`, `_summarize_tool_input`, `load_history`, `load_stats_cache`.

```python
"""
Data collection — parse session JSONL files, history, and stats cache.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from constants import (
    PROJECTS_DIR, HISTORY_FILE, STATS_FILE,
    get_context_window, parse_timestamp,
)


def collect_sessions(days, project_filter, session_filter, use_all):
    """Walk ~/.claude/projects/ and parse session JSONL files."""
    cutoff = None
    if not use_all and days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    sessions = {}
    project_dirs = []

    if not PROJECTS_DIR.exists():
        print("No projects directory found at ~/.claude/projects/", file=sys.stderr)
        return sessions

    for pdir in PROJECTS_DIR.iterdir():
        if not pdir.is_dir():
            continue
        pname = pdir.name
        if project_filter and project_filter.lower() not in pname.lower():
            continue
        project_dirs.append(pdir)

    for pdir in project_dirs:
        pname = pdir.name
        for jfile in pdir.glob("*.jsonl"):
            sid = jfile.stem
            if session_filter and not sid.startswith(session_filter):
                continue

            session = parse_session_file(jfile, sid, pname, cutoff)
            if session and session["human_messages"]:
                sessions[sid] = session

        subagent_dir = pdir / "subagents"
        if subagent_dir.exists():
            for meta_file in subagent_dir.glob("agent-*.meta.json"):
                try:
                    meta = json.loads(meta_file.read_text())
                    parent_sid = meta.get("parentSessionId", "")
                    if parent_sid in sessions:
                        agent_type = meta.get("type", "unknown")
                        sessions[parent_sid]["subagent_types"].append(agent_type)
                except (json.JSONDecodeError, IOError):
                    pass

    return sessions


def parse_session_file(filepath, session_id, project_name, cutoff):
    """Parse a single session JSONL file."""
    session = {
        "id": session_id,
        "project": project_name,
        "human_messages": [],
        "assistant_tool_calls": [],
        "total_assistant_blocks": 0,
        "subagent_types": [],
        "all_timestamps": [],
        "slug": "",
        "cwd": "",
        "version": "",
        "model_usage": [],
        "models_used": set(),
    }

    seen_uuids = {}
    first_ts = None

    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                rtype = record.get("type")
                ts_str = record.get("timestamp")
                ts = parse_timestamp(ts_str) if ts_str else None

                if ts:
                    session["all_timestamps"].append(ts)
                    if first_ts is None:
                        first_ts = ts

                if not session["slug"] and record.get("slug"):
                    session["slug"] = record["slug"]
                if not session["cwd"] and record.get("cwd"):
                    session["cwd"] = record["cwd"]
                if not session["version"] and record.get("version"):
                    session["version"] = record["version"]

                if rtype == "user":
                    msg = record.get("message", {})
                    content = msg.get("content", "")
                    is_meta = record.get("isMeta", False)

                    if isinstance(content, str) and content.strip() and not is_meta:
                        session["human_messages"].append({
                            "text": content.strip(),
                            "timestamp": ts,
                            "word_count": len(content.split()),
                            "char_count": len(content),
                        })

                elif rtype == "assistant":
                    uuid = record.get("uuid", "")
                    msg = record.get("message", {})
                    content = msg.get("content", [])
                    model = msg.get("model", "")
                    usage = msg.get("usage", {})

                    if uuid:
                        seen_uuids[uuid] = {
                            "content": content,
                            "model": model,
                            "usage": usage,
                            "timestamp": ts,
                        }
                    elif not uuid:
                        _process_assistant_content(session, content, model, usage, ts)

    except (IOError, OSError) as e:
        print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)
        return None

    for uid, data in seen_uuids.items():
        _process_assistant_content(
            session, data["content"], data["model"], data["usage"], data["timestamp"]
        )

    if cutoff and first_ts and first_ts < cutoff:
        return None

    session["start_time"] = first_ts
    if session["all_timestamps"]:
        session["end_time"] = max(session["all_timestamps"])
        session["duration_minutes"] = (
            (session["end_time"] - min(session["all_timestamps"])).total_seconds() / 60
        )
    else:
        session["end_time"] = first_ts
        session["duration_minutes"] = 0

    session["models_used"] = list(session["models_used"])

    return session


def _process_assistant_content(session, content, model, usage, ts):
    """Process a deduplicated assistant message's content, model, and usage."""
    if model and model != "<synthetic>":
        session["models_used"].add(model)

    if usage:
        input_tokens = usage.get("input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_creation = usage.get("cache_creation_input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_context = input_tokens + cache_read + cache_creation

        if total_context > 0 or output_tokens > 0:
            session["model_usage"].append({
                "model": model or "unknown",
                "input_tokens": input_tokens,
                "cache_read": cache_read,
                "cache_creation": cache_creation,
                "output_tokens": output_tokens,
                "total_context": total_context,
                "context_window": get_context_window(model),
                "utilization_pct": round(total_context / get_context_window(model) * 100, 1) if total_context > 0 else 0,
                "timestamp": ts.isoformat() if ts else None,
            })

    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    session["assistant_tool_calls"].append({
                        "name": tool_name,
                        "timestamp": ts,
                        "input_summary": _summarize_tool_input(tool_name, tool_input),
                    })
                session["total_assistant_blocks"] += 1


def _summarize_tool_input(tool_name, tool_input):
    """Create a brief summary of tool input for display."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name in ("Read", "Write", "Edit"):
        return tool_input.get("file_path", "")[:80]
    if tool_name == "Bash":
        return tool_input.get("command", "")[:80]
    if tool_name == "Grep":
        return tool_input.get("pattern", "")[:60]
    if tool_name == "Glob":
        return tool_input.get("pattern", "")[:60]
    if tool_name == "Agent":
        return tool_input.get("prompt", "")[:80]
    if tool_name == "Skill":
        return tool_input.get("skill", "")
    if tool_name == "ToolSearch":
        return tool_input.get("query", "")[:60]
    return str(tool_input)[:60]


def load_history(days, project_filter, use_all):
    """Load history.jsonl for slash command and prompt history."""
    entries = []
    if not HISTORY_FILE.exists():
        return entries

    cutoff_ms = None
    if not use_all and days:
        cutoff_ms = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000

    try:
        with open(HISTORY_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts_val = entry.get("timestamp", 0)
                if cutoff_ms and ts_val < cutoff_ms:
                    continue

                proj = entry.get("project", "")
                if project_filter and project_filter.lower() not in proj.lower():
                    continue

                entries.append(entry)
    except IOError:
        pass

    return entries


def load_stats_cache():
    """Load stats-cache.json if available."""
    if not STATS_FILE.exists():
        return {}
    try:
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}
```

**Step 4: Run tests to verify they pass**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_parsers.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add plugins/claude-code-analytics/scripts/parsers.py plugins/claude-code-analytics/scripts/tests/test_parsers.py
git commit -m "refactor: extract parsers.py from analyze_sessions"
```

---

### Task 3: Create metrics.py — all compute_* functions

**Files:**
- Create: `plugins/claude-code-analytics/scripts/metrics.py`
- Test: `plugins/claude-code-analytics/scripts/tests/test_metrics.py`

**Step 1: Write the failing tests**

```python
# tests/test_metrics.py
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


def test_compute_thematic_analysis_basic():
    s = _make_session(human_messages=[
        {
            "text": "debug the error in auth module traceback",
            "timestamp": datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            "word_count": 7,
            "char_count": 40,
        }
    ])
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
```

**Step 2: Run tests to verify they fail**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'metrics'`

**Step 3: Write metrics.py**

Extract all 7 `compute_*` functions and `_short_model_name` from `analyze_sessions.py`:

```python
"""
Metrics computation — prompt quality, tool usage, efficiency, temporal,
model/context, thematic analysis, and history metrics.
"""

import re
from collections import Counter, defaultdict
from datetime import timedelta

from constants import (
    LOCAL_UTC_OFFSET_HOURS, STOPWORDS,
    get_context_window, to_local_hour, to_local_weekday,
)


def compute_prompt_metrics(sessions):
    # ... (lines 365-448 from original, unchanged)


def compute_tool_metrics(sessions):
    # ... (lines 451-489 from original, unchanged)


def compute_efficiency_metrics(sessions):
    # ... (lines 492-528 from original, unchanged)


def compute_temporal_metrics(sessions):
    # ... (lines 531-574 from original, unchanged)


def compute_model_metrics(sessions):
    # ... (lines 577-669 from original, unchanged)


def _short_model_name(model):
    # ... (lines 672-694 from original, unchanged)


def compute_thematic_analysis(sessions):
    # ... (lines 697-817 from original, unchanged)


def compute_history_metrics(history_entries):
    # ... (lines 820-832 from original, unchanged)
```

(Full function bodies are identical to the original — just copy them verbatim.)

**Step 4: Run tests to verify they pass**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_metrics.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add plugins/claude-code-analytics/scripts/metrics.py plugins/claude-code-analytics/scripts/tests/test_metrics.py
git commit -m "refactor: extract metrics.py from analyze_sessions"
```

---

### Task 4: Create suggestions.py — suggestion engine

**Files:**
- Create: `plugins/claude-code-analytics/scripts/suggestions.py`
- Test: `plugins/claude-code-analytics/scripts/tests/test_suggestions.py`

**Step 1: Write the failing tests**

```python
# tests/test_suggestions.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from suggestions import generate_suggestions


def test_empty_metrics_returns_info():
    result = generate_suggestions({"empty": True}, {}, {}, {}, {})
    assert len(result) == 1
    assert result[0]["type"] == "info"


def test_short_prompts_many_messages_suggests_context():
    prompt = {"avg_words": 10, "specificity_rate": 50, "question_ratio": 20,
              "file_ref_rate": 10, "code_block_rate": 5, "timeline": []}
    efficiency = {"avg_messages_per_session": 15, "sessions": []}
    result = generate_suggestions(prompt, {"plan_mode_count": 0}, efficiency, {}, {})
    titles = [s["title"] for s in result]
    assert "Add More Upfront Context" in titles


def test_short_prompts_few_messages_positive():
    prompt = {"avg_words": 10, "specificity_rate": 50, "question_ratio": 20,
              "file_ref_rate": 10, "code_block_rate": 5, "timeline": []}
    efficiency = {"avg_messages_per_session": 3, "sessions": []}
    result = generate_suggestions(prompt, {"plan_mode_count": 0}, efficiency, {}, {})
    titles = [s["title"] for s in result]
    assert "Efficient Short Prompts" in titles


def test_no_signals_returns_looking_good():
    prompt = {"avg_words": 25, "specificity_rate": 50, "question_ratio": 30,
              "file_ref_rate": 10, "code_block_rate": 5, "timeline": []}
    efficiency = {"avg_messages_per_session": 5, "sessions": []}
    tools = {"plan_mode_count": 1, "subagent_types": {}}
    result = generate_suggestions(prompt, tools, efficiency, {}, {})
    titles = [s["title"] for s in result]
    assert "Looking Good" in titles


def test_high_context_window_warning():
    prompt = {"avg_words": 25, "specificity_rate": 50, "question_ratio": 30,
              "file_ref_rate": 10, "code_block_rate": 5, "timeline": []}
    efficiency = {"avg_messages_per_session": 5, "sessions": []}
    tools = {"plan_mode_count": 1, "subagent_types": {}}
    model = {"sessions_over_75pct": 3, "max_utilization": 95, "avg_peak_utilization": 60}
    result = generate_suggestions(prompt, tools, efficiency, {}, model)
    titles = [s["title"] for s in result]
    assert "High Context Window Usage" in titles
```

**Step 2: Run tests to verify they fail**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_suggestions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'suggestions'`

**Step 3: Write suggestions.py**

```python
"""
Suggestion engine — generates actionable suggestions from computed metrics.
"""


def generate_suggestions(prompt_metrics, tool_metrics, efficiency, themes, model_metrics):
    # ... (lines 838-998 from original, unchanged — the full generate_suggestions function)
```

(Full function body is identical to the original.)

**Step 4: Run tests to verify they pass**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_suggestions.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add plugins/claude-code-analytics/scripts/suggestions.py plugins/claude-code-analytics/scripts/tests/test_suggestions.py
git commit -m "refactor: extract suggestions.py from analyze_sessions"
```

---

### Task 5: Create report.py — HTML report generation

**Files:**
- Create: `plugins/claude-code-analytics/scripts/report.py`
- Test: `plugins/claude-code-analytics/scripts/tests/test_report.py`

**Step 1: Write the failing tests**

```python
# tests/test_report.py
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from report import generate_report


def test_generate_report_injects_data(tmp_path):
    template = tmp_path / "template.html"
    template.write_text("<html>/*__REPORT_DATA__*/</html>")
    output = tmp_path / "report.html"

    data = {"key": "value", "count": 42}
    result = generate_report(data, str(output), str(template))

    assert result == str(output)
    content = output.read_text()
    assert "window.__REPORT_DATA__" in content
    assert '"key": "value"' in content


def test_generate_report_missing_template(tmp_path):
    """Should exit with error when template is missing."""
    import pytest
    output = tmp_path / "report.html"
    with pytest.raises(SystemExit):
        generate_report({}, str(output), str(tmp_path / "nonexistent.html"))
```

**Step 2: Run tests to verify they fail**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'report'`

**Step 3: Write report.py**

```python
"""
Report generation — inject metrics data into the HTML template.
"""

import json
import sys


def generate_report(data, output_path, template_path):
    """Generate the HTML report by injecting data into template."""
    try:
        with open(template_path, "r") as f:
            template = f.read()
    except IOError:
        print(f"Error: Template not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    data_json = json.dumps(data, indent=None, default=str)
    html = template.replace("/*__REPORT_DATA__*/", f"window.__REPORT_DATA__ = {data_json};")

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Report generated: {output_path}")
    return output_path
```

**Step 4: Run tests to verify they pass**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_report.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add plugins/claude-code-analytics/scripts/report.py plugins/claude-code-analytics/scripts/tests/test_report.py
git commit -m "refactor: extract report.py from analyze_sessions"
```

---

### Task 6: Rewrite analyze_sessions.py as thin CLI entry point

**Files:**
- Modify: `plugins/claude-code-analytics/scripts/analyze_sessions.py`
- Test: `plugins/claude-code-analytics/scripts/tests/test_main.py`

**Step 1: Write the failing test**

```python
# tests/test_main.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_analyze_sessions_imports():
    """Verify the thin entry point can import all modules."""
    import analyze_sessions
    assert hasattr(analyze_sessions, "main")
```

**Step 2: Run test to verify it fails**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/test_main.py -v`
Expected: PASS (current file still has main) — this is a smoke test for after the rewrite.

**Step 3: Rewrite analyze_sessions.py**

Replace the entire file with the thin orchestrator:

```python
#!/usr/bin/env python3
"""
Deliberate Thinking Analyzer for Claude Code.
Analyzes ~/.claude session data and generates an interactive HTML report.
Pure Python 3.7+ — no pip dependencies.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from parsers import collect_sessions, load_history, load_stats_cache
from metrics import (
    compute_prompt_metrics,
    compute_tool_metrics,
    compute_efficiency_metrics,
    compute_temporal_metrics,
    compute_model_metrics,
    compute_thematic_analysis,
    compute_history_metrics,
)
from suggestions import generate_suggestions
from report import generate_report


def main():
    parser = argparse.ArgumentParser(description="Analyze Claude Code interaction patterns")
    parser.add_argument("--days", type=int, default=30, help="Analyze last N days (default: 30)")
    parser.add_argument("--project", type=str, default=None, help="Filter to projects matching substring")
    parser.add_argument("--session", type=str, default=None, help="Analyze specific session (ID prefix)")
    parser.add_argument("--output", type=str, default="/tmp/deliberate-thinking-report.html", help="Output file path")
    parser.add_argument("--all", action="store_true", help="Analyze all data (no date filter)")
    args = parser.parse_args()

    print(f"Collecting sessions (last {args.days} days)..." if not args.all else "Collecting all sessions...")
    sessions = collect_sessions(args.days, args.project, args.session, args.all)
    print(f"Found {len(sessions)} sessions")

    if not sessions:
        print("No sessions found matching filters. Try --all or --days 90", file=sys.stderr)
        sys.exit(1)

    print("Computing metrics...")
    prompt_metrics = compute_prompt_metrics(sessions)
    tool_metrics = compute_tool_metrics(sessions)
    efficiency = compute_efficiency_metrics(sessions)
    temporal = compute_temporal_metrics(sessions)
    themes = compute_thematic_analysis(sessions)
    model_metrics = compute_model_metrics(sessions)

    history = load_history(args.days, args.project, args.all)
    history_metrics = compute_history_metrics(history)

    stats_cache = load_stats_cache()

    suggestions = generate_suggestions(prompt_metrics, tool_metrics, efficiency, themes, model_metrics)

    print("\n--- Key Suggestions ---")
    for sug in suggestions:
        icon = {"positive": "+", "consider": "!", "observation": "~", "info": "i"}.get(sug["type"], "-")
        print(f"  [{icon}] {sug['title']}: {sug['text']}")
    print()

    data = {
        "generated_at": datetime.now().isoformat(),
        "filter": {
            "days": args.days if not args.all else "all",
            "project": args.project,
            "session": args.session,
        },
        "prompt_metrics": prompt_metrics,
        "tool_metrics": tool_metrics,
        "efficiency": efficiency,
        "temporal": temporal,
        "themes": themes,
        "model_metrics": model_metrics,
        "history": history_metrics,
        "stats_cache": {
            "model_usage": stats_cache.get("modelUsage", {}),
            "total_sessions": stats_cache.get("totalSessions", 0),
            "total_messages": stats_cache.get("totalMessages", 0),
        },
        "suggestions": suggestions,
    }

    template_path = Path(__file__).parent.parent / "templates" / "report_template.html"
    generate_report(data, args.output, template_path)


if __name__ == "__main__":
    main()
```

**Step 4: Run ALL tests to verify everything works**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/ -v`
Expected: all PASS

**Step 5: Run the actual script end-to-end**

Run: `cd plugins/claude-code-analytics && python3 scripts/analyze_sessions.py --days 7`
Expected: generates report without errors

**Step 6: Commit**

```bash
git add plugins/claude-code-analytics/scripts/analyze_sessions.py plugins/claude-code-analytics/scripts/tests/test_main.py
git commit -m "refactor: rewrite analyze_sessions.py as thin CLI entry point"
```

---

### Task 7: Final verification and cleanup

**Step 1: Run full test suite**

Run: `cd plugins/claude-code-analytics && python3 -m pytest scripts/tests/ -v`
Expected: all PASS

**Step 2: Run end-to-end**

Run: `python3 plugins/claude-code-analytics/scripts/analyze_sessions.py --days 7`
Expected: report generates, opens correctly

**Step 3: Verify line counts**

Run: `wc -l plugins/claude-code-analytics/scripts/*.py`
Expected: each file well under 500 lines, total ~same as original

**Step 4: Commit all together if any stragglers**

```bash
git add -A plugins/claude-code-analytics/scripts/
git commit -m "refactor: complete modularization of analyze_sessions.py"
```
