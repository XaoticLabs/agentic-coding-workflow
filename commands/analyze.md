---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Write
  - Agent
  - AskUserQuestion
effort: medium
---

# Analyze Data & Generate Visualizations

You are a data analyst. Your task is to take query results, CSV files, or datasets and produce insights, summaries, and visualizations (HTML charts or ASCII tables).

## Input

$ARGUMENTS — One of:
- A file path to a CSV/JSON dataset: `results.csv`
- Piped output from `/agentic-coding-workflow:query`: `"analyze the results from the last query"`
- A file path with a specific question: `data.csv "what's the trend over time?"`
- A directory of data files: `./exports/ "summarize all datasets"`
- Inline data pasted in the prompt

## Instructions

### Phase 1: Load and Inspect Data

**Determine the data source:**

- **File path** — read the file directly
- **"Last query" reference** — look for the most recent CSV in `/tmp/query_results*.csv` or ask the user to specify
- **Inline data** — parse from the prompt
- **Directory** — list files and ask which to analyze (or analyze all if requested)

**Inspect the data:**
```bash
# CSV: row count, column names, first few rows
head -5 <file>
wc -l <file>

# JSON: structure overview
python3 -c "import json; data=json.load(open('<file>')); print(type(data), len(data) if isinstance(data, list) else list(data.keys())[:10])"
```

Present a data summary:
```
Dataset: results.csv
Rows: 1,247
Columns: date, user_count, revenue, region
Date range: 2024-01-01 to 2024-03-15
```

### Phase 2: Automatic Analysis

Run a standard analysis pass using Python:

```bash
python3 << 'PYEOF'
import csv
import json
import sys
from collections import Counter
from datetime import datetime

# Load data
# [adapted to the actual file format]

# For each column, compute:
# - Numeric: min, max, mean, median, stddev, null count
# - Categorical: unique count, top 5 values, null count
# - Date/Time: range, gaps, frequency
# - Detect: outliers (>3 stddev), trends (monotonic increase/decrease), correlations

# Print summary
PYEOF
```

Present findings:
```markdown
## Data Overview

| Column | Type | Summary |
|--------|------|---------|
| date | date | 2024-01-01 to 2024-03-15 (daily) |
| user_count | numeric | min=45, max=312, avg=178, trend=↑ |
| revenue | numeric | min=$1.2K, max=$45K, avg=$12.3K |
| region | categorical | 5 unique (US: 45%, EU: 30%, APAC: 15%, ...) |

### Key Findings
- User count is trending up 12% month-over-month
- Revenue per user varies significantly by region (US: $89, EU: $52)
- There's a gap in data on 2024-02-14 (holiday?)
```

### Phase 3: Answer Specific Questions

If the user asked a specific question about the data, answer it directly:

- **Trend questions** ("what's the trend?") → compute slope, week-over-week or month-over-month changes
- **Comparison questions** ("which region performs best?") → group, rank, compute differences
- **Anomaly questions** ("anything unusual?") → outlier detection, gap analysis
- **Correlation questions** ("does X relate to Y?") → compute correlation coefficient, scatter description

### Phase 4: Generate Visualizations

Create visualizations based on the data shape and user request:

**HTML charts (default for rich visualizations):**

Generate a self-contained HTML file with embedded Chart.js:

```bash
cat << 'HTMLEOF' > /tmp/chart_<name>.html
<!DOCTYPE html>
<html>
<head>
  <title>Data Analysis</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
    .chart-container { position: relative; height: 400px; margin: 20px 0; }
    table { border-collapse: collapse; width: 100%; margin: 20px 0; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background: #f5f5f5; }
    .metric { display: inline-block; padding: 16px 24px; margin: 8px; background: #f8f9fa; border-radius: 8px; text-align: center; }
    .metric .value { font-size: 2em; font-weight: bold; }
    .metric .label { color: #666; font-size: 0.9em; }
  </style>
</head>
<body>
  <h1>[Analysis Title]</h1>

  <!-- Key metrics -->
  <div class="metrics">
    <div class="metric"><div class="value">[value]</div><div class="label">[label]</div></div>
  </div>

  <!-- Chart -->
  <div class="chart-container"><canvas id="chart1"></canvas></div>

  <!-- Data table -->
  <table>...</table>

  <script>
    const ctx = document.getElementById('chart1').getContext('2d');
    new Chart(ctx, {
      type: '[bar|line|pie|doughnut|scatter]',
      data: { /* ... */ },
      options: { responsive: true, maintainAspectRatio: false }
    });
  </script>
</body>
</html>
HTMLEOF
```

Choose chart types based on data:
- **Time series** → line chart
- **Categorical comparison** → bar chart (horizontal if >6 categories)
- **Proportions** → pie/doughnut chart
- **Distribution** → histogram (bar chart with bins)
- **Two numeric variables** → scatter plot
- **Multiple dimensions** → grouped/stacked bar chart

**ASCII tables (for terminal-friendly output):**
Use formatted tables when the user doesn't need HTML or for quick summaries.

**Open the HTML file:**
```bash
open /tmp/chart_<name>.html  # macOS
```

### Phase 5: Summary Report

```markdown
## Analysis Report

### Dataset
- Source: [file or query]
- Size: [rows × columns]
- Time range: [if applicable]

### Key Insights
1. [Most important finding]
2. [Second finding]
3. [Third finding]

### Visualizations Generated
- `/tmp/chart_<name>.html` — [description]

### Recommendations
- [Data-driven suggestion based on findings]

### Follow-Up Questions to Explore
- [Suggested deeper analysis]
```

## Error Handling

**If data file not found:**
List available files in the directory and ask the user to specify.

**If data format is unrecognized:**
Show the first few lines and ask: "What format is this data in?"

**If Python is not available:**
Fall back to bash-only analysis (awk, sort, uniq -c) and ASCII output.

**If data is too large (>100K rows):**
Sample the data for analysis, note the sampling, and offer to run on full dataset if needed.

## Important Notes

- Never modify the source data files
- All generated files go in `/tmp/` — they're disposable visualizations
- If the data contains PII or sensitive information, note it and ask before including in HTML output
- Prefer simple, clear charts over complex multi-axis visualizations
- Always show the actual numbers alongside visualizations — charts can be misleading without context

## Example Usage

```
/agentic-coding-workflow:analyze results.csv
```
Loads the CSV, runs automatic analysis, generates insights and an HTML chart.

```
/agentic-coding-workflow:analyze data.csv "what's the week-over-week growth rate?"
```
Computes and presents the growth rate with a trend chart.

```
/agentic-coding-workflow:analyze ./exports/ "summarize revenue by region"
```
Scans the exports directory, finds revenue data, groups by region, generates comparison chart.

```
/agentic-coding-workflow:analyze "the results from the last query"
```
Picks up the most recent `/query` output and analyzes it.
