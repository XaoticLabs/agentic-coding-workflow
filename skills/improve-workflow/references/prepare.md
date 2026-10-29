# Prepare

Start with one falsifiable hypothesis, such as: removing a duplicated guidance
copy reduces time to a verified result without losing project requirements.
Use `harness-audit` when the candidate itself needs investigation; its audit
does not authorize edits or model runs.

## Create or resume the notebook

From the consuming project, derive a descriptive ID and run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/improve-workflow/scripts/notebook.py" start prime-context --idea "Reduce context loaded by prime" --project-dir "${CLAUDE_PROJECT_DIR}"
```

`start` preserves an existing record. `status [id]` lists saved work and its next
action without writing. The helper records the starting source and discovers
the last kept baseline from `.claude/improvements/baseline.json`, when present.
It launches no checks, model calls, worktrees, or candidate edits.

Fill `plan` in `experiment.json` using relevant project guidance and evidence:

- **Hypothesis and success criteria:** what would justify keep, revise, or
  reject? Define the meaningful improvement and acceptable variability before
  inspecting results. Record correctness and required checks separately from
  speed. Avoid treating a small pilot as proof of rare-defect equivalence.
- **Protections:** requested behavior, required lint/test/product checks,
  selected optional modes, authorization boundaries, and honest completion.
- **Cases:** choose relevant tasks from [cases.md](cases.md), existing project
  cases, or real failures. Record IDs, tuning/holdout split, fixture/grader
  revision, input, and observable criteria. A new evaluation suite is optional.
- **Controls:** task starting source, tool/CLI versions, environment and
  dependencies, model/settings, and fresh/resumed/cache conditions. Distinguish
  the workflow revision being varied from the product fixture being held fixed.
- **Trial plan:** repetitions, order, timeouts, and authorized budget. Start with
  enough repeats to expose obvious variability and expand when the decision
  remains uncertain. Interleave baseline/candidate order when practical.

Use the current source as a provisional baseline when no accepted baseline
exists. An older accepted revision is a reference, not permission to reuse old
measurements with new cases, graders, models, or environments. Confirm the
appropriate baseline and capture its trials **before** candidate edits. A dirty
baseline needs its exact patch or preserved checkout as well as its fingerprint;
a hash alone cannot reconstruct it. Do not silently reset local changes.

Set `stage` to `baseline` and `next_action` to the next concrete operation.
Use [report.md](../assets/report.md) for a readable handoff; unavailable results
stay `NOT_RUN`. Keep raw evidence under ignored runtime directories and retain
sanitized final summaries under `evals/benchmarks/` for plugin changes.
