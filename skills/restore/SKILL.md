---
name: restore
description: |
  Restore a specific named checkpoint. Use when users want to return to a saved state,
  load context from a previous session point, or recover from unwanted changes.
  Keywords: restore checkpoint, load checkpoint, recover state, return to checkpoint,
  load save, restore session, go back to checkpoint, load saved state.
allowed-tools: Bash, Read, Write, Grep, Glob
user-invocable: true
---

# Restore - Load a Named Checkpoint

Restore context and optionally code state from a specific saved checkpoint.

## Usage

```
/restore <checkpoint-name>
```

- **checkpoint-name** (required): Name or ID of the checkpoint to restore

## What Gets Restored

### Context Loading
- Checkpoint summary and notes
- Working directory context
- Git state information (branch, commit SHA)
- Any user-provided context from checkpoint creation

### Optional Code Restoration
- Can checkout the git commit from checkpoint time
- Can show diff between current and checkpoint state
- User controls whether to actually revert code

### Cannot Restore
- Actual conversation message history
- Claude's internal context window state
- Runtime/ephemeral state

## Execution Steps

### Step 1: Validate Checkpoint Exists

```bash
# Find checkpoint by name or ID
checkpoint_id=$(${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh get "<name>")

if [[ -z "$checkpoint_id" ]]; then
    echo "Checkpoint not found: <name>"
    # Show available checkpoints
    ${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh list
    exit 1
fi
```

### Step 2: Show Checkpoint Details

Display full checkpoint information before restoring:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh show "<name>"
```

Present to user:
- **Name and ID**
- **Created**: Timestamp
- **Summary**: What was being worked on
- **Context notes**: Any additional information
- **Git state**: Branch, SHA, uncommitted files at checkpoint time
- **Working directory**: Path where work was happening

### Step 3: Auto-checkpoint Current State

Before restoration, save current state:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh create \
    "pre-restore-$(date +%H%M%S)" \
    "Auto-checkpoint before restoring to <checkpoint-name>" \
    "Safety backup before /restore operation" \
    true
```

### Step 4: Load Context

Read the checkpoint's context files and summarize for the conversation:

```bash
# Read checkpoint files
cat .claude/checkpoints/<checkpoint-id>/metadata.json
cat .claude/checkpoints/<checkpoint-id>/context.json
cat .claude/checkpoints/<checkpoint-id>/state.json
```

### Step 5: Offer Git Restoration Options

If git information is available in the checkpoint:

```bash
# Get checkpoint git SHA
checkpoint_sha=$(jq -r '.git.sha' .claude/checkpoints/<checkpoint-id>/context.json)
current_sha=$(git rev-parse HEAD)

if [[ "$checkpoint_sha" != "$current_sha" ]]; then
    echo "Code has changed since checkpoint"
    echo "Checkpoint SHA: $checkpoint_sha"
    echo "Current SHA: $current_sha"

    # Show what changed
    git log --oneline $checkpoint_sha..HEAD
fi
```

Present options:
1. **Context only** - Load checkpoint context, keep current code
2. **View diff** - Show code changes since checkpoint
3. **Checkout code** - Restore code to checkpoint state
4. **New branch** - Create branch from checkpoint commit

### Step 6: Execute Restoration

Based on user choice:

**Context only:**
```
I've loaded the context from checkpoint "<name>".

At that point, you were:
- Working on: <summary>
- In directory: <working_dir>
- On branch: <branch> at <sha>
- Notes: <context_notes>

How would you like to continue?
```

**Git checkout:**
```bash
# Warn about uncommitted changes
git status --porcelain

# If clean, checkout
git checkout <checkpoint_sha>

# Or create recovery branch
git checkout -b restore/<checkpoint-name> <checkpoint_sha>
```

## Example Interaction

**User:** `/restore pre-database-migration`

**Claude:** I'll restore the checkpoint `pre-database-migration`.

**Checkpoint Details:**
- **ID:** `ckpt-20250111-120000-c3d4`
- **Created:** 2025-01-11 12:00:00
- **Summary:** State before running database migrations
- **Git:** Branch `main` at `abc1234`
- **Notes:** About to run schema migrations for user table changes

**Current State:**
- Git: `main` at `def5678` (4 commits ahead of checkpoint)
- 2 uncommitted files

**Auto-saved current state as:** `pre-restore-143522`

**What would you like to do?**

1. **Load context only** - Continue with checkpoint context loaded (recommended)
2. **View code diff** - See what changed since the checkpoint
3. **Restore code** - Checkout the checkpoint commit
4. **Cancel** - Keep current state

---

**User:** Load context only

**Claude:** Context loaded from `pre-database-migration`.

**Restored Context:**
At this checkpoint, we were preparing to run database migrations for user table changes. The codebase was on branch `main` at commit `abc1234`.

The state was captured before any migrations were applied, so if you need to re-run or modify migrations, this is the reference point.

How would you like to proceed?

## Error Handling

| Error | Resolution |
|-------|------------|
| Checkpoint not found | Show list of available checkpoints |
| Corrupted checkpoint | Attempt to read individual files, report what's missing |
| Git SHA doesn't exist | Checkpoint may reference pruned commits; skip git restoration |
| Uncommitted changes | Warn user, suggest stash or commit first |
| No `.claude/checkpoints/` | Explain checkpoint system, offer to create first checkpoint |

## Related Commands

- `/checkpoint [name]` - Create a new checkpoint
- `/checkpoints` - List all saved checkpoints
- `/rewind <n>` - Quick rewind by count
- `/fork-session` - Branch for experimentation
