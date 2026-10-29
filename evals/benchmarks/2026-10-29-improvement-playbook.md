# Improvement playbook: initial evidence

Date: 2026-10-29. Base revision:
`346c055154fa217dd2fa165aedf312ec11175693`. Candidate is the working-tree
addition of `skills/improve-workflow/`, its notebook helper, preparation/resume
cases, and discovery documentation. No instruction-loading optimization or
verification-gate reduction is part of this candidate.

## Local evidence

- `make setup` synchronized the locked environment with uv 0.11.26.
- The notebook/scaffold tests exercise dirty source capture, nested project
  discovery, read-only status, restart without overwriting evidence, accepted
  baseline discovery without copying old results, invalid records, and path
  containment. The resume scaffold actually runs a passing baseline check and
  a failing candidate check, retaining both outputs.
- `validate-skill.py skills/improve-workflow --json` reported valid with no
  findings. This establishes structural compliance, not agent behavior.
- Run `make check` for the complete local gates. Its delivery proof retains
  the checked source and command results under `.claude/proofs/delivery/`.
  Deterministic checks do not establish a model outcome or turnaround benefit.

## Native comparison

| Evidence | Result |
| --- | --- |
| Native `claude plugin validate .` | NOT_RUN: Claude Code CLI is not installed in this environment |
| `improvement-prepare` model evaluation | NOT_RUN: CLI/model access unavailable; no evaluation budget selected |
| `improvement-resume` model evaluation | NOT_RUN: same prerequisite gap |
| Final holdout comparison | NOT_RUN: no candidate selection from tuning results or frozen final cases |
| Delivery speedup or review-quality improvement | Unmeasured |

Execution and judge models are unselected. Runs per native arm: zero. Model
spend: $0. No native reports or observed model IDs exist. The new prompts and
graders are tuning cases; authoring and exercising their scaffolds does not
validate the model judge or establish plugin uplift.

## Next comparison

With authenticated Claude Code and a concrete authorized allowance, use the
existing native runner with `--split tuning`, `--shell`, the chosen execution
and judge models, and `--case improvement-prepare` or `improvement-resume`.
Retain all attempts and compare the same case/fixture/grader versions across
current and candidate plugin revisions. The runner's no-plugin arm remains a
control; it is not an old-plugin revision comparison.

Freeze criteria and candidate before reserving and executing fresh holdout
cases. Retain later results as a new benchmark summary; do not replace this
record of unavailable native evidence. The initial `prime` latency experiment
must confirm actual duplicated guidance and capture baseline trials before
changing the priming behavior.
