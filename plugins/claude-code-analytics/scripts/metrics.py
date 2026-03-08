"""Metrics computation functions for Claude Code analytics."""

import re
from collections import Counter, defaultdict
from datetime import timedelta

from constants import (
    LOCAL_UTC_OFFSET_HOURS, STOPWORDS,
    get_context_window, to_local_hour, to_local_weekday,
)


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
