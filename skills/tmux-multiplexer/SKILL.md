---
name: tmux-multiplexer
description: |
  Orchestrate tmux terminal multiplexing for multi-agent workflows. Use when: splitting
  terminal panes, launching parallel Claude instances, coordinating multiple agents,
  running background tasks, creating workspaces with multiple windows. Keywords: tmux,
  panes, windows, split, multiplexer, parallel agents, multi-agent, coordinate, orchestrate,
  launch claude, new terminal, background tasks, split screen, terminal tabs.
allowed-tools: Bash, Read, Write
user-invocable: true
---

# tmux Multiplexer for Multi-Agent Coordination

Orchestrate terminal panes and coordinate multiple Claude Code instances for parallel task execution.

## Quick Start

```bash
# Check if tmux is available
command -v tmux >/dev/null || echo "Install tmux first"

# Check if already in tmux
[ -n "$TMUX" ] && echo "In tmux" || echo "Not in tmux"
```

## Core tmux Operations

### Session Management

```bash
# Create named session
tmux new-session -d -s workspace

# List sessions
tmux list-sessions

# Attach to session
tmux attach-session -t workspace

# Kill session
tmux kill-session -t workspace

# Detach from current session (interactive)
# Prefix + d (usually Ctrl-b d)
```

### Window Management

```bash
# Create new window in current session
tmux new-window -t workspace -n "build"

# List windows
tmux list-windows -t workspace

# Select window by index
tmux select-window -t workspace:0

# Select window by name
tmux select-window -t workspace:build

# Rename current window
tmux rename-window "new-name"

# Kill window
tmux kill-window -t workspace:build
```

### Pane Management

```bash
# Split horizontally (top/bottom)
tmux split-window -v

# Split vertically (left/right)
tmux split-window -h

# Split with specific size (percentage)
tmux split-window -h -p 30

# Navigate panes
tmux select-pane -U  # up
tmux select-pane -D  # down
tmux select-pane -L  # left
tmux select-pane -R  # right

# Navigate by index
tmux select-pane -t 0

# Resize panes
tmux resize-pane -U 5  # up 5 cells
tmux resize-pane -D 5  # down
tmux resize-pane -L 10 # left
tmux resize-pane -R 10 # right

# Zoom pane (toggle fullscreen)
tmux resize-pane -Z

# Kill pane
tmux kill-pane -t 0

# List panes with IDs
tmux list-panes -F "#{pane_index}: #{pane_current_command}"
```

### Sending Commands to Panes

```bash
# Send command to specific pane
tmux send-keys -t workspace:0.1 "echo hello" Enter

# Send to pane in current window
tmux send-keys -t 1 "npm test" Enter

# Send Ctrl-C to cancel
tmux send-keys -t 0 C-c

# Send without pressing Enter (for partial input)
tmux send-keys -t 0 "partial command"
```

### Capturing Output

```bash
# Capture pane content
tmux capture-pane -t 0 -p

# Capture with history (last 1000 lines)
tmux capture-pane -t 0 -p -S -1000

# Capture to file
tmux capture-pane -t 0 -p > /tmp/pane-output.txt

# Capture all panes in window
for pane in $(tmux list-panes -F "#{pane_index}"); do
  echo "=== Pane $pane ===" >> /tmp/all-panes.txt
  tmux capture-pane -t "$pane" -p >> /tmp/all-panes.txt
done
```

## Claude Code Patterns

### Launch Claude in New Pane

```bash
# Split and run claude with prompt
tmux split-window -h "claude -p 'Review this code for bugs'"

# Launch in background pane with context
tmux split-window -v "claude --context file.ts -p 'Explain this file'"

# Non-interactive execution with output capture
tmux split-window -h "claude -p 'Generate unit tests' > /tmp/tests-output.txt 2>&1"
```

### Coordinated Multi-Agent Launch

```bash
# Create workspace with multiple Claude agents
tmux new-session -d -s agents
tmux send-keys -t agents "claude -p 'Work on frontend component'" Enter
tmux split-window -h -t agents
tmux send-keys -t agents "claude -p 'Work on backend API'" Enter
tmux split-window -v -t agents
tmux send-keys -t agents "claude -p 'Write integration tests'" Enter
tmux attach-session -t agents
```

### Monitor Agent Progress

```bash
# Watch all panes for completion
watch -n 2 'for p in $(tmux list-panes -F "#{pane_index}"); do
  echo "--- Pane $p ---"
  tmux capture-pane -t $p -p | tail -5
done'
```

## Multi-Agent Workflows

