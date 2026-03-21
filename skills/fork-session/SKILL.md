---
name: fork-session
description: |
  Branch the current session for experimentation. Creates a checkpoint and provides
  instructions for parallel exploration. Use when users want to try different approaches,
  experiment without losing current progress, or create parallel workstreams.
  Keywords: fork session, branch session, experiment, try alternative, parallel session,
  split session, create branch, explore option, safe experimentation.
allowed-tools: Bash, Read, Write, Grep, Glob
user-invocable: true
---

# Fork Session - Branch for Experimentation

Create a checkpoint and set up for safe experimentation with the ability to return to the current state.

## Usage

```
/fork-session
```

No arguments required. Creates a fork point from the current session state.

## What Fork Session Does

1. **Creates a checkpoint** named `fork-point-<timestamp>`
2. **Records fork metadata** including parent session info
3. **Provides instructions** for:
   - Continuing in current session (experimental path)
   - Starting a new session from fork point
   - Returning to original state

## Conceptual Model

```
                    ┌─── Experimental Path (current session)
                    │    Try risky changes, explore alternatives
Fork Point ─────────┤
(checkpoint)        │
                    └─── Safe Path (new session)
                         Start fresh from checkpoint if experiment fails
```

## Execution Steps

### Step 1: Create Fork Point Checkpoint

```bash
# Generate fork checkpoint with current context
fork_name="fork-point-$(date +%Y%m%d-%H%M%S)"

checkpoint_id=$(${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh create \
    "$fork_name" \
    "Fork point for experimentation" \
    "Created via /fork-session for safe experimentation" \
    true)

echo "Fork checkpoint created: $fork_name"
```

### Step 2: Generate Session Identifier

Create a unique identifier for tracking the fork relationship:

```bash
session_id="fork-$(openssl rand -hex 4)"
echo "Experimental session ID: $session_id"
```

### Step 3: Record Fork Metadata

```bash
${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh fork \
    "$fork_name" \
    "$session_id" \
    "$checkpoint_id"
```

### Step 4: Capture Current Git State

```bash
# Get current branch and create a marker
git_branch=$(git branch --show-current 2>/dev/null || echo "none")
git_sha=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

# Optionally create a git branch marker
# git branch "fork/$fork_name" 2>/dev/null || true
```

### Step 5: Present Fork Information

Display to user:

```
=== Session Forked ===

Fork Point: fork-point-20250111-143022
Session ID: fork-a1b2c3d4
Git State: main @ abc1234

You are now on the EXPERIMENTAL path.

=== Options ===

1. CONTINUE EXPERIMENTING (current session)
   - Try risky changes, explore alternatives
   - This session continues from the fork point
   - Original state is safely checkpointed

2. RETURN TO FORK POINT (if experiment fails)
   - Run: /restore fork-point-20250111-143022
   - Or start a new Claude session and run the restore

3. START PARALLEL SESSION (new terminal)
   - Open new terminal
   - Run: claude
   - Then: /restore fork-point-20250111-143022
   - Work on alternative approach simultaneously

=== Git Tip ===
Consider creating a git branch for your experiment:
  git checkout -b experiment/your-idea

This way you can easily discard changes:
  git checkout main
```

## Example Interaction

**User:** `/fork-session`

**Claude:** I'll create a fork point for safe experimentation.

**Fork Created:**
- **Checkpoint:** `fork-point-20250111-143022`
- **Session ID:** `fork-a1b2`
- **Git:** `feature/auth` at `abc1234` (clean)

**You're now on the experimental path.** Feel free to try risky changes - your current state is safely saved.

**Your Options:**

| Action | How |
|--------|-----|
| Continue experimenting | Just keep working in this session |
| Abandon experiment | `/restore fork-point-20250111-143022` |
| Parallel exploration | New terminal → `claude` → `/restore fork-point-20250111-143022` |

**Git Tip:** Create an experimental branch for easy code rollback:
```bash
git checkout -b experiment/my-idea
```

What would you like to experiment with?

---

**User:** Let's try a completely different approach to the authentication system

**Claude:** Great! Since we've forked, I can explore a radically different approach without risk.

Currently we have session-based auth. Let me explore a JWT-based approach instead...

*[Proceeds with experimental implementation]*

---

**User:** This isn't working. Let's go back to the fork point.

**Claude:** No problem. Let me restore the fork point.

```bash
/restore fork-point-20250111-143022
```

*[Restores context and offers to revert any code changes]*

## Fork Relationships

The checkpoint system tracks fork relationships:

```json
{
  "forks": [
    {
      "parent_checkpoint": "fork-point-20250111-143022",
      "forked_session": "fork-a1b2",
      "fork_checkpoint": "ckpt-20250111-143022-x1y2",
      "timestamp": "2025-01-11T14:30:22Z"
    }
  ]
}
```

This allows you to:
- See all fork points in a project
- Track experimental branches
- Understand session lineage

## Best Practices

1. **Fork before major experiments** - Try new architectures, libraries, or approaches
2. **Name your experiments** - After forking, create a checkpoint with a descriptive name
3. **Use git branches** - Combine fork points with git branches for code-level protection
4. **Document your experiment** - Note what you're trying and why
5. **Clean up failed experiments** - Delete checkpoints from abandoned paths

## When to Fork

| Situation | Recommendation |
|-----------|----------------|
| Trying a new library | Fork first |
| Major refactoring | Fork first |
| Exploring 2+ solutions | Fork, try one, restore, try another |
| Quick bug fix | Probably don't need to fork |
| Following established pattern | Probably don't need to fork |

## Related Commands

- `/checkpoint [name]` - Create a named checkpoint
- `/checkpoints` - List all checkpoints (including fork points)
- `/restore <name>` - Return to a fork point
- `/rewind <n>` - Quick rewind by count
