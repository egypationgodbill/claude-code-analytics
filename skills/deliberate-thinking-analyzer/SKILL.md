---
name: deliberate-thinking-analyzer
description: Analyze your Claude Code interaction patterns to measure prompt deliberateness, tool usage, and workflow habits. Use when the user asks about their Claude Code usage, wants to improve prompting, asks "how am I using Claude", wants session analytics, or mentions deliberate thinking analysis.
---

# Deliberate Thinking Analyzer

Generates an interactive HTML report from your `~/.claude/` session data showing prompt quality metrics, tool usage patterns, workflow habits, and actionable suggestions.

## How to Run

Execute the analysis script, then open the report:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/analyze_sessions.py" [OPTIONS]
open /tmp/deliberate-thinking-report.html
```

## Filtering Options

| Flag | Default | Description |
|------|---------|-------------|
| `--days N` | 30 | Analyze last N days |
| `--project <substring>` | all | Filter to projects matching substring |
| `--session <id-prefix>` | all | Analyze a specific session |
| `--output <path>` | `/tmp/deliberate-thinking-report.html` | Output file path |
| `--all` | off | Override date filter, analyze everything |

## What It Measures

### Prompt Quality
- Word/character count per prompt (average, median, distribution)
- Question ratio (prompts ending with `?`)
- Context provision rate (prompts >50 words or containing file paths/code blocks)
- Specificity score (file names, function names, specific instructions)

### Workflow Patterns
- Tool usage frequency (which tools, how often)
- Subagent delegation (types, frequency)
- Plan mode and skill invocations
- Slash command usage from history

### Efficiency
- Messages per session (back-and-forth indicator)
- Tool calls per human message
- Sessions where short prompts led to many exchanges

### Temporal
- Activity by hour/day
- Prompt length trends over time
- Session duration distribution

### Thematic Analysis
- Keyword + tool-pattern session classification (debugging, feature_dev, refactoring, exploration, etc.)
- N-gram frequency on prompt text
- Effectiveness correlation: efficiency vs prompt length by category

## Interpreting Results

**Short prompts are NOT always bad.** They may indicate:
- Well-configured CLAUDE.md providing implicit context
- Follow-up messages in an established context
- Efficient slash command usage

**The suggestion engine considers context:**
- Short prompts + many exchanges → "consider more upfront context"
- Short prompts + few exchanges → "your CLAUDE.md may be providing good context"
- No plan mode on long sessions → "try plan mode for complex tasks"
- Repeated file reads → "specify file paths in your prompt"

## After Running

1. Open the HTML report in your browser
2. Use the filter bar to narrow by date range, project, or category
3. Review the suggestion cards on the Dashboard tab
4. Share key suggestions in the conversation for discussion

## Data Privacy

- Reads only local `~/.claude/` data
- Never transmits data anywhere
- Prompt excerpts are truncated to 100 characters in tables
