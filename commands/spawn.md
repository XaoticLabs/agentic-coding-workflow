---
allowed-tools:
  - Read
  - Glob
  - Bash
  - AskUserQuestion
effort: low
---

# Spawn Primary Claude Instance

Launches a new full Claude Code session in a tmux pane with an agent role preloaded as context. Use when work needs an independently visible, steerable session or a separate session lifecycle. Choose placement by required capabilities and oversight; implementation can also run in the current session or a suitably configured subagent.

## Input

$ARGUMENTS - One of:
- An agent role name: `researcher`, `test-writer`, `explorer`
- An agent role + context: `evaluator --context pr-diff.patch`
- An agent role + task prompt: `test-writer "Write tests for the auth module"`
- An agent role + worktree: `test-writer --worktree feature-branch`

## Instructions

### Phase 1: Parse Arguments

Extract from the input:
- **Role name** (required) — matches a file in `agents/` directory
- **`--context <file>`** (optional) — additional context file to load
- **`--worktree <branch>`** (optional) — create/use a git worktree for isolation
- **Task prompt** (optional) — quoted string describing what the instance should do

`--context` is an option of this slash command only. Load the file explicitly in the initial prompt; the Claude CLI uses documented `--agent` selection, not a `--context` flag. See the [CLI reference](https://code.claude.com/docs/en/cli-reference).

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

If not in tmux, tell the user:
> You need to be in a tmux session. Run: `tmux new-session -s work`

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

Select the plugin agent and build an interactive Claude invocation. Resolve the extra context path before changing to a worktree:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
ROLE_FILE="${PLUGIN_ROOT}/agents/${ROLE_NAME}.md"
WORK_DIR="${WORKTREE_PATH:-$(pwd)}"

# Loading the plugin registers its agents and applies their frontmatter settings.
CLAUDE_ARGS=(claude --plugin-dir "$PLUGIN_ROOT" --agent "agentic-coding-workflow:${ROLE_NAME}")
INITIAL_PROMPT="${TASK_PROMPT:-}"

# Add extra context if provided
if [ -n "${CONTEXT_FILE:-}" ]; then
  [ -r "$CONTEXT_FILE" ] || { echo "Context file not readable: $CONTEXT_FILE" >&2; exit 1; }
  CONTEXT_FILE=$(realpath "$CONTEXT_FILE")
  INITIAL_PROMPT="Read the context file at ${CONTEXT_FILE} before starting.

${INITIAL_PROMPT}"
fi

# A positional initial prompt keeps the instance interactive and steerable.
[ -z "$INITIAL_PROMPT" ] || CLAUDE_ARGS+=("$INITIAL_PROMPT")
printf -v CMD '%q ' "${CLAUDE_ARGS[@]}"
```

Create a new tmux pane and send the command:

```bash
# Run through Bash so the quoted argument array survives tmux's shell boundary.
tmux split-window -h -c "$WORK_DIR" bash -lc "$CMD"

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
/agentic-coding-workflow:spawn evaluator --context pr-diff.patch
```
Opens an evaluator instance and explicitly reads the PR diff as context.

```
/agentic-coding-workflow:spawn test-writer "Write integration tests for the accounts API"
```
Launches an interactive test writer with an initial task prompt.

```
/agentic-coding-workflow:spawn explorer --worktree explore/auth-system
```
Creates a worktree on a new branch and launches an explorer instance there.
