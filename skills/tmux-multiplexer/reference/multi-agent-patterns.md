# Multi-Agent Coordination Patterns

Advanced patterns for orchestrating multiple Claude Code instances.

## Pattern Categories

1. **Parallel Execution** - Independent tasks running simultaneously
2. **Pipeline/Sequential** - Tasks that depend on previous results
3. **Map-Reduce** - Split work, then aggregate results
4. **Supervisor** - One agent coordinates others

---

## 1. Parallel Execution Patterns

> **Convention:** All patterns use windows (tabs) + panes within the current tmux session.
> If not already in tmux, create a session first: `tmux new-session -s work`

### 1.1 File-Parallel Review

Each agent reviews a different file independently.

```bash
#!/bin/bash
# parallel-review.sh - Review multiple files in parallel

files=("$@")
name="review-$$"

tmux new-window -n "$name"

for i in "${!files[@]}"; do
  file="${files[$i]}"
  [ $i -gt 0 ] && tmux split-window -t ":$name"
  tmux send-keys -t ":$name" "claude -p 'Review $file for bugs, security issues, and improvements' > /tmp/review-$i.md" Enter
  tmux select-layout -t ":$name" tiled
done

echo "Reviews started in tab: $name"
echo "Results will be in /tmp/review-*.md"
```

### 1.2 Test Matrix

Run tests across different configurations.

```bash
#!/bin/bash
# test-matrix.sh - Run tests with different configs

configs=("node16" "node18" "node20")
name="test-matrix"

tmux new-window -n "$name"

for i in "${!configs[@]}"; do
  config="${configs[$i]}"
  [ $i -gt 0 ] && tmux split-window -v -t ":$name"
  tmux send-keys -t ":$name" "NODE_VERSION=$config npm test 2>&1 | tee /tmp/test-$config.log" Enter
done

tmux select-layout -t ":$name" even-vertical
```

### 1.3 Research Squad

Multiple agents research different topics.

```bash
#!/bin/bash
# research-squad.sh

topics=(
  "Best practices for error handling in TypeScript"
  "Modern React state management approaches"
  "API rate limiting strategies"
)

name="research"
tmux new-window -n "$name"

for i in "${!topics[@]}"; do
  [ $i -gt 0 ] && tmux split-window -h -t ":$name"
  topic="${topics[$i]}"
  tmux send-keys -t ":$name" "claude -p 'Research: $topic. Provide actionable recommendations.' > /tmp/research-$i.md" Enter
  tmux select-layout -t ":$name" tiled
done
```

---

## 2. Pipeline Patterns

### 2.1 Sequential Processing

Output of one stage feeds into the next. Uses separate windows (tabs) for each stage.

```bash
#!/bin/bash
# sequential-pipeline.sh

# Stage 1: Generate code
tmux new-window -n "stage1"
tmux send-keys -t ":stage1" "claude -p 'Generate a REST API handler for user registration' > /tmp/stage1.ts" Enter

# Wait for stage 1
sleep 2
while pgrep -f "claude.*stage1" >/dev/null; do sleep 1; done

# Stage 2: Review the generated code
tmux new-window -n "stage2"
tmux send-keys -t ":stage2" "claude --context /tmp/stage1.ts -p 'Review this code and suggest improvements' > /tmp/stage2.md" Enter

# Wait for stage 2
sleep 2
while pgrep -f "claude.*stage2" >/dev/null; do sleep 1; done

# Stage 3: Generate tests
tmux new-window -n "stage3"
tmux send-keys -t ":stage3" "claude --context /tmp/stage1.ts -p 'Generate comprehensive unit tests for this code' > /tmp/stage3.ts" Enter

tmux select-window -t ":stage1"
```

### 2.2 Build Pipeline with Gates

Each stage must pass before proceeding.

```bash
#!/bin/bash
# build-pipeline.sh

name="build"
tmux new-window -n "$name"

# Run lint
tmux send-keys -t ":$name" 'npm run lint && echo "LINT_PASS" || echo "LINT_FAIL"' Enter
tmux split-window -v -t ":$name"

# Run type check
tmux send-keys -t ":$name" 'npm run typecheck && echo "TYPES_PASS" || echo "TYPES_FAIL"' Enter
tmux split-window -v -t ":$name"

# Run tests
tmux send-keys -t ":$name" 'npm test && echo "TESTS_PASS" || echo "TESTS_FAIL"' Enter

tmux select-layout -t ":$name" even-vertical
```

---

## 3. Map-Reduce Patterns

### 3.1 Component Analysis

Analyze components, then synthesize findings.

```bash
#!/bin/bash
# analyze-components.sh

components=(src/components/*.tsx)
name="analyze"

tmux new-window -n "$name"

# Map phase: analyze each component
for i in "${!components[@]}"; do
  comp="${components[$i]}"
  [ $i -gt 0 ] && tmux split-window -t ":$name"
  tmux send-keys -t ":$name" "claude -p 'Analyze $comp for accessibility issues' > /tmp/a11y-$i.md" Enter
  tmux select-layout -t ":$name" tiled

  # Limit concurrent panes
  [ $((i % 4)) -eq 3 ] && sleep 30
done

# Reduce phase will be manual or in another tab
echo "After completion, synthesize with:"
echo "claude -p 'Synthesize these accessibility findings' --context /tmp/a11y-*.md"
```

### 3.2 Distributed Code Search

Search different parts of codebase, combine results.

