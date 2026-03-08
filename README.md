# Claude Code Analytics

Analyze your Claude Code interaction patterns and get actionable suggestions to improve your workflow. Generates interactive HTML reports from your local `~/.claude/` session data.

**What makes this different from cost trackers:** This focuses on *how* you use Claude Code — prompt quality, tool usage habits, context window utilization, and workflow patterns — not just token counts.

## What It Measures

- **Prompt Quality** — word count distribution, context provision rate, specificity (file/function references), question ratio
- **Tool Usage** — frequency, tools-per-message ratio, subagent delegation, plan mode and skill usage
- **Models & Context** — which models you use, context window utilization over time, cache hit rates
- **Workflow Efficiency** — messages per session, short-prompt/many-exchange detection, session duration
- **Thematic Analysis** — auto-classifies sessions (debugging, feature dev, refactoring, exploration), n-gram frequency, per-category efficiency
- **Temporal Patterns** — activity heatmap by hour/day, prompt length trends over time

## Installation

### From the plugin marketplace

```bash
# Add the marketplace (one-time)
claude plugin marketplace add egypationgodbill/claude-code-analytics

# Install the plugin
claude plugin install claude-code-analytics@egypationgodbill-claude-code-analytics
```

### From source

```bash
# Clone the repo
git clone https://github.com/egypationgodbill/claude-code-analytics.git

# Install the plugin locally
claude plugin install --path ./claude-code-analytics/plugins/claude-code-analytics
```

## Usage

### Slash command

After installing the plugin, you get the `/analytics` slash command:

```
/analytics              # Analyze last 30 days
/analytics --days 7     # Last 7 days
/analytics --project Espresso  # Filter by project name
/analytics --all        # All time
```

> **Note:** The `/analytics` command is provided by this plugin — it is not built into Claude Code. You must install the plugin first (see Installation above).

### Standalone script

You can also run the analysis script directly without installing the plugin:

```bash
python3 scripts/analyze_sessions.py --output /tmp/analytics-report.html
open /tmp/analytics-report.html
```

### Natural language

Once the plugin is installed, you can also ask Claude Code:

> "Analyze my Claude usage"
> "How am I using Claude Code?"
> "Show me my prompt quality metrics"

The skill auto-triggers and runs the analysis.

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--days N` | 30 | Analyze last N days |
| `--project <name>` | all | Filter to projects matching substring |
| `--session <id>` | all | Analyze a specific session by ID prefix |
| `--output <path>` | `/tmp/deliberate-thinking-report.html` | Output file path |
| `--all` | off | Override date filter, analyze everything |

## Report

The generated HTML report has six tabs:

1. **Dashboard** — summary cards, suggestions, distribution overview
2. **Prompt Analysis** — scatter plot of prompt lengths over time, word count distribution, daily averages
3. **Tools & Workflow** — tool frequency, subagent types, slash command usage
4. **Activity** — hour x day heatmap, session bubble chart, session table
5. **Models & Context** — model usage breakdown, context window utilization timeline, token analysis
6. **Themes** — session categorization, word cloud, n-gram tables, per-category efficiency

Every metric card and chart title has a **?** hint icon — hover over it to see what the metric means and why it matters.

## Requirements

- Python 3.7+ (no pip dependencies)
- Claude Code with session data in `~/.claude/`

## Privacy

- **All data stays local.** The script reads only from `~/.claude/` on your machine.
- **Nothing is transmitted.** No network requests, no telemetry, no external services.
- **Prompt excerpts are truncated** to 100 characters in report tables.

## License

MIT
