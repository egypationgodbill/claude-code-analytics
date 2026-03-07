#!/usr/bin/env python3
"""
Deliberate Thinking Analyzer for Claude Code.
Analyzes ~/.claude session data and generates an interactive HTML report.
Pure Python 3.7+ — no pip dependencies.
"""

import argparse
import json
import os
import re
import sys
import math
from collections import Counter, defaultdict
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


# --- Data Collection ---

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
        _process_assistant_content(
            session, data["content"], data["model"], data["usage"], data["timestamp"]
        )

    # Apply date filter
    if cutoff and first_ts and first_ts < cutoff:
        return None

    # FIX #4: Duration from ALL timestamps, not just human messages
    session["start_time"] = first_ts
    if session["all_timestamps"]:
        session["end_time"] = max(session["all_timestamps"])
        session["duration_minutes"] = (
            (session["end_time"] - min(session["all_timestamps"])).total_seconds() / 60
        )
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

    # Extract tool calls
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


# --- Metrics Computation ---

def compute_prompt_metrics(sessions):
    """Compute prompt quality metrics across all sessions."""
    all_prompts = []
    for s in sessions.values():
        all_prompts.extend(s["human_messages"])

    if not all_prompts:
        return {"empty": True}

    word_counts = [p["word_count"] for p in all_prompts]
    char_counts = [p["char_count"] for p in all_prompts]

    sorted_wc = sorted(word_counts)
    median_wc = sorted_wc[len(sorted_wc) // 2]

    question_count = sum(1 for p in all_prompts if p["text"].rstrip().endswith("?"))

    # FIX #6: Split context rate into sub-metrics
    long_prompts = sum(1 for p in all_prompts if p["word_count"] > 50)
    has_file_refs = sum(
        1 for p in all_prompts
        if re.search(r'[/\\]\w+\.\w+', p["text"])
    )
    has_code_blocks = sum(1 for p in all_prompts if "```" in p["text"])
    # Union for overall context rate
    context_count = sum(
        1 for p in all_prompts
        if p["word_count"] > 50
        or re.search(r'[/\\]\w+\.\w+', p["text"])
        or "```" in p["text"]
    )

    # Specificity: file names, function names, code references
    specific_count = sum(
        1 for p in all_prompts
        if re.search(r'\w+\.(ts|tsx|js|jsx|py|rs|go|java|rb|css|html|md|json|yaml|yml|toml)', p["text"])
        or re.search(r'`[a-zA-Z_]\w+`', p["text"])
        or re.search(r'(function|class|method|variable|import|export)\s+\w+', p["text"], re.I)
    )

    # Word count distribution buckets
    buckets = {"1-5": 0, "6-15": 0, "16-30": 0, "31-50": 0, "51-100": 0, "100+": 0}
    for wc in word_counts:
        if wc <= 5:
            buckets["1-5"] += 1
        elif wc <= 15:
            buckets["6-15"] += 1
        elif wc <= 30:
            buckets["16-30"] += 1
        elif wc <= 50:
            buckets["31-50"] += 1
        elif wc <= 100:
            buckets["51-100"] += 1
        else:
            buckets["100+"] += 1

    # Prompt length over time (for scatter plot)
    prompt_timeline = []
    for p in all_prompts:
        if p["timestamp"]:
            prompt_timeline.append({
                "timestamp": p["timestamp"].isoformat(),
                "word_count": p["word_count"],
                "excerpt": p["text"][:100],
            })

    n = len(all_prompts)
    return {
        "total_prompts": n,
        "avg_words": round(sum(word_counts) / n, 1),
        "median_words": median_wc,
        "avg_chars": round(sum(char_counts) / n, 1),
        "max_words": max(word_counts),
        "min_words": min(word_counts),
        "question_ratio": round(question_count / n * 100, 1),
        # FIX #6: broken-out context sub-metrics
        "context_rate": round(context_count / n * 100, 1),
        "long_prompt_rate": round(long_prompts / n * 100, 1),
        "file_ref_rate": round(has_file_refs / n * 100, 1),
        "code_block_rate": round(has_code_blocks / n * 100, 1),
        "specificity_rate": round(specific_count / n * 100, 1),
        "distribution": buckets,
        "timeline": prompt_timeline,
    }


def compute_tool_metrics(sessions):
    """Compute tool usage metrics."""
    tool_counts = Counter()
    tool_by_session = defaultdict(int)
    subagent_types = Counter()
    plan_mode_count = 0
    skill_invocations = []

    for s in sessions.values():
        session_tools = set()
        for tc in s["assistant_tool_calls"]:
            name = tc["name"]
            tool_counts[name] += 1
            session_tools.add(name)

            if name == "EnterPlanMode":
                plan_mode_count += 1
            elif name == "Skill":
                skill_invocations.append(tc["input_summary"])

        for t in session_tools:
            tool_by_session[t] += 1

        for at in s["subagent_types"]:
            subagent_types[at] += 1

    total_human = sum(len(s["human_messages"]) for s in sessions.values())
    total_tools = sum(tool_counts.values())

    return {
        "tool_frequency": dict(tool_counts.most_common(20)),
        "tool_by_session": dict(sorted(tool_by_session.items(), key=lambda x: -x[1])[:20]),
        "total_tool_calls": total_tools,
        "tools_per_message": round(total_tools / max(total_human, 1), 2),
        "subagent_types": dict(subagent_types),
        "plan_mode_count": plan_mode_count,
        "skill_invocations": skill_invocations,
        "unique_tools_used": len(tool_counts),
    }


def compute_efficiency_metrics(sessions):
    """Compute efficiency metrics per session."""
    session_data = []

    for sid, s in sessions.items():
        n_human = len(s["human_messages"])
        n_tools = len(s["assistant_tool_calls"])
        avg_prompt_words = (
            sum(m["word_count"] for m in s["human_messages"]) / n_human
            if n_human else 0
        )

        session_data.append({
            "id": sid,
            "project": s["project"],
            "slug": s["slug"],
            "human_messages": n_human,
            "tool_calls": n_tools,
            "avg_prompt_words": round(avg_prompt_words, 1),
            "duration_minutes": round(s["duration_minutes"], 1),
            "tools_per_message": round(n_tools / max(n_human, 1), 2),
            "start_time": s["start_time"].isoformat() if s["start_time"] else None,
            "models_used": s["models_used"],
        })

    session_data.sort(key=lambda x: x["start_time"] or "")

    return {
        "sessions": session_data,
        "total_sessions": len(session_data),
        "avg_messages_per_session": round(
            sum(d["human_messages"] for d in session_data) / max(len(session_data), 1), 1
        ),
        "avg_duration": round(
            sum(d["duration_minutes"] for d in session_data) / max(len(session_data), 1), 1
        ),
    }


def compute_temporal_metrics(sessions):
    """Compute temporal patterns. FIX #7: uses local time."""
    hour_counts = Counter()
    day_counts = Counter()
    daily_prompt_lengths = defaultdict(list)

    for s in sessions.values():
        for msg in s["human_messages"]:
            if msg["timestamp"]:
                local_hour = to_local_hour(msg["timestamp"])
                local_day = to_local_weekday(msg["timestamp"])
                hour_counts[local_hour] += 1
                day_counts[local_day] += 1
                # Use local date for daily grouping
                local_dt = msg["timestamp"] + timedelta(hours=LOCAL_UTC_OFFSET_HOURS)
                date_key = local_dt.strftime("%Y-%m-%d")
                daily_prompt_lengths[date_key].append(msg["word_count"])

    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    heatmap = {}
    for s in sessions.values():
        for msg in s["human_messages"]:
            if msg["timestamp"]:
                h = to_local_hour(msg["timestamp"])
                d = to_local_weekday(msg["timestamp"])
                key = f"{d}_{h}"
                heatmap[key] = heatmap.get(key, 0) + 1

    daily_avg = []
    for date_key in sorted(daily_prompt_lengths.keys()):
        lengths = daily_prompt_lengths[date_key]
        daily_avg.append({
            "date": date_key,
            "avg_words": round(sum(lengths) / len(lengths), 1),
            "count": len(lengths),
        })

    return {
        "hour_counts": dict(hour_counts),
        "day_counts": {d: day_counts.get(d, 0) for d in days_order},
        "heatmap": heatmap,
        "daily_avg_prompt_length": daily_avg,
        "timezone_offset": LOCAL_UTC_OFFSET_HOURS,
    }


def compute_model_metrics(sessions):
    """NEW: Compute model usage and context window metrics."""
    model_counts = Counter()  # messages per model
    model_tokens = defaultdict(lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0})
    context_utilizations = []  # list of {pct, model, timestamp, session_id}
    session_models = []  # per-session model summary
    peak_utilizations = []  # highest utilization per session

    for sid, s in sessions.items():
        session_model_counts = Counter()
        session_peak = 0
        session_total_output = 0

        for mu in s["model_usage"]:
            m = mu["model"]
            if m == "<synthetic>":
                continue
            model_counts[m] += 1
            session_model_counts[m] += 1
            model_tokens[m]["input"] += mu["input_tokens"]
            model_tokens[m]["output"] += mu["output_tokens"]
            model_tokens[m]["cache_read"] += mu["cache_read"]
            model_tokens[m]["cache_creation"] += mu["cache_creation"]
            session_total_output += mu["output_tokens"]

            if mu["utilization_pct"] > 0:
                context_utilizations.append({
                    "pct": mu["utilization_pct"],
                    "model": m,
                    "timestamp": mu["timestamp"],
                    "session_id": sid,
                })
                session_peak = max(session_peak, mu["utilization_pct"])

        primary_model = session_model_counts.most_common(1)[0][0] if session_model_counts else "unknown"
        session_models.append({
            "id": sid,
            "slug": s["slug"],
            "primary_model": _short_model_name(primary_model),
            "models": {_short_model_name(k): v for k, v in session_model_counts.items()},
            "peak_context_pct": round(session_peak, 1),
            "total_output_tokens": session_total_output,
            "human_messages": len(s["human_messages"]),
            "start_time": s["start_time"].isoformat() if s["start_time"] else None,
        })

        if session_peak > 0:
            peak_utilizations.append(session_peak)

    # Context utilization distribution
    util_buckets = {"0-25%": 0, "25-50%": 0, "50-75%": 0, "75-90%": 0, "90%+": 0}
    for cu in context_utilizations:
        p = cu["pct"]
        if p < 25:
            util_buckets["0-25%"] += 1
        elif p < 50:
            util_buckets["25-50%"] += 1
        elif p < 75:
            util_buckets["50-75%"] += 1
        elif p < 90:
            util_buckets["75-90%"] += 1
        else:
            util_buckets["90%+"] += 1

    # Context utilization over time
    util_timeline = sorted(context_utilizations, key=lambda x: x["timestamp"] or "")

    # Model token summary
    model_summary = {}
    for m, tokens in model_tokens.items():
        total = tokens["input"] + tokens["cache_read"] + tokens["cache_creation"] + tokens["output"]
        model_summary[_short_model_name(m)] = {
            "messages": model_counts[m],
            "input_tokens": tokens["input"],
            "output_tokens": tokens["output"],
            "cache_read": tokens["cache_read"],
            "cache_creation": tokens["cache_creation"],
            "total_tokens": total,
        }

    return {
        "model_summary": model_summary,
        "model_message_counts": {_short_model_name(k): v for k, v in model_counts.most_common()},
        "context_utilization_distribution": util_buckets,
        "context_utilization_timeline": [
            {"timestamp": u["timestamp"], "pct": u["pct"], "model": _short_model_name(u["model"])}
            for u in util_timeline[-200:]  # last 200 data points
        ],
        "session_models": session_models,
        "avg_peak_utilization": round(sum(peak_utilizations) / max(len(peak_utilizations), 1), 1),
        "max_utilization": round(max(peak_utilizations) if peak_utilizations else 0, 1),
        "sessions_over_75pct": sum(1 for p in peak_utilizations if p > 75),
    }


