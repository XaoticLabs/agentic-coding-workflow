---
allowed-tools:
  - Read
  - Glob
  - Bash
  - AskUserQuestion
effort: low
---

# Spawn Primary Claude Instance

Launches a new full Claude Code session in a tmux pane with an agent role preloaded as context. For when you need a visible, steerable Claude instance — not a fire-and-forget subagent.

## Input

$ARGUMENTS - One of:
- An agent role name: `researcher`, `test-writer`, `explorer`
- An agent role + context: `code-reviewer --context pr-diff.patch`
- An agent role + task prompt: `test-writer "Write tests for the auth module"`
- An agent role + worktree: `test-writer --worktree feature-branch`

## Instructions

### Phase 1: Parse Arguments

Extract from the input:
- **Role name** (required) — matches a file in `agents/` directory
- **`--context <file>`** (optional) — additional context file to load
- **`--worktree <branch>`** (optional) — create/use a git worktree for isolation
- **Task prompt** (optional) — quoted string describing what the instance should do

**Validate the role:**
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
ROLE_FILE="${PLUGIN_ROOT}/agents/${ROLE_NAME}.md"
ls "$ROLE_FILE" 2>/dev/null || echo "ROLE_NOT_FOUND"
```

If role not found, list available roles:
```bash
ls "${PLUGIN_ROOT}/agents/"*.md 2>/dev/null | xargs -I{} basename {} .md
```

### Phase 2: Pre-flight Checks

```bash
# Verify tmux
command -v tmux >/dev/null 2>&1 || echo "TMUX_NOT_FOUND"

# Verify claude CLI
command -v claude >/dev/null 2>&1 || echo "CLAUDE_NOT_FOUND"

# Check if in tmux session
[ -n "$TMUX" ] || echo "NOT_IN_TMUX"
```

If not in tmux, inform the user and offer to create a session:
```bash
SESSION_NAME="spawn-$(date +%s)"
tmux new-session -d -s "$SESSION_NAME"
tmux attach -t "$SESSION_NAME"
```

### Phase 3: Set Up Working Directory

**If `--worktree` specified:**
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
BRANCH_NAME="$WORKTREE_ARG"
WORKTREE_PATH="${WORKTREE_BASE}/${BRANCH_NAME}"

# Ensure .claude/worktrees/ is gitignored
if ! grep -q '\.claude/worktrees/' "${REPO_ROOT}/.gitignore" 2>/dev/null; then
  echo -e '\n# Git worktrees\n.claude/worktrees/' >> "${REPO_ROOT}/.gitignore"
fi

mkdir -p "$WORKTREE_BASE"

if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME"; then
  git worktree add "$WORKTREE_PATH" "$BRANCH_NAME"
else
  git worktree add -b "$BRANCH_NAME" "$WORKTREE_PATH"
fi
```

**If no worktree:** use the current project directory.

### Phase 4: Launch Claude Instance

Build the claude command:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
ROLE_FILE="${PLUGIN_ROOT}/agents/${ROLE_NAME}.md"
WORK_DIR="${WORKTREE_PATH:-$(pwd)}"

# Base command with agent context
CMD="claude --context '$ROLE_FILE'"

# Add extra context if provided
if [ -n "$CONTEXT_FILE" ]; then
  CMD="$CMD --context '$CONTEXT_FILE'"
fi

# Add task prompt if provided (non-interactive mode)
if [ -n "$TASK_PROMPT" ]; then
  CMD="$CMD -p '$TASK_PROMPT'"
fi
```

Create a new tmux pane and send the command:

```bash
# Split current window to create a new pane
tmux split-window -h -c "$WORK_DIR"

# Send the claude command to the new pane
tmux send-keys "$CMD" Enter

# Rebalance panes
tmux select-layout tiled
```

### Phase 5: Report

```
Spawned Claude instance!

| Setting    | Value                                    |
|------------|------------------------------------------|
| Role       | {ROLE_NAME}                              |
| Context    | agents/{ROLE_NAME}.md                    |
| Extra      | {CONTEXT_FILE or "none"}                 |
| Directory  | {WORK_DIR}                               |
| Worktree   | {WORKTREE_PATH or "none"}                |
| Task       | {TASK_PROMPT or "interactive"}           |

Switch to pane: Ctrl+B then arrow keys
```

## Error Handling

- **Role not found:** List available roles and ask user to pick one
- **Not in tmux:** Offer to create a session, or suggest running `tmux` first
- **Claude not installed:** Direct user to install Claude Code
- **Worktree conflict:** If branch already has a worktree, offer to reuse it

## Example Usage

```
/agentic-coding-workflow:spawn researcher
```
Opens a new tmux pane with an interactive Claude session loaded with the researcher role.

```
/agentic-coding-workflow:spawn code-reviewer --context pr-diff.patch
```
Opens a reviewer instance with both the code-reviewer role and PR diff as context.

```
/agentic-coding-workflow:spawn test-writer "Write integration tests for the accounts API"
```
Launches a test writer with a specific task — runs non-interactively.

```
/agentic-coding-workflow:spawn explorer --worktree explore/auth-system
```
Creates a worktree on a new branch and launches an explorer instance there.
