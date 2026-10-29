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
| Tuning | `runtime-proof-regression`, `unavailable-runtime-proof` | Actual failing/fixed execution and honest missing-runtime handling |
| Tuning | `improvement-prepare`, `improvement-resume` | Saved comparison preparation, preserved requirements, and resuming a failed candidate without false acceptance |
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

The original cases need drafting/read tools. Runtime and improvement cases also
need reviewed scaffolds and Bash. Neither command invokes deployment infrastructure. See
[Skill Forge's eval reference](../skills/skill-forge/references/plugin-evals.md)
for native tools, graders, baseline interpretation, and cost limits, and the
[native documentation](https://code.claude.com/docs/en/plugin-evals) for CLI details.

## Controlled runs

Use `scripts/run-evals.py` to require a split, execution/judge selectors, cost
ceiling, concurrency one, both baseline arms, timeout, and local-only reports.
For a coding case, explicitly grant shell tools:

```bash
python3 scripts/run-evals.py --split tuning --case runtime-proof-regression \
  --model YOUR_EXECUTION_MODEL_ID --judge-model YOUR_JUDGE_MODEL_ID \
  --max-cost-usd 5 --runs 3 --shell
```

`--dry-run` writes the exact invocation with `NOT_RUN`; optional
`--not-run-reason` records an unavailable prerequisite or deliberate deferral.
Native auth is checked before paid calls. Final holdout also requires clean
source and `--frozen-revision` equal to the full HEAD SHA. Freeze success criteria
and graders independently before invoking it. Native cost limits stop new runs;
in-flight calls can overrun the estimate, so leave headroom under an allowance.

The runtime scaffolds use no third-party dependencies. Their graders combine
actual tool activity with a narrowly scoped trace assessment; an agent's PASS
file alone is insufficient. Deterministic tests prove the fixture detects its
known bug and accepts the fix. Until calibrated model runs exist, grader accuracy
and plugin uplift remain unmeasured. Five trials are an exploratory signal,
not proof of a general reliability percentage.

For knowledge ablations, compare the same task, model, tools, source, and
environment with one rule/skill changed, retaining all attempts. Keep alternative
plugin revisions in separate checkouts and use the same native runner, rather
than introducing another evaluation engine. Judge outcomes blind to the arm
when feasible; inspect failures and human correction effort as well as score.

The [improvement playbook](../skills/improve-workflow/SKILL.md) saves this
comparison's criteria, source references, evidence, decisions, and next action.
Its preparation/resume cases need `--shell` for their disposable Git scaffolds
and local verification. They do not launch nested model evaluations.

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