def _short_model_name(model):
    """Shorten model ID for display."""
    if not model:
        return "unknown"
    # claude-opus-4-6 -> Opus 4.6
    # claude-sonnet-4-5-20250929 -> Sonnet 4.5
    # claude-sonnet-4-6 -> Sonnet 4.6
    m = model.replace("claude-", "")
    parts = m.split("-")
    if len(parts) >= 2:
        family = parts[0].capitalize()
        # Join version numbers with dots, drop date suffixes
        version_parts = []
        for p in parts[1:]:
            if p.isdigit() and len(p) <= 2:
                version_parts.append(p)
            elif len(p) == 8 and p.isdigit():
                break  # date suffix
            else:
                break
        version = ".".join(version_parts) if version_parts else ""
        return f"{family} {version}".strip()
    return model


def compute_thematic_analysis(sessions):
    """Classify sessions by theme and extract n-grams.
    FIX #3: Rebalanced keywords — removed overly generic words.
    FIX #2: N-grams computed per-session then merged (no cross-session spans).
    """
    # FIX #3: More specific keywords, weighted by specificity
    theme_keywords = {
        "debugging": {
            "high": ["bug", "error", "crash", "broken", "debug", "traceback", "exception", "stack trace"],
            "low": ["fix", "issue", "fail", "failing", "wrong"],
        },
        "feature_dev": {
            "high": ["implement", "new feature", "feature", "component", "build out", "scaffold"],
            "low": ["build", "create", "add"],  # FIX #3: these are low-weight now
        },
        "refactoring": {
            "high": ["refactor", "clean up", "simplify", "reorganize", "restructure"],
            "low": ["rename", "move", "extract"],
        },
        "exploration": {
            "high": ["explore", "how does", "what is", "explain", "investigate", "understand"],
            "low": ["look at", "show me", "where is"],
        },
        "configuration": {
            "high": ["config", "setup", "install", "configure", "environment", "dependency", "dependencies"],
            "low": ["setting", "settings"],
        },
        "review": {
            "high": ["review", "audit", "code review", "pull request"],
            "low": ["verify", "approve"],  # FIX #3: removed "check" — too generic
        },
        "documentation": {
            "high": ["document", "readme", "docstring", "docs", "write up", "documentation"],
            "low": ["comment"],
        },
        "testing": {
            "high": ["test", "spec", "assert", "expect", "mock", "jest", "coverage", "unit test"],
            "low": [],
        },
    }

    # FIX #3: Reduced tool-based boost weight
    tool_themes = {
        "Edit": ("feature_dev", 0.1),
        "Write": ("feature_dev", 0.1),
        "Grep": ("exploration", 0.15),
        "Glob": ("exploration", 0.1),
    }

    session_categories = []
    all_bigrams = Counter()
    all_trigrams = Counter()
    all_unigrams = Counter()

    for sid, s in sessions.items():
        prompt_text = " ".join(m["text"].lower() for m in s["human_messages"])
        scores = defaultdict(float)

        # FIX #3: Weighted keyword scoring
        for theme, keyword_groups in theme_keywords.items():
            for kw in keyword_groups.get("high", []):
                scores[theme] += prompt_text.count(kw) * 2.0
            for kw in keyword_groups.get("low", []):
                scores[theme] += prompt_text.count(kw) * 0.5

        # FIX #3: Reduced tool-based scoring
        tool_names = [tc["name"] for tc in s["assistant_tool_calls"]]
        tool_counter = Counter(tool_names)
        for tool, (theme, weight) in tool_themes.items():
            scores[theme] += tool_counter.get(tool, 0) * weight

        best_theme = max(scores, key=scores.get) if scores else "uncategorized"
        if scores.get(best_theme, 0) < 1.0:  # FIX #3: minimum threshold
            best_theme = "uncategorized"

        session_categories.append({
            "id": sid,
            "project": s["project"],
            "slug": s["slug"],
            "category": best_theme,
            "human_messages": len(s["human_messages"]),
            "avg_prompt_words": round(
                sum(m["word_count"] for m in s["human_messages"]) / max(len(s["human_messages"]), 1), 1
            ),
            "tool_calls": len(s["assistant_tool_calls"]),
            "start_time": s["start_time"].isoformat() if s["start_time"] else None,
        })

        # FIX #2: N-grams per session — no cross-session contamination
        words = re.findall(r'[a-z]+', prompt_text)
        filtered = [w for w in words if w not in STOPWORDS and len(w) > 2]
        all_unigrams.update(filtered)
        for i in range(len(filtered) - 1):
            all_bigrams[f"{filtered[i]} {filtered[i+1]}"] += 1
        for i in range(len(filtered) - 2):
            all_trigrams[f"{filtered[i]} {filtered[i+1]} {filtered[i+2]}"] += 1

    cat_counts = Counter(sc["category"] for sc in session_categories)

    cat_efficiency = {}
    for cat in cat_counts:
        cat_sessions = [sc for sc in session_categories if sc["category"] == cat]
        if cat_sessions:
            avg_words = sum(sc["avg_prompt_words"] for sc in cat_sessions) / len(cat_sessions)
            avg_tools = sum(sc["tool_calls"] for sc in cat_sessions) / len(cat_sessions)
            avg_msgs = sum(sc["human_messages"] for sc in cat_sessions) / len(cat_sessions)
            cat_efficiency[cat] = {
                "avg_prompt_words": round(avg_words, 1),
                "avg_tool_calls": round(avg_tools, 1),
                "avg_messages": round(avg_msgs, 1),
                "session_count": len(cat_sessions),
            }

    return {
        "session_categories": session_categories,
        "category_counts": dict(cat_counts.most_common()),
        "category_efficiency": cat_efficiency,
        "top_bigrams": dict(all_bigrams.most_common(20)),
        "top_trigrams": dict(all_trigrams.most_common(15)),
        "top_words": dict(all_unigrams.most_common(30)),
    }


