"""
Suggestion engine — generates actionable suggestions from computed metrics.
"""


def generate_suggestions(prompt_metrics, tool_metrics, efficiency, themes, model_metrics):
    """Generate actionable suggestions based on computed metrics."""
    suggestions = []

    if prompt_metrics.get("empty"):
        return [
            {
                "type": "info",
                "title": "No Data",
                "text": "No session data found for the selected filters.",
            }
        ]

    avg_words = prompt_metrics.get("avg_words", 0)
    avg_msgs = efficiency.get("avg_messages_per_session", 0)

    # Short prompts + many messages = consider more context
    if avg_words < 15 and avg_msgs > 10:
        suggestions.append(
            {
                "type": "consider",
                "title": "Add More Upfront Context",
                "text": f"Your average prompt is {avg_words} words with {avg_msgs} messages per session. "
                "Adding more context upfront (file paths, expected behavior, constraints) could reduce back-and-forth.",
            }
        )

    # Short prompts + few messages = good CLAUDE.md
    if avg_words < 15 and avg_msgs <= 5:
        suggestions.append(
            {
                "type": "positive",
                "title": "Efficient Short Prompts",
                "text": f"Your average prompt is {avg_words} words but sessions average only {avg_msgs} messages. "
                "Your CLAUDE.md and project context may be providing effective implicit context.",
            }
        )

    # Low specificity
    specificity = prompt_metrics.get("specificity_rate", 0)
    if specificity < 20:
        suggestions.append(
            {
                "type": "consider",
                "title": "Reference Specific Files",
                "text": f"Only {specificity}% of prompts reference specific files or code. "
                "Including file paths and function names helps Claude navigate your codebase faster.",
            }
        )

    # Plan mode usage
    plan_count = tool_metrics.get("plan_mode_count", 0)
    long_sessions = sum(1 for s in efficiency.get("sessions", []) if s["human_messages"] > 15)
    if long_sessions > 2 and plan_count == 0:
        suggestions.append(
            {
                "type": "consider",
                "title": "Try Plan Mode for Complex Tasks",
                "text": f"You have {long_sessions} sessions with >15 messages but haven't used plan mode. "
                "Plan mode helps structure complex tasks before diving into implementation.",
            }
        )

    # Subagent usage
    subagent_count = sum(tool_metrics.get("subagent_types", {}).values())
    if subagent_count > 5:
        suggestions.append(
            {
                "type": "positive",
                "title": "Good Subagent Usage",
                "text": f"You've used {subagent_count} subagent delegations. "
                "This helps parallelize work and keeps the main context focused.",
            }
        )

    # High question ratio
    q_ratio = prompt_metrics.get("question_ratio", 0)
    if q_ratio > 60:
        suggestions.append(
            {
                "type": "observation",
                "title": "Question-Heavy Interaction",
                "text": f"{q_ratio}% of your prompts are questions. Consider using more directive prompts "
                "('do X') alongside questions for clearer intent.",
            }
        )

    # FIX #6: More nuanced context provision feedback
    file_ref_rate = prompt_metrics.get("file_ref_rate", 0)
    code_block_rate = prompt_metrics.get("code_block_rate", 0)
    if file_ref_rate > 30 or code_block_rate > 20:
        suggestions.append(
            {
                "type": "positive",
                "title": "Strong Context Provider",
                "text": f"{file_ref_rate}% of prompts include file paths, {code_block_rate}% include code blocks. "
                "This helps Claude understand your codebase quickly.",
            }
        )

    # Category-specific insights
    cat_eff = themes.get("category_efficiency", {})
    for cat, data in cat_eff.items():
        if data["session_count"] >= 2:
            if cat == "debugging" and data["avg_prompt_words"] > 40:
                suggestions.append(
                    {
                        "type": "positive",
                        "title": "Detailed Debugging Prompts",
                        "text": f"Your debugging prompts average {data['avg_prompt_words']} words "
                        "— detailed bug reports help Claude diagnose issues faster.",
                    }
                )
            elif cat == "debugging" and data["avg_prompt_words"] < 15:
                suggestions.append(
                    {
                        "type": "consider",
                        "title": "More Detail in Bug Reports",
                        "text": f"Debugging prompts average only {data['avg_prompt_words']} words. "
                        "Including error messages, expected vs actual behavior, and reproduction steps helps.",
                    }
                )

    # Prompt length trend
    timeline = prompt_metrics.get("timeline", [])
    if len(timeline) > 20:
        first_half = [t["word_count"] for t in timeline[: len(timeline) // 2]]
        second_half = [t["word_count"] for t in timeline[len(timeline) // 2 :]]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        if avg_second > avg_first * 1.3:
            suggestions.append(
                {
                    "type": "observation",
                    "title": "Prompts Getting Longer",
                    "text": f"Your average prompt length increased from {avg_first:.0f} to {avg_second:.0f} words "
                    "over the analysis period. You may be providing more context over time.",
                }
            )
        elif avg_second < avg_first * 0.7:
            suggestions.append(
                {
                    "type": "observation",
                    "title": "Prompts Getting Shorter",
                    "text": f"Your average prompt length decreased from {avg_first:.0f} to {avg_second:.0f} words. "
                    "This could indicate growing familiarity or better CLAUDE.md configuration.",
                }
            )

    # FIX #5: Context-aware tool ratio suggestion
    # Only flag high tool ratio for multi-message sessions (not 1-prompt executions)
    for s in efficiency.get("sessions", []):
        if s["tools_per_message"] > 8 and s["human_messages"] > 3:
            suggestions.append(
                {
                    "type": "consider",
                    "title": "High Tool-to-Message Ratio",
                    "text": f"Session '{s['slug'] or s['id'][:8]}' had {s['tools_per_message']} tool calls per message "
                    f"across {s['human_messages']} messages. Specifying file paths in prompts can reduce exploration.",
                }
            )
            break

    # NEW: Context window suggestions
    if model_metrics:
        sessions_over_75 = model_metrics.get("sessions_over_75pct", 0)
        max_util = model_metrics.get("max_utilization", 0)
        if sessions_over_75 > 0:
            suggestions.append(
                {
                    "type": "observation",
                    "title": "High Context Window Usage",
                    "text": f"{sessions_over_75} session(s) used >75% of the context window (peak: {max_util}%). "
                    "Long sessions may benefit from plan mode or splitting into sub-tasks.",
                }
            )

        avg_peak = model_metrics.get("avg_peak_utilization", 0)
        if avg_peak < 30:
            suggestions.append(
                {
                    "type": "positive",
                    "title": "Context Window Well-Managed",
                    "text": f"Average peak context utilization is {avg_peak}%. "
                    "Your sessions stay well within context limits.",
                }
            )

    if not suggestions:
        suggestions.append(
            {
                "type": "positive",
                "title": "Looking Good",
                "text": "No strong signals detected. Your interaction patterns seem balanced.",
            }
        )

    return suggestions
