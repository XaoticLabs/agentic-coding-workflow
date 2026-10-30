---
name: improve-workflow
description: "Prepare, compare, and resume measured improvements to agent instructions, skills, orchestration, or verification policy. Use for the improvement playbook, not ordinary product edits."
metadata:
  workflow-source: "skills/improve-workflow/SKILL.md"
---


# Improvement playbook

**Prepare → Compare → Decide.** `$ARGUMENTS` is an improvement idea,
`resume <id>`, or `status [id]`. Natural-language equivalents select the same
workflow. An idea starts preparation; implement the candidate only when that
work is authorized. A request for status is read-only.

Use `scripts/notebook.py` from this skill to start or discover records under
`${CLAUDE_PROJECT_DIR}/.claude/improvements/`. Resume the named record; with no
ID, inspect status and use the clearly relevant unfinished experiment. Ask only
when multiple records leave the intended work ambiguous. Keep `experiment.json`
as the canonical state and `report.md` as the readable result.

Read only the reference for the current step:

- **Prepare:** [prepare.md](references/prepare.md) establishes the hypothesis,
  protections, cases, baseline, and comparison plan before candidate edits.
- **Compare:** [compare.md](references/compare.md) selects existing runners and
  retains actual outcomes against equivalent inputs.
- **Decide:** [decide.md](references/decide.md) records keep/revise/reject and
  updates the baseline only when the agreed evidence supports keeping it.

On resume, read the record, linked evidence, and relevant current source. Check
that recorded revisions, criteria, and environment still apply before continuing.
For a missing or malformed record, report its path and error and preserve the
files; do not silently restart the experiment.
End each work session by updating `stage`, `next_action`, and `updated_at` and
reporting the record location. Preserve previous attempts and decisions.

Required verification and authorization remain in force. The notebook is
context, not a trusted approval or acceptance gate. Paid evaluations require a
concrete authorized budget; preparation and dry-run records can proceed without
model access. Missing runs are `NOT_RUN`, never inferred passes.

## Examples

```text
/agentic-coding-workflow:improve-workflow "Reduce context loaded by prime"
/agentic-coding-workflow:improve-workflow resume prime-context
/agentic-coding-workflow:improve-workflow status
```

You can also say: **“Use the improvement playbook for: <idea>.”**
