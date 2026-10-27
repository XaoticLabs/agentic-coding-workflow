# Graph engineering in this workflow

Graph engineering means choosing work boundaries, routing rules, shared state,
and verification for a system of agents and deterministic tools. Use the term
as a design discipline, not a reason to create a graph for every task.

Start with one continuing session. Add a boundary when independent work,
different capabilities, limited context, a separate verifier, or enforced
recovery makes that boundary useful. A node should have a cohesive responsibility;
it need not be split merely because its description contains two verbs. A test
runner is a process, not a language model impersonating a test runner.

## Three distinct graphs

1. **Task dependencies:** which accepted outcomes must precede other tasks.
   The existing task-plan parser validates this DAG.
2. **Execution states:** implement, check, review, integrate, accept, or stop.
   Repair edges make this a bounded state machine, not a DAG. Relay enforces it.
3. **Evidence relationships:** a criterion is supported by a command result,
   source revision/fingerprint, runtime artifact, and independent review.
   Evidence describes what was observed; model confidence does not create proof.

Keep them distinct. A completed plan checkbox is not an accepted execution
state, and an accepted execution state is not a deployment record.

## Choosing an edge

Use code for dependency eligibility, scope rules, retry/time limits, ownership,
and acceptance conditions. Use generative models for implementation and contextual
review. Use decision models such as Jev/Laya for narrow, evaluated classifications
when rules cannot settle them. [Decision-model integration](decision-models.md)
begins in observation mode: classifications do not route fixes or relax gates.

Each handoff names the input, allowed output, owner, source version, failure
behavior, and verification. Give a node the slice it needs, with evidence paths
for deeper inspection. Each worker owns one worktree; one controller updates
canonical state; integration is serialized. Propagate cancellation and budgets
through every path. An escalation is an incomplete result with evidence, not
another kind of success.

## Applying the supplied CI-triage article

The useful design is `classify -> investigate/repair -> verify -> independent
review -> delivery`, with explicit escalation, versioned evidence, and bounded
repair. Relay implements the repair/verification core. It does not silently
install a scheduled CI bot, manipulate secrets, file remote issues, or send
Slack messages. Delivery, provider events, and schedules stay in their existing
owners and require the corresponding requested scope.

Corrections that matter in implementation:

- Markdown role rules and `allowed-tools` prompt-free grants are not hard tool
  restrictions. Actual tool selection/denies and externally enforced process,
  filesystem, and network boundaries provide different levels of isolation.
- Simulating specialists sequentially in one conversation does not provide
  isolated context windows or independent evaluation. Separate processes do.
- A passing retry is evidence of intermittency, not proof of a harmless flake.
  Keep the original failure and investigate; do not auto-close or merge from it.
- A test's zero exit is evidence for that configured test, not a proof of the
  entire requirement. Preserve raw results, source identity, scope checks, and
  review of verification changes. Gate coverage must itself be maintained.
- The Anthropic 90.2% result concerns its research system and benchmark; it is
  not a measured coding-quality improvement for this repository. Its article
  also describes increased token use. Do not generalize it or promise routing
  halves cost without workload-specific comparisons.
- `/goal` evaluates surfaced conversation evidence and does not independently
  execute tests. `/loop` and cloud scheduling have different lifecycles. A
  written schedule or prompt is not an activated automation.
- No first-use date or universal five-pattern taxonomy is required by this
  implementation. Apply useful routing, chaining, parallelism, and review where
  they reduce a demonstrated bottleneck.

## Borrowing from pstack and gstack

Pstack contributes useful patterns for scoped briefs, one writer per branch,
observable verification, and durable handoffs. Gstack contributes useful
runtime QA and developer-experience audits. Adopt those capabilities through
the existing verification and delivery contracts rather than installing two
competing top-level workflow policies or duplicating supervisors.

The local `verify-project` skill and `runtime-verifier` role make real user
paths executable and reviewable. `devex-review` exercises developer journeys;
`test-audit` proposes evidence-backed test improvements without deleting checks.
For onboarding, have someone other than the
author follow the three recipes in README from a fresh checkout; retain failed
steps and improve the canonical instructions. Audit tests for the observable
failure they protect, preserving useful contract tests. Removal based solely on
test count, source-grep use, or code size is not an engineering result.

## Evidence before optimization

Compare the native-session baseline with Relay on representative tasks, using
the same model, source, environment, tools, and criteria. Record accepted
behavior, false acceptance/rejection, failed attempts, human correction effort,
latency, and total cost. Evaluate decision classification separately from coding
quality. Use [existing evaluations](../evals/README.md) and
[experiments](experiments.md); there is no new benchmark platform.

Sources: [Anthropic multi-agent research](https://www.anthropic.com/research/multi-agent-research-system),
[Claude subagent capabilities](https://code.claude.com/docs/en/sub-agents),
[native goals](https://code.claude.com/docs/en/goal),
[pstack](https://github.com/cursor/plugins/tree/main/pstack),
[gstack](https://github.com/garrytan/gstack).
