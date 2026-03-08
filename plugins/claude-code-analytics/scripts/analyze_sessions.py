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

from metrics import (
    compute_efficiency_metrics,
    compute_history_metrics,
    compute_model_metrics,
    compute_prompt_metrics,
    compute_temporal_metrics,
    compute_thematic_analysis,
    compute_tool_metrics,
)
from parsers import collect_sessions, load_history, load_stats_cache
from report import generate_report
from suggestions import generate_suggestions


def main():
    parser = argparse.ArgumentParser(description="Analyze Claude Code interaction patterns")
    parser.add_argument("--days", type=int, default=30, help="Analyze last N days (default: 30)")
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Filter to projects matching substring",
    )
    parser.add_argument("--session", type=str, default=None, help="Analyze specific session (ID prefix)")
    parser.add_argument(
        "--output",
        type=str,
        default="/tmp/deliberate-thinking-report.html",
        help="Output file path",
    )
    parser.add_argument("--all", action="store_true", help="Analyze all data (no date filter)")
    args = parser.parse_args()

    print(f"Collecting sessions (last {args.days} days)..." if not args.all else "Collecting all sessions...")
    sessions = collect_sessions(args.days, args.project, args.session, args.all)
    print(f"Found {len(sessions)} sessions")

    if not sessions:
        print(
            "No sessions found matching filters. Try --all or --days 90",
            file=sys.stderr,
        )
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