def compute_history_metrics(history_entries):
    """Analyze history.jsonl for slash commands."""
    slash_commands = Counter()
    for entry in history_entries:
        display = entry.get("display", "").strip()
        if display.startswith("/"):
            cmd = display.split()[0]
            slash_commands[cmd] += 1

    return {
        "total_history_entries": len(history_entries),
        "slash_commands": dict(slash_commands.most_common(15)),
    }


# --- Suggestion Engine ---

def generate_suggestions(prompt_metrics, tool_metrics, efficiency, themes, model_metrics):
    """Generate actionable suggestions based on computed metrics."""
    suggestions = []

    if prompt_metrics.get("empty"):
        return [{"type": "info", "title": "No Data", "text": "No session data found for the selected filters."}]

    avg_words = prompt_metrics.get("avg_words", 0)
    avg_msgs = efficiency.get("avg_messages_per_session", 0)

    # Short prompts + many messages = consider more context
    if avg_words < 15 and avg_msgs > 10:
        suggestions.append({
            "type": "consider",
            "title": "Add More Upfront Context",
            "text": f"Your average prompt is {avg_words} words with {avg_msgs} messages per session. "
                    "Adding more context upfront (file paths, expected behavior, constraints) could reduce back-and-forth.",
        })

    # Short prompts + few messages = good CLAUDE.md
    if avg_words < 15 and avg_msgs <= 5:
        suggestions.append({
            "type": "positive",
            "title": "Efficient Short Prompts",
            "text": f"Your average prompt is {avg_words} words but sessions average only {avg_msgs} messages. "
                    "Your CLAUDE.md and project context may be providing effective implicit context.",
        })

    # Low specificity
    specificity = prompt_metrics.get("specificity_rate", 0)
    if specificity < 20:
        suggestions.append({
            "type": "consider",
            "title": "Reference Specific Files",
            "text": f"Only {specificity}% of prompts reference specific files or code. "
                    "Including file paths and function names helps Claude navigate your codebase faster.",
        })

    # Plan mode usage
    plan_count = tool_metrics.get("plan_mode_count", 0)
    long_sessions = sum(1 for s in efficiency.get("sessions", []) if s["human_messages"] > 15)
    if long_sessions > 2 and plan_count == 0:
        suggestions.append({
            "type": "consider",
            "title": "Try Plan Mode for Complex Tasks",
            "text": f"You have {long_sessions} sessions with >15 messages but haven't used plan mode. "
                    "Plan mode helps structure complex tasks before diving into implementation.",
        })

    # Subagent usage
    subagent_count = sum(tool_metrics.get("subagent_types", {}).values())
    if subagent_count > 5:
        suggestions.append({
            "type": "positive",
            "title": "Good Subagent Usage",
            "text": f"You've used {subagent_count} subagent delegations. "
                    "This helps parallelize work and keeps the main context focused.",
        })

    # High question ratio
    q_ratio = prompt_metrics.get("question_ratio", 0)
    if q_ratio > 60:
        suggestions.append({
            "type": "observation",
            "title": "Question-Heavy Interaction",
            "text": f"{q_ratio}% of your prompts are questions. Consider using more directive prompts "
                    "('do X') alongside questions for clearer intent.",
        })

    # FIX #6: More nuanced context provision feedback
    file_ref_rate = prompt_metrics.get("file_ref_rate", 0)
    code_block_rate = prompt_metrics.get("code_block_rate", 0)
    if file_ref_rate > 30 or code_block_rate > 20:
        suggestions.append({
            "type": "positive",
            "title": "Strong Context Provider",
            "text": f"{file_ref_rate}% of prompts include file paths, {code_block_rate}% include code blocks. "
                    "This helps Claude understand your codebase quickly.",
        })

    # Category-specific insights
    cat_eff = themes.get("category_efficiency", {})
    for cat, data in cat_eff.items():
        if data["session_count"] >= 2:
            if cat == "debugging" and data["avg_prompt_words"] > 40:
                suggestions.append({
                    "type": "positive",
                    "title": "Detailed Debugging Prompts",
                    "text": f"Your debugging prompts average {data['avg_prompt_words']} words — detailed bug reports "
                            "help Claude diagnose issues faster.",
                })
            elif cat == "debugging" and data["avg_prompt_words"] < 15:
                suggestions.append({
                    "type": "consider",
                    "title": "More Detail in Bug Reports",
                    "text": f"Debugging prompts average only {data['avg_prompt_words']} words. "
                            "Including error messages, expected vs actual behavior, and reproduction steps helps.",
                })

    # Prompt length trend
    timeline = prompt_metrics.get("timeline", [])
    if len(timeline) > 20:
        first_half = [t["word_count"] for t in timeline[:len(timeline)//2]]
        second_half = [t["word_count"] for t in timeline[len(timeline)//2:]]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        if avg_second > avg_first * 1.3:
            suggestions.append({
                "type": "observation",
                "title": "Prompts Getting Longer",
                "text": f"Your average prompt length increased from {avg_first:.0f} to {avg_second:.0f} words "
                        "over the analysis period. You may be providing more context over time.",
            })
        elif avg_second < avg_first * 0.7:
            suggestions.append({
                "type": "observation",
                "title": "Prompts Getting Shorter",
                "text": f"Your average prompt length decreased from {avg_first:.0f} to {avg_second:.0f} words. "
                        "This could indicate growing familiarity or better CLAUDE.md configuration.",
            })

    # FIX #5: Context-aware tool ratio suggestion
    # Only flag high tool ratio for multi-message sessions (not 1-prompt executions)
    for s in efficiency.get("sessions", []):
        if s["tools_per_message"] > 8 and s["human_messages"] > 3:
            suggestions.append({
                "type": "consider",
                "title": "High Tool-to-Message Ratio",
                "text": f"Session '{s['slug'] or s['id'][:8]}' had {s['tools_per_message']} tool calls per message "
                        f"across {s['human_messages']} messages. Specifying file paths in prompts can reduce exploration.",
            })
            break

    # NEW: Context window suggestions
    if model_metrics:
        sessions_over_75 = model_metrics.get("sessions_over_75pct", 0)
        max_util = model_metrics.get("max_utilization", 0)
        if sessions_over_75 > 0:
            suggestions.append({
                "type": "observation",
                "title": "High Context Window Usage",
                "text": f"{sessions_over_75} session(s) used >75% of the context window (peak: {max_util}%). "
                        "Long sessions may benefit from plan mode or splitting into sub-tasks.",
            })

        avg_peak = model_metrics.get("avg_peak_utilization", 0)
        if avg_peak < 30:
            suggestions.append({
                "type": "positive",
                "title": "Context Window Well-Managed",
                "text": f"Average peak context utilization is {avg_peak}%. "
                        "Your sessions stay well within context limits.",
            })

    if not suggestions:
        suggestions.append({
            "type": "positive",
            "title": "Looking Good",
            "text": "No strong signals detected. Your interaction patterns seem balanced.",
        })

    return suggestions


# --- Report Generation ---

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


# --- Main ---

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

    # Print key suggestions to terminal
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
