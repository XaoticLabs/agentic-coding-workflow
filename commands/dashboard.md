---
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
effort: low
---

# Dashboard — Monitor Parallel Work

Launches a live dashboard in a tmux pane that monitors all active worktrees, shows Claude activity, and displays inter-agent messages.

## Input

$ARGUMENTS - Options:
- Empty — launch dashboard with defaults (30s refresh)
- `--interval 15` — set refresh interval in seconds

## Instructions

### Phase 1: Pre-flight

```bash
# Verify tmux
command -v tmux >/dev/null 2>&1 || echo "TMUX_NOT_FOUND"

# Check if in tmux session
[ -n "$TMUX" ] || echo "NOT_IN_TMUX"

# Verify the dashboard script exists
SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/dashboard.sh"
[ -f "$SCRIPT" ] || echo "SCRIPT_NOT_FOUND"
```

If not in tmux, tell the user:
> You need to be in a tmux session. Run: `tmux new-session -s work`

### Phase 2: Launch Dashboard Pane

Create a new tmux pane (split horizontally, 30% height) and run the dashboard script:

```bash
# Parse arguments
ARGS=""
# Add flags based on $ARGUMENTS parsing

# Create a bottom pane for the dashboard
tmux split-window -v -l 12 -c "$(git rev-parse --show-toplevel)" \
  "${CLAUDE_PLUGIN_ROOT}/scripts/dashboard.sh ${ARGS}"
```

### Phase 3: Confirm

```
Dashboard launched in bottom pane!

Monitoring: .claude/worktrees/*
Refresh: every 30s

Controls:
  Ctrl-B ↑/↓  — switch between dashboard and work pane
  Ctrl-C      — stop dashboard
  /agentic-coding-workflow:git-worktree status — one-time status check (no dashboard needed)
```
