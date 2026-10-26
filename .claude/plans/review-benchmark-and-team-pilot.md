# Review benchmark and team pilot plan

Status: planned; implementation and company pilot deferred. Created 2026-10-25
from the workflow discussion against baseline `227f2b3` and the subsequent
review/readiness changes. The team's primary bottleneck is review; its stack is
Go, Python, and TypeScript.

## Problem and goals

The plugin has deterministic contract tests and native workflow/skill cases,
but no executed behavioral comparison demonstrating better software delivery.
The [current benchmark](../../evals/benchmarks/2026-10-25-skill-authoring-cleanup.md)
explicitly records zero runs per arm. Establish whether the workflow reduces
review effort and delivery time while preserving quality, and which components
justify their cost.

Do not claim improvement from schema checks, generated code volume, agent
agreement, or the number of review comments. This plan does not authorize
company data collection, model evaluations, infrastructure, or a rollout now.

## Scope and coordination

Extend [the existing evaluation conventions](../../evals/README.md) and coordinate
fixtures/CI with [the harness regression suite plan](harness-regression-suite.md).
Use the existing [review policy](../../references/review-policy.md) and
[readiness contract](../../references/project-readiness.md). Keep reproducible
environment provisioning in [its existing plan](reproducible-setup-and-unattended-execution.md).
Do not create a second evaluation platform or duplicate setup infrastructure.

## Implementation

1. **Agree on the decision and criteria.** With representative code owners and
   reviewers, select one or two services, task types, participants, and the
   quality requirements. Before seeing results, define what improvement would
   justify adoption and what would require revision. Assign an evaluation owner
   and an independent adjudicator; names remain to be chosen.

2. **Build a representative offline review set.** Select historical Go, Python,
   and TypeScript PRs with confirmed bugs and their fixes, plus reviewed clean
   changes. Include error/cancellation/concurrency paths, runtime API boundaries,
   cross-component changes, test/configuration changes, and ordinary fixes when
   these represent the company's work. Reconstruct the pre-fix change without
   revealing the fix to the reviewer. Code owners confirm triggers, locations,
   consequences, and expected findings. Keep unconfirmed candidate bugs distinct.
   Company source and raw traces stay in their approved internal location;
   only suitable sanitized fixtures/summaries enter this repository.

3. **Run a fair baseline comparison.** Compare a well-configured native agent
   against the streamlined plugin with the same model, source revisions,
   project guidance, tools, check commands, environment, and task inputs. Record
   intended differences between arms. Freeze criteria and candidate revisions;
   use tuning cases for changes and fresh holdout cases for final comparison.
   Run repeated trials and record failed/interrupted attempts. Evaluate advanced
   orchestration separately after the default workflow has a baseline.

4. **Score outcomes and inspect disagreements.** Measure detection against the
   confirmed bug set, false findings on reviewed clean cases, severity and
   location accuracy, actionable evidence, review rounds, human correction and
   adjudication time, latency, and total agent/CI cost. Report counts and
   denominators; known-bug recall is not recall over every possible defect.
   Humans adjudicate novel findings and disagreements without editing graders
   to make a candidate pass. Examine per-case wins/regressions and calibrate any
   model judge against human decisions.

5. **Run a small team pilot.** A practical starting point is four to six weeks,
   after a short baseline period and readiness checks in the selected services.
   Keep existing human review/merge rules. Classify task type, complexity, and
   risk before execution; compare similar work, including abandoned attempts.
   Use staggered rollout or randomized comparable tasks when feasible. Track
   active review effort separately from queue waiting, implementation effort,
   intervention/recovery effort, and time to an accepted PR and production.
   Record post-merge rework, reverts, escaped defects/incidents, and total spend.
   Add a short developer/reviewer survey about cognitive load and confidence
   explaining the change. Follow quality beyond the pilot because defects lag.

6. **Publish an honest internal decision.** Report medians/upper percentiles,
   sample sizes, task mix, repeated-run variability, model/CLI/plugin revisions,
   cost, failed attempts, and limitations. A small before/after pilot supplies a
   signal, not causal proof or evidence of rare-incident equivalence. Retain or
   remove components based on the observed tradeoffs. Save sanitized benchmark
   summaries under `evals/benchmarks/`, and keep private raw evidence in the
   agreed internal location. Feed confirmed misses/noise into new tuning cases.

## Verification and completion

- [ ] Each benchmark case has reproducible source/criteria and a human-reviewed
  bug label or clean-case assessment; withheld fixes are not available to agents.
- [ ] Baseline/candidate runs preserve equal inputs apart from intended workflow
  differences, with complete counts, cost, timing, and interrupted outcomes.
- [ ] Grader/runner tests cover missing evidence, false positives, stale source,
  timeouts, and errors; behavioral results remain separate from structural checks.
- [ ] Pilot criteria and quality requirements were agreed before measurement;
  review effort, waiting, rework, and production outcomes are reported separately.
- [ ] An internal report explains uncertainty and supports a concrete adoption,
  revision, or rejection decision without individual performance rankings.

## Open decisions

Service selection, owners, company data/tool policy, model budget, sample size,
baseline duration, and success thresholds require company input before execution.
Preparation might take several focused days after data access; pilot observation
and delayed quality follow-up take longer. No runs or company outcomes are
claimed by checking in this plan.

## Research inputs

- [Uber, 2026-08-27](https://www.uber.com/us/en/blog/efficient-software-factory/): real-work reviewer benchmarks, quality/noise, and cost per outcome.
- [Claude Code team, 2026-10-15](https://claude.dev/blog/solving-code-review-at-anthropic/): incident-derived evaluation cases and convergent review; observational team experience.
- [DORA measurement guidance](https://dora.dev/insights/measurement-frameworks/): combine delivery evidence and developer experience around a decision.
- [METR, 2026-02-24](https://metr.org/blog/2026-02-24-uplift-update/): task selection and concurrent-agent time measurement complicate productivity claims.
