"""Session, history, and stats file parsing for Claude Code analytics."""

import json
import sys
from datetime import datetime, timedelta, timezone

from constants import (
    HISTORY_FILE,
    PROJECTS_DIR,
    STATS_FILE,
    get_context_window,
    parse_timestamp,
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

        # Check subagents
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
        "all_timestamps": [],  # FIX #4: track ALL record timestamps
        "slug": "",
        "cwd": "",
        "version": "",
        # NEW: model and token tracking
        "model_usage": [],  # list of {model, input_tokens, output_tokens, cache_read, cache_creation, total_context}
        "models_used": set(),
    }

    seen_uuids = {}  # uuid -> parsed data (for dedup)
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

                # FIX #4: collect ALL timestamps for accurate duration
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
                        session["human_messages"].append(
                            {
                                "text": content.strip(),
                                "timestamp": ts,
                                "word_count": len(content.split()),
                                "char_count": len(content),
                            }
                        )

                elif rtype == "assistant":
                    uuid = record.get("uuid", "")
                    msg = record.get("message", {})
                    content = msg.get("content", [])
                    model = msg.get("model", "")
                    usage = msg.get("usage", {})

                    # FIX #1: Deduplicate by uuid — only process the LAST
                    # occurrence of each uuid (streaming creates partials).
                    # We collect all records, then process deduplicated set after.
                    if uuid:
                        seen_uuids[uuid] = {
                            "content": content,
                            "model": model,
                            "usage": usage,
                            "timestamp": ts,
                        }
                    elif not uuid:
                        # Records without uuid — process inline (rare)
                        _process_assistant_content(session, content, model, usage, ts)

    except (IOError, OSError) as e:
        print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)
        return None

    # FIX #1: Now process deduplicated assistant records
    for uid, data in seen_uuids.items():
        _process_assistant_content(session, data["content"], data["model"], data["usage"], data["timestamp"])

    # Apply date filter
    if cutoff and first_ts and first_ts < cutoff:
        return None

    # FIX #4: Duration from ALL timestamps, not just human messages
    session["start_time"] = first_ts
    if session["all_timestamps"]:
        session["end_time"] = max(session["all_timestamps"])
        session["duration_minutes"] = (session["end_time"] - min(session["all_timestamps"])).total_seconds() / 60
    else:
        session["end_time"] = first_ts
        session["duration_minutes"] = 0

    # Convert set to list for JSON serialization later
    session["models_used"] = list(session["models_used"])

    return session


def _process_assistant_content(session, content, model, usage, ts):
    """Process a deduplicated assistant message's content, model, and usage."""
    # Track model
    if model and model != "<synthetic>":
        session["models_used"].add(model)

    # Track token usage (NEW: context window tracking)
    if usage:
        input_tokens = usage.get("input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_creation = usage.get("cache_creation_input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_context = input_tokens + cache_read + cache_creation

        if total_context > 0 or output_tokens > 0:
            session["model_usage"].append(
                {
                    "model": model or "unknown",
                    "input_tokens": input_tokens,
                    "cache_read": cache_read,
                    "cache_creation": cache_creation,
                    "output_tokens": output_tokens,
                    "total_context": total_context,
                    "context_window": get_context_window(model),
                    "utilization_pct": round(total_context / get_context_window(model) * 100, 1)
                    if total_context > 0
                    else 0,
                    "timestamp": ts.isoformat() if ts else None,
                }
            )

    # Extract tool calls
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    session["assistant_tool_calls"].append(
                        {
                            "name": tool_name,
                            "timestamp": ts,
                            "input_summary": _summarize_tool_input(tool_name, tool_input),
                        }
                    )
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
