---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Write
  - Agent
effort: medium
---

# Harness Audit — Inventory, Stress-Test, and Simplify

Every component in a harness encodes an assumption about what the model can't do on its own. Those assumptions go stale as models improve. This command inventories all harness components, documents their assumptions, and suggests simplification experiments.

## Input

$ARGUMENTS - Optional:
- `(empty)` — full audit of all harness components
- `--focus <component>` — audit a specific component (e.g., `evaluator`, `gates`, `struggle-detection`)
- `--model <model>` — note the model under evaluation (default: shared model policy)

## Phase 1: Inventory All Harness Components

Scan the plugin to catalog every component that shapes autonomous behavior. For each, document:

1. **Component name and location** (file:line)
2. **What it does** (one sentence)
3. **What assumption it encodes** — why does this exist? What model limitation does it compensate for?
4. **When it was last tuned** — check git blame for last modification date
5. **Model it was tuned for** — use recorded model provenance; label missing evidence unknown

### Components to Inventory

**Quality Gates** (in `loop.sh`):
- Test gate — runs test suite after each iteration
- Lint gate — runs linter after each iteration
- Optional scope limit — disabled by default; inspect workload-specific evaluation evidence for any configured `RALPH_MAX_DIFF_FILES` limit
- Protected files gate — blocks modifications to specified files
- Verification integrity review — preserved criteria, approved expectations, justified corrections, and protection against bypasses

**Safety Mechanisms** (in `loop.sh`):
- Struggle detection — stops after N retries on same task
- Circuit breaker (soft) — warns at low commit ratio
- Circuit breaker (hard) — stops on consecutive reverts across different tasks
- Plan integrity check — verifies completed task commits exist
- Time budget — per-iteration timeout

**Evaluation System** (evaluator phase):
- Tiered evaluation thresholds — when to run light vs full eval
- Evaluator scoring dimensions and thresholds
- Plan acceptance criteria — measurable done criteria inline in plan tasks
- Calibration reference — scored examples and smell detection

**Prompt Engineering**:
- PROMPT_build.md — build iteration instructions
- PROMPT_evaluate.md — evaluation instructions
- PROMPT_plan.md — planning instructions
- PROMPT_harvest.md — pattern extraction instructions
- PROMPT_reconcile.md — post-merge verification
- PROMPT_resolve.md — conflict resolution

**Context Management**:
- Native compaction/resume in ordinary continuing feature sessions
- Ralph's specialized fresh workers and generated briefings
- Learnings section — actionable rules in plan
- Overrides — persistent cross-run rules
- Mid-loop injection — one-shot steering

**Hooks** (from `hooks/hooks.json`):
- Each registered hook with its trigger event and purpose

## Phase 2: Analyze Assumptions

For each component, classify the assumption:

| Classification | Meaning | Action |
|---------------|---------|--------|
| **Load-bearing** | Removing this would likely degrade output quality | Keep, but schedule periodic retest |
| **Possibly stale** | Newer models may handle this natively | Design A/B experiment |
| **Defensive only** | Prevents rare catastrophic failure, low ongoing cost | Keep as safety net |
| **Likely redundant** | Multiple components serve the same purpose | Candidate for removal |

Use these as investigation leads, not removal evidence:
- A model upgrade makes compensating instructions candidates for retesting.
- Overlapping checks can catch different failure modes; measure their added value.
- A gate that never triggered may be rare-event protection or simply unexercised.
  Inspect coverage and consequences before classifying it.

## Phase 3: Design Simplification Experiments

For each "possibly stale" or "likely redundant" component, propose an A/B test:

```markdown
### Experiment: Remove <component>

**Hypothesis:** <Model X> can handle <what the component compensates for> natively.

**Test design:**
- Use the same representative tasks, model, tools, environment, and criteria in both arms
- Run repeated trials WITH the component (control) and WITHOUT it (treatment)
- Keep judges blind to the arm when feasible; retain failed/interrupted attempts
- Compare behavioral completion, missed defects, interventions, time, total cost, and reverts

**Risk if wrong:** <what happens if the component IS still needed>

**How to run:**
- Control: `ralph <slug>` (default)
- Treatment: `RALPH_<FLAG>=false ralph <slug>` or edit loop.sh

**Metrics to compare:**
- Commit ratio (kept/total iterations)
- Evaluator scores (if using full evaluation)
- Diff size distribution
- Time per iteration
```

Use the existing `evals/` split/retention policy and `scripts/run-evals.py` for
controlled native comparisons. Five trials can be an exploratory starting point,
not a reliability estimate. A single-rule ablation needs separate frozen plugin
revisions and identical cases. Paid runs require an explicit cost ceiling;
this audit proposes experiments and does not authorize their execution.

## Phase 4: Check for Missing Components

Check which capabilities the workload actually needs and what evidence supports them:

- [ ] Separated evaluation from generation (evaluator agent)
- [ ] Inline acceptance criteria in plan tasks
- [ ] Evaluator calibration (few-shot examples with scores)
- [ ] Active feature exercising (not just code review)
- [ ] Prompt steering awareness (tracking how prompt wording affects output)
- [ ] Harness simplification protocol (this audit itself)
- [ ] Tiered evaluation (light vs full based on task complexity)

## Phase 5: Write Audit Report

Write the report to `.claude/harness-audit-<date>.md`:

```markdown
# Harness Audit — <date>

## Summary
- Total components: N
- Load-bearing: N
- Possibly stale: N
- Defensive only: N
- Likely redundant: N

## Component Inventory
(table with all components, classifications, last tuned date, model)

## Simplification Experiments
(proposed A/B tests for stale/redundant components)

## Missing Components
(checklist of recommended additions)

## Recommendations
1. (prioritized list of changes)
```

## Error Handling

- If no Ralph runs have been completed (no journal/trace data), note that some analysis requires run data and limit to structural audit only
- If hooks.json doesn't exist, skip hooks section

## Example Usage

```
/agentic-coding-workflow:harness-audit
```
Full audit of all harness components.

```
/agentic-coding-workflow:harness-audit --focus evaluator
```
Focused audit of the evaluation system only.

```
/agentic-coding-workflow:harness-audit --model <team-selected-model-id>
```
Audit against the selected model's recorded behavior; missing runs remain unmeasured.
