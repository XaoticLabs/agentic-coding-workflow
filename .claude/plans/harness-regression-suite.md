# Harness regression suite plan

Status: planned. Baseline: `0fe760a`, reviewed 2026-10-25.

Finish the checked-in regression suite so changes to commands, hooks, and
workflows have reproducible evidence of correctness. Estimated remaining effort
is **12–24 focused hours, roughly 2–3 working days**. Allow another 1–2 days if
evaluations expose harness bugs requiring fixes. This plan records future work;
paid evaluations remain deferred.

## Current coverage

- [Nine test modules](../../tests/) cover command parsing, dependency graph
  validation, hook decisions, pipeline failures, cleanup preservation, and
  retained reports and traces. Map these to the requirements and fill gaps.
- [CI](../../.github/workflows/tests.yml) already runs pytest and hook validation
  on pushes and pull requests.
- [Six native eval cases](../../evals/) cover skill creation, a skill selection
  near-miss, native session launch and resume, and workflow advice. Several grade
  explanations; actual coding completion needs additional fixtures.
- [Local report handling](../../.gitignore) already ignores `evals/results/`.
  The documented eval command uses `--no-publish`, but has no cost ceiling.

## Implementation

1. **Audit and extend deterministic coverage — 2–4 hours.** Map each requirement
   to existing assertions. Fill concrete gaps using temporary projects, local
   Git repositories, and stubbed CLI processes. Check malformed commands,
   dependency cycles and missing dependencies, hook allow/block decisions,
   producer/consumer failures and timeouts, preservation of unfinished work,
   and delivery of complete artifacts after cleanup. Keep these tests free of
   model calls and external services.

2. **Add behavioral evals — 6–10 hours.** Use small fixture projects and concrete
   graders for task completion, correct skill selection, unnecessary questions,
   scope drift, and verification honesty. Include appropriate non-selection and
   clarification cases. Exercise real file changes and deliberately failing or
   unavailable checks. Compare completion and verification claims with files,
   tool activity, and captured command results. Prefer deterministic graders
   for observable facts and narrow model rubrics for judgment. Include known
   bad outcomes to confirm graders detect failures.

3. **Add a controlled eval entry point — 2–4 hours.** Use native
   `claude plugin eval` where available. Check the supported CLI version,
   required options, credentials, and sandbox prerequisites; report unavailable
   prerequisites clearly. Require an explicit cost ceiling, pin agent and judge
   models, and set turn/time limits. Default to concurrency one and
   `--no-publish`; retain JSON and HTML under ignored `evals/results/`. Treat
   partial runs and skipped paid graders as incomplete. Keep paid evals manually
   triggered initially; run deterministic checks on every PR.

4. **Calibrate and document results — 2–6 hours.** Iterate with one trial and
   `--ablation none`, then confirm with three trials per arm and a no-plugin
   baseline. Record model versions, cost, duration, failures, and outcome
   differences. Check skill invocation separately from task success. Establish
   thresholds from observed results before making paid evals a required gate.

## Cost and execution constraints

The documented minimum is Claude Code v2.1.269 with model access; recheck support
when implementation starts. The current environment has no `claude` on PATH.
Native evals isolate agent runs, but plugin hooks and fixture scaffold scripts
run outside that sandbox. Use disposable fixtures and an isolated runner for
cases that execute hooks or shell commands.

`--max-cost-usd` stops new runs after the estimated ceiling is reached; active
runs can exceed it. Turn/time limits and low concurrency help bound exposure.
Measure a small pilot before choosing recurring budgets.

## Completion criteria

Every requested behavior maps to a checked-in test or eval with an observable
pass condition. Deterministic checks pass in CI, behavioral graders reject known
bad outcomes, and repeated trials produce local reports with explicit budgets
and baseline comparisons. Document remaining failures and variability alongside
the evidence; partial runs cannot establish success.

Reference: [Claude Code plugin evaluations](https://code.claude.com/docs/en/plugin-evals).
