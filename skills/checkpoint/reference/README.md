# Claude Code Checkpoint System

A checkpointing and session management system for Claude Code that enables saving conversation context, rewinding to previous states, and branching sessions for experimentation.

## Quick Reference

| Command | Description |
|---------|-------------|
| `/checkpoint [name]` | Save current state with optional name |
| `/checkpoints` | List all saved checkpoints |
| `/restore <name>` | Restore a specific checkpoint |
| `/rewind <n>` | Conceptually rewind n steps |
| `/fork-session` | Branch session for experimentation |

## Installation

The skills are installed in `~/.claude/skills/`:

```
~/.claude/skills/
├── checkpoint/
│   ├── SKILL.md
│   ├── scripts/
│   │   └── checkpoint-manager.sh
│   └── reference/
│       └── README.md (this file)
├── checkpoints/
│   └── SKILL.md
├── restore/
│   └── SKILL.md
├── rewind/
│   └── SKILL.md
└── fork-session/
    └── SKILL.md
```

## Storage Structure

Checkpoints are stored per-project in `.claude/checkpoints/`:

```
your-project/
└── .claude/
    └── checkpoints/
        ├── index.json                    # Registry of all checkpoints
        └── ckpt-YYYYMMDD-HHMMSS-xxxx/   # Individual checkpoint
            ├── metadata.json             # Name, timestamp, summary
            ├── context.json              # Working dir, git state, notes
            └── state.json                # Reserved for future use
```

## What Gets Captured

### Captured (Per Checkpoint)
- **Git state**: Branch, commit SHA, list of uncommitted files
- **Working directory**: Absolute path where work was happening
- **Timestamp**: When checkpoint was created
- **User context**: Summary and notes about current work
- **Checkpoint metadata**: Name, ID, auto-generated flag

### NOT Captured (Limitations)
- **Conversation history**: Messages are stored server-side at Anthropic
- **Claude's context window**: Internal state cannot be serialized
- **MCP server states**: External tool states are not captured
- **Runtime variables**: Any ephemeral state in the session

## Detailed Usage

### Creating Checkpoints

**With auto-generated name:**
```
/checkpoint
```
Claude analyzes recent work and generates a descriptive name like `debugging-auth-flow` or `added-api-tests`.

**With custom name:**
```
/checkpoint pre-major-refactor
```

**Auto-naming patterns:**
- `debugging-{component}` - Bug investigation
- `added-{feature}` - New functionality
- `fixed-{issue}` - Bug fixes
- `refactored-{module}` - Code restructuring
- `pre-{operation}` - Before risky changes
- `updated-{target}` - Modifications

### Listing Checkpoints

```
/checkpoints
```

Output:
```
=== Checkpoints (3 total) ===

[2025-01-11] added-user-validation
  ID: ckpt-20250111-154500-x1y2
  Summary: Implemented input validation for user forms

[2025-01-11] pre-refactor-cleanup
  ID: ckpt-20250111-143522-c3d4
  Summary: Before major code restructuring

[2025-01-10] initial-feature-branch
  ID: ckpt-20250110-091500-z3w4
  Summary: Started work on new feature
```

### Restoring Checkpoints

```
/restore pre-refactor-cleanup
```

Options provided:
1. **Context only** - Load checkpoint context, keep current code
2. **View diff** - See code changes since checkpoint
3. **Restore code** - Checkout the git commit from checkpoint
4. **Cancel** - Stay at current state

### Rewinding

```
/rewind 2
```

Shows available checkpoints and offers to restore the 2nd most recent.

**Note:** This is conceptual rewinding. It creates a safety checkpoint of current state, then helps you return to an earlier context.

### Forking Sessions

```
/fork-session
```

Creates a fork point for safe experimentation:
- Checkpoint current state with `fork-point-*` name
- Continue experimenting in current session
- Can restore fork point if experiment fails
- Can start parallel session from fork point

## Example Workflows

### Workflow 1: Safe Refactoring

```
1. /checkpoint pre-refactor
2. [Make extensive changes]
3. If something breaks: /restore pre-refactor
4. If successful: /checkpoint refactor-complete
```

### Workflow 2: Exploring Alternatives

```
1. /fork-session
2. [Try approach A]
3. /checkpoint approach-a-result
4. /restore fork-point-*
5. [Try approach B]
6. /checkpoint approach-b-result
7. [Compare and choose]
```

### Workflow 3: Long Session Management

```
1. /checkpoint session-start
2. [Work for a while]
3. /checkpoint milestone-1
4. [More work]
5. /checkpoint milestone-2
6. [If need to review]: /checkpoints
7. [If need earlier context]: /restore milestone-1
```

### Workflow 4: Pre-Migration Safety

```
1. /checkpoint pre-database-migration
2. [Run migrations]
3. If issues: /restore pre-database-migration
   - Optionally: git checkout <sha> to restore code
```

## Git Integration

Checkpoints capture git state but don't modify your repository:

- **SHA captured**: Know exactly what commit was current
- **Branch recorded**: Track which branch you were on
- **Dirty files listed**: See what was uncommitted

**Manual git restoration:**
```bash
# View checkpoint's git state
cat .claude/checkpoints/<id>/context.json | jq '.git'

# Checkout that commit
git checkout <sha>

# Or create a recovery branch
git checkout -b recovery/my-checkpoint <sha>
```

## Maintenance

### Cleanup Old Checkpoints

```bash
# Keep only last 20 checkpoints
~/.claude/skills/checkpoint/scripts/checkpoint-manager.sh cleanup 20
```

### Export a Checkpoint

```bash
~/.claude/skills/checkpoint/scripts/checkpoint-manager.sh export my-checkpoint exported.json
```

### Delete Specific Checkpoint

```bash
~/.claude/skills/checkpoint/scripts/checkpoint-manager.sh delete my-checkpoint
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No checkpoints found" | Run `/checkpoint` to create your first one |
| "Checkpoint not found" | Run `/checkpoints` to see available names |
| Script permission denied | Run `chmod +x ~/.claude/skills/checkpoint/scripts/*.sh` |
| jq not found | Install jq: `brew install jq` (macOS) or `apt install jq` (Linux) |
| Git SHA doesn't exist | Commit may have been garbage collected; skip git restore |

## Dependencies

- **jq**: JSON processing (required)
- **git**: For git state capture (optional but recommended)
- **openssl**: For generating random IDs (usually pre-installed)

## Limitations & Honest Assessment

This system provides **context checkpointing**, not true session state restoration.

**What it IS:**
- A way to bookmark and document your work progress
- A safety net before risky operations
- A context loader for continuing from earlier work
- A git state reference system

**What it is NOT:**
- A time machine for conversation history
- A way to literally restore Claude's memory
- A replacement for git branches/commits

**Best mental model:** Think of checkpoints as detailed bookmarks with context notes, not save states in a video game.

## Contributing

To extend or modify:

1. Skills are in `~/.claude/skills/<name>/SKILL.md`
2. Core logic is in `~/.claude/skills/checkpoint/scripts/checkpoint-manager.sh`
3. Test changes in a non-critical project first

## Version

- **System Version:** 1.0.0
- **Compatible with:** Claude Code CLI
- **Storage Format:** JSON v1
