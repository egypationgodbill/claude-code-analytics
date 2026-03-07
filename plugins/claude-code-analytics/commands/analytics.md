---
description: Analyze your Claude Code usage patterns and generate an interactive report
argument-hint: [--days N] [--project NAME] [--all]
allowed-tools: [Bash]
---

## Task

Run the deliberate thinking analyzer script and open the report.

The user invoked: /analytics $ARGUMENTS

Run the analysis script with any arguments the user passed:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/analyze_sessions.py" $ARGUMENTS --output /tmp/deliberate-thinking-report.html
```

Then open the report:

```bash
open /tmp/deliberate-thinking-report.html
```

Print a summary of the key suggestions from the terminal output.