### Pattern 1: Parallel Code Review

Split task across agents reviewing different files simultaneously.

```bash
#!/bin/bash
# Review multiple files in parallel
files=("src/api.ts" "src/utils.ts" "src/types.ts")
tmux new-session -d -s review

for i in "${!files[@]}"; do
  if [ $i -gt 0 ]; then
    tmux split-window -h -t review
    tmux select-layout -t review tiled
  fi
  tmux send-keys -t review "claude -p 'Review ${files[$i]} for bugs and improvements'" Enter
done

tmux attach-session -t review
```

### Pattern 2: Build + Test + Lint Pipeline

Run multiple validation tasks in parallel.

```bash
tmux new-session -d -s pipeline -n validate
tmux send-keys -t pipeline "npm run build 2>&1 | tee /tmp/build.log" Enter
tmux split-window -v -t pipeline
tmux send-keys -t pipeline "npm test 2>&1 | tee /tmp/test.log" Enter
tmux split-window -h -t pipeline
tmux send-keys -t pipeline "npm run lint 2>&1 | tee /tmp/lint.log" Enter
tmux attach-session -t pipeline
```

### Pattern 3: Research Squad

Launch multiple Claude instances for parallel research.

```bash
tmux new-session -d -s research
topics=("React hooks best practices" "TypeScript generics patterns" "Testing strategies")

for i in "${!topics[@]}"; do
  [ $i -gt 0 ] && tmux split-window -v -t research
  tmux send-keys -t research "claude -p 'Research: ${topics[$i]}' > /tmp/research-$i.md" Enter
done

tmux select-layout -t research even-vertical
tmux attach-session -t research
```

### Pattern 4: Frontend + Backend Coordination

Coordinate agents working on different parts of a feature.

```bash
tmux new-session -d -s feature -n frontend
tmux send-keys -t feature "claude -p 'Implement user profile component in React'" Enter

tmux new-window -t feature -n backend
tmux send-keys -t feature:backend "claude -p 'Implement /api/profile endpoint'" Enter

tmux new-window -t feature -n tests
tmux send-keys -t feature:tests "claude -p 'Write E2E tests for profile feature'" Enter

tmux select-window -t feature:frontend
tmux attach-session -t feature
```

## Helper Scripts

Use the provided scripts in `scripts/` directory:

```bash
# Setup a workspace with multiple panes
./scripts/setup-workspace.sh my-workspace 4 tiled

# Launch claude in a new pane with a prompt
./scripts/launch-claude-pane.sh "Review this code"

# Collect output from all panes
./scripts/collect-pane-outputs.sh > review-results.txt

# Clean up session when done
./scripts/cleanup-session.sh my-workspace
```

## Layouts

Available tmux layouts for organizing panes:

| Layout | Description |
|--------|-------------|
| `even-horizontal` | Equal width columns |
| `even-vertical` | Equal height rows |
| `main-horizontal` | Large top pane, smaller bottom |
| `main-vertical` | Large left pane, smaller right |
| `tiled` | Grid arrangement |

```bash
# Apply layout
tmux select-layout tiled

# Rebalance after adding panes
tmux select-layout -E
```

## Safety Guidelines

1. **Always check tmux availability** before running commands
2. **Use named sessions** for organization and easy cleanup
3. **Limit concurrent agents** to avoid resource exhaustion (4-6 max recommended)
4. **Clean up sessions** when tasks complete
5. **Capture output** before killing panes to preserve results
6. **Handle both contexts**: already in tmux vs starting fresh

### In-tmux vs Not-in-tmux

```bash
if [ -n "$TMUX" ]; then
  # Already in tmux - split current window
  tmux split-window -h "claude -p 'task'"
else
  # Not in tmux - create new session
  tmux new-session -d -s work "claude -p 'task'"
  tmux attach-session -t work
fi
```

### Prevent Runaway Spawning

```bash
# Check pane count before adding more
pane_count=$(tmux list-panes | wc -l)
if [ "$pane_count" -ge 6 ]; then
  echo "Too many panes ($pane_count). Clean up first."
  exit 1
fi
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "no server running" | Start with `tmux new-session` |
| "session not found" | List sessions: `tmux ls` |
| Pane too small | Resize: `tmux resize-pane -R 20` |
| Commands not running | Ensure `Enter` is sent: `send-keys "cmd" Enter` |
| Can't see output | Capture: `tmux capture-pane -p` |

## Reference

See additional documentation:
- `reference/tmux-cheatsheet.md` - Quick command reference
- `reference/multi-agent-patterns.md` - Advanced coordination patterns
