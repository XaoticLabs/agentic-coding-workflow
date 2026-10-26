# Behavioral evaluation cases and evidence

Use native `claude plugin eval` for manual comparison and iteration. The runner
creates local HTML and JSON reports.
Standards validation checks syntax, schema, and resource availability.
Behavioral evaluation checks task outcomes and the plugin's contribution
relative to the no-plugin baseline. Report these separately.

## Case splits

Each case has exactly one split tag, `tuning` or `holdout`, alongside its topic
tags. Existing cases are tuning evidence because they have already informed
the workflows. The reserved holdout cases have not been run; authoring them
does not establish that they represent unseen real-world tasks.

| Split | Cases | Intended coverage |
| --- | --- | --- |
| Tuning | `skill-forge-small-skill`, `skill-forge-near-miss` | Self-contained skill creation and ordinary prose near-miss |
| Tuning | `native-goal-workflow`, `spawn-native-goal`, `spawn-native-worktree`, `resume-feature-session` | Workflow selection, native isolation, goals, and session continuity |
| Tuning | `ticket-cli-api-routing`, `delivery-follow-up` | CLI/API ticket identity, explicit fallback, and bounded PR feedback handling |
| Holdout | `skill-forge-repair-skill` | Repair evidence handling and missing-fact behavior while preserving invocation policy |
| Holdout | `skill-forge-explicit-deploy` | Draft a manually invoked deployment workflow without executing it |

Tune descriptions, instructions, and graders using only tuning cases. Freeze
the candidate revision, case/graders revision, and acceptance criteria before
the final holdout run. Record all outcomes; never choose a description or
candidate by holdout score. Do not run the unfiltered suite while tuning.

If a holdout outcome informs an edit, record that the set is consumed and retag
it as tuning. Reserve fresh cases before another final comparison. Do not
silently revise holdout graders to accept a failing candidate. A public,
versioned holdout is reproducible but cannot be treated as permanently unseen.

From the trusted plugin checkout, with Claude Code v2.1.269 or later and model
access, choose the appropriate split:

```bash
claude plugin eval . --tag tuning --allow-tools Write Edit --no-publish
claude plugin eval . --tag holdout --allow-tools Write Edit --no-publish
```

These cases need file drafting and read tools, not shell execution. Neither
command invokes deployment infrastructure. See
[Skill Forge's eval reference](../skills/skill-forge/references/plugin-evals.md)
for native tools, graders, baseline interpretation, and cost limits, and the
[native documentation](https://code.claude.com/docs/en/plugin-evals) for CLI details.

## Retaining benchmark evidence

Commit representative prompts, fixtures, graders, and sanitized benchmark
summaries under `evals/benchmarks/`. Raw reports and transcripts remain local
under ignored `evals/results/`. Before removing a disposable run workspace,
retain useful failure evidence and the summary; never remove the case suite
or benchmark history as cleanup. Do not commit credentials or private input.

A benchmark summary records:

- Candidate and case/graders revisions, date, exact command, CLI version,
  execution and judge models, run count per arm, and split status.
- Per-case outcome pass counts for both plugin and baseline arms, their
  difference, triggering diagnostics separately, estimated cost, and duration.
- Failures, incomplete or interrupted runs, retained evidence locations, and
  limitations. A missing run is `NOT_RUN`, never a zero or an inferred pass.
- Standards diagnostics, native validation, and deterministic repository tests
  separately from model outcome comparisons.

Freeze any threshold or selection rule on tuning evidence before holdout.
Preserve earlier summaries when adding new results so comparisons remain
reviewable. A passed standards check alone supports no claim of improved
behavior. The initial summary records unavailable native runs explicitly.
