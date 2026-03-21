---
name: checkpoint
description: |
  Save the current conversation state as a checkpoint. Use when users want to save their
  progress, create a restore point before risky operations, or mark a milestone in their
  work session. Keywords: checkpoint, save, snapshot, restore point, save progress,
  save state, bookmark, mark progress, save session, capture state.
allowed-tools: Bash, Read, Write, Grep, Glob
user-invocable: true
---

# Checkpoint - Save Conversation State

Save the current conversation state with context for later restoration or reference.

## Usage

```
/checkpoint [name]
```

- **name** (optional): A descriptive name for this checkpoint
  - If not provided, auto-generate a name based on recent work context
  - Format: lowercase, hyphenated, 3-5 words (e.g., "auth-refactor-started")

## What Gets Saved

### Captured State
- Git SHA (code state at checkpoint time)
- Git branch and uncommitted file list
- Working directory path
- User-provided context notes
- Timestamp and checkpoint metadata
- Summary of recent work focus

### Limitations (Cannot Capture)
- Actual conversation message history (server-side)
- Claude's internal context window
- Any ephemeral runtime state
- MCP server states

## Execution Steps

### Step 1: Initialize Checkpoint Directory

```bash
# Ensure .claude/checkpoints exists
mkdir -p .claude/checkpoints
```

### Step 2: Gather Context for Auto-naming (if no name provided)

Analyze the current conversation to generate a meaningful name:

1. Look at the most recent work focus (files modified, topics discussed)
2. Check the current todo list for active tasks
3. Review recent git changes

Generate a name following these patterns:
- `debugging-{component}` - if fixing bugs
- `refactored-{module}` - if restructuring code
- `added-{feature}` - if implementing new functionality
- `pre-{operation}` - if preparing for something
- `fixed-{issue}` - if resolving a specific problem
- `updated-{target}` - if modifying existing code

### Step 3: Create the Checkpoint

Run the checkpoint manager script:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/checkpoint/scripts/checkpoint-manager.sh create \
    "<checkpoint-name>" \
    "<summary-of-recent-work>" \
    "<context-notes>" \
    false
```

Parameters:
- **checkpoint-name**: The name (provided or auto-generated)
- **summary**: 1-2 sentence summary of what was being worked on
- **context-notes**: Any additional context about the current state
- **auto**: Set to `true` if name was auto-generated

### Step 4: Confirm to User

Report back:
- Checkpoint ID and name
- What was captured (git state, working directory)
- How to list checkpoints: `/checkpoints`
- How to restore: `/restore <name>`

## Auto-naming Examples

| Recent Activity | Generated Name |
|----------------|----------------|
| Debugging authentication flow | `debugging-auth-flow` |
| Added API endpoint tests | `added-api-tests` |
| Refactoring database queries | `refactored-db-queries` |
| Fixed null pointer in parser | `fixed-parser-null-check` |
| Setting up Redis caching | `added-redis-caching` |
| Pre-migration preparation | `pre-database-migration` |
| Code review changes | `applied-review-feedback` |

## Storage Location

```
.claude/checkpoints/
├── index.json                    # Checkpoint registry
└── ckpt-YYYYMMDD-HHMMSS-xxxx/   # Individual checkpoint
    ├── metadata.json            # Name, timestamp, summary
    ├── context.json             # Working dir, git info, notes
    └── state.json               # Reserved for future state capture
```

## Example Interaction

**User:** `/checkpoint`

**Claude:** I'll create a checkpoint of the current session state.

Based on our recent work (implementing user authentication, modifying `src/auth/login.ts` and `src/middleware/session.ts`), I'll name this checkpoint `added-session-auth`.

*Creates checkpoint...*

**Checkpoint created successfully:**
- **Name:** `added-session-auth`
- **ID:** `ckpt-20250111-143022-a1b2`
- **Git state:** Branch `feature/auth` at commit `abc1234` (3 uncommitted files)
- **Working directory:** `/Users/dev/myproject`

To view all checkpoints: `/checkpoints`
To restore this checkpoint: `/restore added-session-auth`

---

**User:** `/checkpoint pre-refactor-cleanup`

**Claude:** Creating checkpoint with name `pre-refactor-cleanup`...

*Creates checkpoint...*

**Checkpoint created successfully:**
- **Name:** `pre-refactor-cleanup`
- **ID:** `ckpt-20250111-143522-c3d4`

## Best Practices

1. **Create checkpoints before risky operations** - refactoring, migrations, major changes
2. **Use descriptive names** when manually naming checkpoints
3. **Include context** about why you're checkpointing when asked
4. **Regular checkpoints** during long sessions help track progress
5. **Clean up old checkpoints** periodically with the manager script

## Error Handling

- If `.claude/` directory doesn't exist, create it
- If checkpoint name already exists, append a unique number
- If git is not available, proceed without git state (warn user)
- If jq is not installed, provide manual fallback instructions
