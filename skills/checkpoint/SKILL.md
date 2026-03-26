---
name: checkpoint
description: |
  Manage conversation checkpoints — save, list, restore, fork, and rewind session state.
  Use for: checkpoint, save state, snapshot, restore point, save progress, save session,
  capture state, bookmark, mark progress, list checkpoints, show checkpoints, view saves,
  saved states, checkpoint history, restore checkpoint, load checkpoint, recover state,
  return to checkpoint, go back to checkpoint, load saved state, rewind, undo, rollback,
  step back, previous state, earlier state, fork session, branch session, experiment,
  try alternative, parallel session, split session, safe experimentation.
  Subcommands: /agentic-coding-workflow:checkpoint (save), /agentic-coding-workflow:checkpoint list, /agentic-coding-workflow:checkpoint restore <name>,
  /agentic-coding-workflow:checkpoint fork, /agentic-coding-workflow:checkpoint rewind <n>
allowed-tools: Bash, Read, Write, Grep, Glob
effort: low
user-invocable: true
argument-hint: "[list | restore <name> | fork | rewind <n> | <name>]"
---

# Checkpoint Manager

Save, list, restore, fork, and rewind conversation checkpoints. Checkpoints capture git state, working directory, and context notes for later reference.

## Usage

```
/agentic-coding-workflow:checkpoint [name]              — Save a checkpoint (auto-names if omitted)
/agentic-coding-workflow:checkpoint list                — List all saved checkpoints
/agentic-coding-workflow:checkpoint restore <name>      — Restore a specific checkpoint
/agentic-coding-workflow:checkpoint fork                — Create a fork point for experimentation
/agentic-coding-workflow:checkpoint rewind <n>          — Go back N checkpoints
```

Parse `$ARGUMENTS` to determine the subcommand. If the first word is `list`, `restore`, `fork`, or `rewind`, route to that subcommand. Otherwise treat the entire argument as a checkpoint name (or auto-generate one).

## Subcommand: Save (default)

Create a checkpoint of the current session state.

```bash
mkdir -p .claude/agentic-coding-workflow:checkpoints
```

If no name provided, auto-generate one from recent work context:
- `debugging-{component}`, `refactored-{module}`, `added-{feature}`, `pre-{operation}`, `fixed-{issue}`

Create the checkpoint:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh create \
    "<checkpoint-name>" \
    "<1-2 sentence summary of recent work>" \
    "<context notes>" \
    <true|false>  # true if name was auto-generated
```

Report: checkpoint ID, name, git state, how to list (`/agentic-coding-workflow:checkpoint list`) and restore (`/agentic-coding-workflow:checkpoint restore <name>`).

## Subcommand: List

```bash
${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh list
```

Format as a table sorted by timestamp (newest first):

```
=== Checkpoints (N total) ===

[YYYY-MM-DD] checkpoint-name
  ID: ckpt-YYYYMMDD-HHMMSS-xxxx
  Summary: Brief description of what was being worked on
```

If no checkpoints exist, show: "No checkpoints found. Create one with `/agentic-coding-workflow:checkpoint [name]`"

## Subcommand: Restore

Requires a checkpoint name or ID as argument.

1. **Find checkpoint:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh get "<name>"
   ```
   If not found, run `list` and show available checkpoints.

2. **Show details:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh show "<name>"
   ```

3. **Auto-checkpoint current state** (safety backup):
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh create \
       "pre-restore-$(date +%H%M%S)" \
       "Auto-checkpoint before restoring to <name>" \
       "Safety backup before /agentic-coding-workflow:checkpoint restore" \
       true
   ```

4. **Load context** from checkpoint files:
   ```bash
   cat .claude/checkpoints/<checkpoint-id>/metadata.json
   cat .claude/checkpoints/<checkpoint-id>/context.json
   ```

5. **Offer options** if git state differs:
   - **Context only** (default) — load checkpoint context, keep current code
   - **View diff** — show changes since checkpoint
   - **Checkout code** — restore to checkpoint commit
   - **New branch** — create branch from checkpoint commit

## Subcommand: Fork

Create a fork point for safe experimentation.

1. **Create fork checkpoint:**
   ```bash
   fork_name="fork-point-$(date +%Y%m%d-%H%M%S)"
   ${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh create \
       "$fork_name" \
       "Fork point for experimentation" \
       "Created via /agentic-coding-workflow:checkpoint fork" \
       true
   ```

2. **Record fork metadata:**
   ```bash
   session_id="fork-$(openssl rand -hex 4)"
   ${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh fork \
       "$fork_name" "$session_id" "$checkpoint_id"
   ```

3. **Present options:**
   - Continue experimenting in current session (original state is saved)
   - Abandon experiment: `/agentic-coding-workflow:checkpoint restore <fork-name>`
   - Parallel exploration: new terminal → `claude` → `/agentic-coding-workflow:checkpoint restore <fork-name>`
   - Git tip: `git checkout -b experiment/your-idea`

## Subcommand: Rewind

Go back N checkpoints. Argument must be a positive integer.

**Important:** This cannot literally rewind conversation history. It loads context from an earlier checkpoint and optionally reverts git state.

1. **Auto-checkpoint current state** (same as restore)

2. **List checkpoints and select the Nth most recent:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh list
   ```

3. **Show the target checkpoint** details and offer the same options as restore (context only, view diff, checkout code, new branch).

If N exceeds checkpoint count, show available checkpoints and ask user to pick one.

## Storage

```
.claude/checkpoints/
├── index.json                    # Checkpoint registry
└── ckpt-YYYYMMDD-HHMMSS-xxxx/   # Individual checkpoint
    ├── metadata.json             # Name, timestamp, summary
    ├── context.json              # Working dir, git info, notes
    └── state.json                # Reserved for future state capture
```

## Error Handling

| Error | Resolution |
|-------|------------|
| No `.claude/checkpoints/` | Create it automatically |
| Checkpoint not found | Show available checkpoints |
| Name already exists | Append unique number |
| Git not available | Proceed without git state, warn user |
| Corrupted checkpoint | Attempt to read individual files, report what's missing |
| Uncommitted changes on restore | Warn user, suggest stash or commit first |
