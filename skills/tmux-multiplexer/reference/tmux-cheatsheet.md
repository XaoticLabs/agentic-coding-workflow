# tmux Quick Reference

## Session Commands

| Command | Description |
|---------|-------------|
| `tmux new-session -s name` | Create named session |
| `tmux new-session -d -s name` | Create detached session |
| `tmux ls` | List sessions |
| `tmux attach -t name` | Attach to session |
| `tmux switch -t name` | Switch to session (from within tmux) |
| `tmux kill-session -t name` | Kill session |
| `tmux rename-session new` | Rename current session |

## Window Commands

| Command | Description |
|---------|-------------|
| `tmux new-window` | Create window |
| `tmux new-window -n name` | Create named window |
| `tmux select-window -t 0` | Select window by index |
| `tmux select-window -t name` | Select window by name |
| `tmux rename-window name` | Rename current window |
| `tmux kill-window` | Kill current window |
| `tmux list-windows` | List windows |

## Pane Commands

| Command | Description |
|---------|-------------|
| `tmux split-window -h` | Split vertical (left/right) |
| `tmux split-window -v` | Split horizontal (top/bottom) |
| `tmux split-window -h -p 30` | Split with 30% width |
| `tmux select-pane -t 0` | Select pane by index |
| `tmux select-pane -UDLR` | Select pane by direction |
| `tmux kill-pane` | Kill current pane |
| `tmux kill-pane -t 0` | Kill specific pane |
| `tmux list-panes` | List panes |
| `tmux resize-pane -UDLR 5` | Resize by 5 cells |
| `tmux resize-pane -Z` | Toggle zoom |

## Send Keys

| Command | Description |
|---------|-------------|
| `tmux send-keys "cmd" Enter` | Send command + Enter |
| `tmux send-keys -t 0 "cmd" Enter` | Send to specific pane |
| `tmux send-keys C-c` | Send Ctrl-C |
| `tmux send-keys C-d` | Send Ctrl-D (EOF) |
| `tmux send-keys C-z` | Send Ctrl-Z (suspend) |

## Capture Output

| Command | Description |
|---------|-------------|
| `tmux capture-pane -p` | Print pane content |
| `tmux capture-pane -p -S -100` | Last 100 lines |
| `tmux capture-pane -p -S -` | Entire scrollback |
| `tmux capture-pane -t 0 -p` | Capture specific pane |
| `tmux save-buffer file.txt` | Save buffer to file |

## Layouts

| Layout | Description |
|--------|-------------|
| `even-horizontal` | Equal width columns |
| `even-vertical` | Equal height rows |
| `main-horizontal` | Large top, small bottom |
| `main-vertical` | Large left, small right |
| `tiled` | Grid arrangement |

```bash
tmux select-layout tiled
tmux select-layout -E  # Rebalance
```

## Target Syntax

Targets specify session, window, and pane:

| Target | Meaning |
|--------|---------|
| `session:` | Session only |
| `session:window` | Session and window |
| `session:window.pane` | Full specification |
| `:window` | Window in current session |
| `.pane` | Pane in current window |
| `{last}` | Previous pane |
| `{next}` | Next pane |

## Default Key Bindings

Default prefix: `Ctrl-b`

| Keys | Action |
|------|--------|
| `Prefix d` | Detach |
| `Prefix c` | New window |
| `Prefix n/p` | Next/prev window |
| `Prefix 0-9` | Select window |
| `Prefix %` | Split vertical |
| `Prefix "` | Split horizontal |
| `Prefix o` | Next pane |
| `Prefix arrows` | Navigate panes |
| `Prefix z` | Zoom pane |
| `Prefix x` | Kill pane |
| `Prefix [` | Copy mode |
| `Prefix ]` | Paste |

## Format Variables

Useful for scripting with `-F`:

| Variable | Description |
|----------|-------------|
| `#{session_name}` | Session name |
| `#{window_index}` | Window index |
| `#{window_name}` | Window name |
| `#{pane_index}` | Pane index |
| `#{pane_current_command}` | Running command |
| `#{pane_pid}` | Pane process ID |
| `#{pane_current_path}` | Current directory |

Example:
```bash
tmux list-panes -F "#{pane_index}: #{pane_current_command} in #{pane_current_path}"
```

## Environment Detection

```bash
# Check if in tmux
[ -n "$TMUX" ] && echo "In tmux"

# Get current session
tmux display-message -p "#{session_name}"

# Get current window
tmux display-message -p "#{window_index}"

# Get current pane
tmux display-message -p "#{pane_index}"
```

## Common Patterns

### Run command in new pane
```bash
tmux split-window -h "npm test"
```

### Run command and keep pane open
```bash
tmux split-window -h "npm test; exec bash"
```

### Create session with initial command
```bash
tmux new-session -d -s build "npm run build"
```

### Send command to background session
```bash
tmux send-keys -t build "npm run watch" Enter
```

### Wait for command to complete
```bash
# Check if pane is idle (shows shell, not running command)
while tmux list-panes -t 0 -F "#{pane_current_command}" | grep -v bash; do
  sleep 1
done
```
