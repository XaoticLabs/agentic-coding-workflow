---
name: rewind
description: |
  Conceptually rewind the conversation state. Creates a checkpoint of current state, then
  provides context for continuing from an earlier point. Keywords: rewind, undo, go back,
  previous state, rollback, undo changes, step back, earlier state.
allowed-tools: Bash, Read, Write, Grep, Glob
user-invocable: true
---

# Rewind - Return to Earlier State

Conceptually rewind the conversation to a previous point by creating a context restoration point.

## Usage

```
/rewind <n>
```

- **n** (required): Number of conceptual "steps" or checkpoints to go back

## Important Limitations

**This command cannot literally rewind Claude's conversation history.** What it does instead:

1. Creates an automatic checkpoint of the current state (safety backup)
2. Helps you identify what state you want to return to
3. Provides context to help continue as if from that earlier point
4. Can help revert file changes if git state was captured

For true conversation branching, consider:
- Starting a fresh session with context from a checkpoint
- Using `/fork-session` before making experimental changes

## Execution Steps

### Step 1: Validate Input

```bash
# Ensure n is a positive integer
if ! [[ "$1" =~ ^[0-9]+$ ]] || [[ "$1" -eq 0 ]]; then
    echo "Error: Please provide a positive number (e.g., /rewind 3)"
    exit 1
fi
```

### Step 2: List Recent Checkpoints

Show the user what checkpoints are available:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh list
```

### Step 3: Auto-checkpoint Current State

Before any rewind operation, save the current state:

```bash
# Generate auto-checkpoint name based on current context
${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh create \
    "pre-rewind-$(date +%H%M%S)" \
    "Auto-checkpoint before rewind operation" \
    "User initiated /rewind $n" \
    true
```

### Step 4: Identify Target State

If rewinding by checkpoint count:
- List checkpoints and select the nth most recent
- Show the user details of that checkpoint

If rewinding by "message count" (conceptual):
- Explain that exact message rewind isn't possible
- Offer to show recent checkpoints as alternatives

### Step 5: Show Rewind Preview

Display what state the user would be "returning" to:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh show <target-checkpoint>
```

Include:
- Checkpoint name and timestamp
- Git state at that time (branch, SHA)
- Working directory
- Any context notes

### Step 6: Offer Options

Present the user with choices:

1. **Restore git state** - If the checkpoint has a git SHA, offer to checkout that commit
2. **Load context** - Read the checkpoint's context to inform future responses
3. **Start fresh session** - Recommend starting a new claude session with the checkpoint context
4. **Cancel** - Keep current state, checkpoint was already saved

## Example Interaction

**User:** `/rewind 2`

**Claude:** I'll help you conceptually rewind to an earlier state.

**Current State (auto-saved):**
- Checkpoint: `pre-rewind-143022`
- Git: `feature/auth` at `abc1234` (2 uncommitted files)

**Available Checkpoints:**
1. `added-validation` (15 min ago)
2. `pre-database-update` (45 min ago) ← **Target**
3. `initial-setup` (2 hours ago)

**Target Checkpoint: `pre-database-update`**
- Created: 2025-01-11 13:45:22
- Git: `feature/auth` at `def5678`
- Summary: Before applying database schema changes
- Context: Working on user authentication flow

**What would you like to do?**

1. **Review the state** - I'll load this checkpoint's context and continue as if from that point
2. **Revert git changes** - Run `git checkout def5678` to restore code state
3. **Start fresh** - I recommend starting a new Claude session with this context
4. **Cancel** - Stay at current state (your auto-checkpoint is saved)

---

**User:** Let's review the state and continue from there

**Claude:** Loading context from `pre-database-update` checkpoint...

Based on the checkpoint, at that point we were:
- Working in `/Users/dev/myproject`
- On branch `feature/auth` at commit `def5678`
- Focused on: "Working on user authentication flow"
- Before: Database schema changes were applied

I'll continue our work with this context in mind. What would you like to focus on?

## Git Reversion (Optional)

If the user wants to restore the actual code state:

```bash
# Check current git status
git status

# Show what would change
git diff <checkpoint-sha>

# If user confirms, restore code state
git checkout <checkpoint-sha>

# Or create a new branch from that point
git checkout -b recovery/<checkpoint-name> <checkpoint-sha>
```

## Error Handling

- **No checkpoints exist**: Create one now and explain checkpoint system
- **n exceeds checkpoint count**: Show available checkpoints, suggest alternatives
- **No git available**: Skip git-related restoration options
- **Uncommitted changes would be lost**: Warn user, suggest committing or stashing first

## Conceptual Model

Think of `/rewind` as:
- A way to **bookmark and reference** earlier states
- A **safety net** (auto-checkpoints before risky operations)
- A **context loader** for continuing from earlier work
- NOT a literal time machine for conversation history

## Related Commands

- `/checkpoint [name]` - Create a checkpoint manually
- `/checkpoints` - List all saved checkpoints
- `/restore <name>` - Restore a specific named checkpoint
- `/fork-session` - Branch the session for experimentation
