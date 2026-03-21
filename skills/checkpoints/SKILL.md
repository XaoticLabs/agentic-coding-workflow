---
name: checkpoints
description: |
  List all saved conversation checkpoints with metadata. Use when users want to see their
  saved checkpoints, find a checkpoint to restore, or review their session history.
  Keywords: list checkpoints, show checkpoints, view saves, saved states, checkpoint history,
  list saves, show snapshots, list restore points.
allowed-tools: Bash, Read
user-invocable: true
---

# Checkpoints - List Saved Checkpoints

Display all saved checkpoints for the current project with their metadata.

## Usage

```
/checkpoints
```

No arguments required. Lists all checkpoints in the current project's `.claude/checkpoints/` directory.

## Execution Steps

### Step 1: Check for Checkpoint Directory

```bash
# Check if checkpoints exist
if [[ -d ".claude/checkpoints" && -f ".claude/checkpoints/index.json" ]]; then
    echo "Checkpoint directory exists"
else
    echo "No checkpoints found for this project"
fi
```

### Step 2: List Checkpoints

```bash
~/.claude/skills/checkpoint/scripts/checkpoint-manager.sh list
```

### Step 3: Format and Display Results

Present checkpoints in a readable format:

```
=== Checkpoints (5 total) ===

[2025-01-11] auth-refactor-completed
  ID: ckpt-20250111-143022-a1b2
  Summary: Completed authentication refactor with session handling

[2025-01-11] pre-database-migration
  ID: ckpt-20250111-120000-c3d4
  Summary: State before running database migrations

[2025-01-10] added-api-tests
  ID: ckpt-20250110-183045-e5f6
  Summary: Added comprehensive API endpoint tests

[2025-01-10] debugging-cache-issue
  ID: ckpt-20250110-142530-g7h8
  Summary: Investigating Redis caching problems

[2025-01-09] initial-setup
  ID: ckpt-20250109-090000-i9j0
  Summary: Project initialized with basic structure
```

## Output Format

For each checkpoint, display:

| Field | Description |
|-------|-------------|
| Date | When the checkpoint was created (YYYY-MM-DD) |
| Name | The checkpoint name (user-provided or auto-generated) |
| ID | Unique identifier for the checkpoint |
| Summary | Brief description of what was being worked on |

## Additional Details

To see full details of a specific checkpoint:

```bash
~/.claude/skills/checkpoint/scripts/checkpoint-manager.sh show <name-or-id>
```

This shows:
- Full metadata (name, timestamp, auto-generated flag)
- Context (working directory, notes)
- Git state (branch, SHA, uncommitted files)

## Example Interaction

**User:** `/checkpoints`

**Claude:** Let me list all saved checkpoints for this project.

```
=== Checkpoints (3 total) ===

[2025-01-11] added-user-validation
  ID: ckpt-20250111-154500-x1y2
  Summary: Implemented input validation for user registration form

[2025-01-11] pre-refactor-cleanup
  ID: ckpt-20250111-143522-c3d4
  Summary: Before major code cleanup and restructuring

[2025-01-10] initial-feature-branch
  ID: ckpt-20250110-091500-z3w4
  Summary: Started work on the new feature branch
```

**Available actions:**
- `/restore <name>` - Restore a specific checkpoint
- `/checkpoint` - Create a new checkpoint

## Empty State

If no checkpoints exist:

```
No checkpoints found for this project.

To create your first checkpoint, use: /checkpoint [name]
```

## Error Handling

- If `.claude/checkpoints/` doesn't exist: Show "no checkpoints" message
- If `index.json` is corrupted: Attempt to rebuild from individual checkpoint directories
- If project directory changed: Remind user that checkpoints are project-specific

## Notes

- Checkpoints are sorted by timestamp (newest first)
- Checkpoints are project-specific - each project has its own checkpoint history
- The checkpoint list shows a preview; use `/restore <name>` to see full details before restoring