```bash
#!/bin/bash
# distributed-search.sh

dirs=("src/api" "src/components" "src/utils" "src/hooks")
pattern="$1"
name="search"

tmux new-window -n "$name"

for i in "${!dirs[@]}"; do
  dir="${dirs[$i]}"
  [ $i -gt 0 ] && tmux split-window -h -t ":$name"
  tmux send-keys -t ":$name" "grep -r '$pattern' $dir > /tmp/search-$i.txt 2>&1; echo '=== Done: $dir ==='" Enter
  tmux select-layout -t ":$name" tiled
done
```

---

## 4. Supervisor Patterns

### 4.1 Orchestrator Pane

One pane monitors and coordinates others.

```bash
#!/bin/bash
# orchestrator.sh

name="orchestrated"
tmux new-window -n "$name"

# Control pane stays in bash for monitoring
tmux send-keys -t ":$name" "echo 'Control pane - monitor workers here'" Enter

# Worker panes
tmux split-window -h -t ":$name"
tmux send-keys -t ":$name" "claude -p 'Implement feature A'" Enter

tmux split-window -v -t ":$name"
tmux send-keys -t ":$name" "claude -p 'Implement feature B'" Enter

# Select control pane
tmux select-pane -t ":$name.0"

# In control pane, you can run monitoring commands:
# watch -n 5 'for p in 1 2; do echo "=== Pane $p ==="; tmux capture-pane -t $p -p | tail -5; done'
```

### 4.2 Health Monitor

Continuously monitor agent panes.

```bash
#!/bin/bash
# monitor.sh - Run in control pane

while true; do
  clear
  echo "=== Agent Status $(date) ==="
  echo ""

  for pane in $(tmux list-panes -F "#{pane_index}"); do
    [ "$pane" = "0" ] && continue  # Skip control pane

    cmd=$(tmux display-message -t "$pane" -p "#{pane_current_command}")
    last_line=$(tmux capture-pane -t "$pane" -p | tail -1)

    echo "Pane $pane: $cmd"
    echo "  Last: $last_line"
    echo ""
  done

  sleep 5
done
```

---

## 5. Error Handling

### 5.1 Retry Pattern

```bash
#!/bin/bash
# retry-task.sh

max_retries=3
pane=$1
task="$2"

for i in $(seq 1 $max_retries); do
  tmux send-keys -t "$pane" "$task" Enter

  # Wait for completion
  sleep 5
  while tmux list-panes -t "$pane" -F "#{pane_current_command}" | grep -q claude; do
    sleep 2
  done

  # Check if successful (look for error markers)
  output=$(tmux capture-pane -t "$pane" -p | tail -20)
  if ! echo "$output" | grep -qi "error\|failed\|exception"; then
    echo "Task succeeded on attempt $i"
    exit 0
  fi

  echo "Attempt $i failed, retrying..."
  sleep 2
done

echo "Task failed after $max_retries attempts"
exit 1
```

### 5.2 Timeout Handler

```bash
#!/bin/bash
# timeout-task.sh

timeout_seconds=300
pane=$1
task="$2"

tmux send-keys -t "$pane" "$task" Enter

start=$(date +%s)
while true; do
  # Check if still running
  if ! tmux list-panes -t "$pane" -F "#{pane_current_command}" | grep -q claude; then
    echo "Task completed"
    exit 0
  fi

  # Check timeout
  now=$(date +%s)
  elapsed=$((now - start))
  if [ $elapsed -gt $timeout_seconds ]; then
    echo "Task timed out after ${timeout_seconds}s"
    tmux send-keys -t "$pane" C-c
    exit 1
  fi

  sleep 5
done
```

---

## 6. Result Collection

### 6.1 Aggregate Results

```bash
#!/bin/bash
# collect-results.sh

session="$1"
output_file="${2:-/tmp/aggregated-results.md}"

echo "# Aggregated Results" > "$output_file"
echo "Collected: $(date)" >> "$output_file"
echo "" >> "$output_file"

for window in $(tmux list-windows -t "$session" -F "#{window_index}:#{window_name}"); do
  IFS=: read -r idx name <<< "$window"

  echo "## Window: $name" >> "$output_file"
  echo "" >> "$output_file"

  for pane in $(tmux list-panes -t "$session:$idx" -F "#{pane_index}"); do
    echo "### Pane $pane" >> "$output_file"
    echo '```' >> "$output_file"
    tmux capture-pane -t "$session:$idx.$pane" -p >> "$output_file"
    echo '```' >> "$output_file"
    echo "" >> "$output_file"
  done
done

echo "Results saved to: $output_file"
```

### 6.2 JSON Results

```bash
#!/bin/bash
# json-results.sh

session="$1"

echo "{"
echo '  "session": "'"$session"'",'
echo '  "timestamp": "'"$(date -Iseconds)"'",'
echo '  "panes": ['

first=true
for pane in $(tmux list-panes -t "$session" -a -F "#{session_name}:#{window_index}.#{pane_index}"); do
  $first || echo ","
  first=false

  content=$(tmux capture-pane -t "$pane" -p | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')

  echo "    {"
  echo '      "target": "'"$pane"'",'
  echo '      "content": '"$content"
  echo -n "    }"
done

echo ""
echo "  ]"
echo "}"
```

---

## Best Practices

1. **Limit concurrency**: 4-6 agents max to avoid resource exhaustion
2. **Use named windows (tabs)**: Easy cleanup and identification — visible in status bar
3. **Capture output**: Always save results before killing windows
4. **Handle failures**: Implement retry/timeout for unreliable tasks
5. **Clean up**: Kill windows when done to free resources (`tmux kill-window -t :name`)
6. **Monitor progress**: Use a control pane or watch commands
7. **Windows over sessions**: Create new windows (tabs), not sessions — keeps everything in one place
