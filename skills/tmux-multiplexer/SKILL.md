---
name: tmux-multiplexer
description: |
  Orchestrate tmux terminal multiplexing for multi-agent workflows. Use when: splitting
  terminal panes, launching parallel Claude instances, coordinating multiple agents,
  running background tasks, creating workspaces with multiple windows. Keywords: tmux,
  panes, windows, split, multiplexer, parallel agents, multi-agent, coordinate, orchestrate,
  launch claude, new terminal, background tasks, split screen, terminal tabs.
allowed-tools: Bash, Read, Write
effort: low
user-invocable: true
---

# tmux Multiplexer for Multi-Agent Coordination

Orchestrate terminal panes and coordinate multiple Claude Code instances for parallel task execution.

## Quick Start

```bash
command -v tmux >/dev/null || echo "Install tmux first"
[ -n "$TMUX" ] && echo "In tmux" || echo "Not in tmux"
```

For tmux command syntax (sessions, windows, panes, layouts, key bindings), load `reference/tmux-cheatsheet.md`.

## Claude Code Patterns

### Launch Claude in New Pane

```bash
# Split and run claude with prompt
tmux split-window -h "claude -p 'Review this code for bugs'"

# Launch with context file
tmux split-window -v "claude --context file.ts -p 'Explain this file'"

# Non-interactive with output capture
tmux split-window -h "claude -p 'Generate unit tests' > /tmp/tests-output.txt 2>&1"
```

### Coordinated Multi-Agent Launch

```bash
# Create a new tab with panes for each agent
tmux new-window -n agents
tmux send-keys -t ":agents" "claude -p 'Work on frontend component'" Enter
tmux split-window -h -t ":agents"
tmux send-keys -t ":agents" "claude -p 'Work on backend API'" Enter
tmux split-window -v -t ":agents"
tmux send-keys -t ":agents" "claude -p 'Write integration tests'" Enter
```

### Monitor Agent Progress

```bash
watch -n 2 'for p in $(tmux list-panes -F "#{pane_index}"); do
  echo "--- Pane $p ---"
  tmux capture-pane -t $p -p | tail -5
done'
```

### In-tmux vs Not-in-tmux

```bash
if [ -n "$TMUX" ]; then
  # Prefer new window (tab) for independent tasks, split for related work
  tmux new-window -n work "claude -p 'task'"         # new tab
  # tmux split-window -h "claude -p 'task'"           # or split current pane
else
  tmux new-session -d -s work "claude -p 'task'"
  tmux attach-session -t work
fi
```

## Multi-Agent Workflows

For advanced coordination patterns (map-reduce, supervisor, pipeline, error handling), load `reference/multi-agent-patterns.md`.

### Quick Pattern: Parallel File Review

```bash
files=("src/api.ts" "src/utils.ts" "src/types.ts")
tmux new-window -n review

for i in "${!files[@]}"; do
  [ $i -gt 0 ] && tmux split-window -h -t ":review" && tmux select-layout -t ":review" tiled
  tmux send-keys -t ":review" "claude -p 'Review ${files[$i]} for bugs'" Enter
done
```

## Helper Scripts

```bash
# Setup a workspace with multiple panes
${CLAUDE_PLUGIN_ROOT}/skills/tmux-multiplexer/scripts/setup-workspace.sh my-workspace 4 tiled

# Launch claude in a new pane with a prompt
${CLAUDE_PLUGIN_ROOT}/skills/tmux-multiplexer/scripts/launch-claude-pane.sh "Review this code"

# Collect output from all panes
${CLAUDE_PLUGIN_ROOT}/skills/tmux-multiplexer/scripts/collect-pane-outputs.sh > results.txt

# Clean up session when done
${CLAUDE_PLUGIN_ROOT}/skills/tmux-multiplexer/scripts/cleanup-session.sh my-workspace
```

## Safety

- Always check tmux availability before running commands
- Use named sessions for organization and easy cleanup
- Limit concurrent agents to 4-6 to avoid resource exhaustion
- Capture output before killing panes to preserve results
- Check pane count before spawning more:
  ```bash
  pane_count=$(tmux list-panes | wc -l)
  [ "$pane_count" -ge 6 ] && echo "Too many panes. Clean up first." && exit 1
  ```

## References

- `reference/tmux-cheatsheet.md` — tmux command syntax and key bindings
- `reference/multi-agent-patterns.md` — advanced coordination patterns (map-reduce, supervisor, pipeline)
