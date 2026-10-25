# Prompt Changelog

Tracks revisions to Ralph prompt templates, their intended effects, and observed behavioral impact. Prompt wording has unexpected steering effects — this log captures what we've learned.

## Why This Exists

The Anthropic harness design article found that "phrases like 'the best designs are museum quality' steered the generator in ways I didn't fully anticipate." Prompt changes can have non-obvious downstream effects. This changelog helps track cause and effect across prompt revisions.

## Format

Each entry follows this structure:

```markdown
### <date> — <prompt file> — <short description>

**Changed:** <what was added/removed/modified>
**Intended effect:** <what we expected to happen>
**Observed effect:** <what actually happened — fill in after running>
**Model:** <which model this was tested with>
**Evidence:** <journal data, evaluator scores, or qualitative observation>
```

---

## Changelog

### 2026-10-25 — PROMPT_build.md / PROMPT_evaluate.md — Contextual maintainability review

**Changed:** Replaced compression scoring with maintainability in prompts and the evaluator schema. Removed shortest-program, deletion-ratio, lines-per-criterion, and single-use inlining incentives. Updated calibration, interactive implementation, and language review guidance; removed the Python function-length warning. Ralph no longer imposes a default file-count rejection limit or a file-count filter on enabled quality review. Optional workload-specific size thresholds require our own evaluation evidence.
**Intended effect:** Keep changes focused while crediting readable decomposition, necessary validation, and legitimate greenfield work. Require concrete maintenance costs and behavior-preserving corrections rather than size-based penalties.
**Observed effect:** Pending — no live model run performed; no workload-specific size threshold has been validated by this revision.
**Model:** N/A — controller and hook regressions use deterministic fixtures and a fake CLI.
**Evidence:** Regressions cover the maintainability schema, actionable revision results, optional scope limits captured before the build, and retained Python validation warnings without length penalties. Model review quality remains unmeasured.

### 2026-10-25 — PROMPT_build.md / PROMPT_evaluate.md — Review verification integrity

**Changed:** Replaced RED-commit file freezes with preserved acceptance criteria, provenance for human-approved expectations, justified test corrections, and mandatory independent integrity review for every committed build iteration. RED/GREEN commits are optional; the controller retains original verification inputs and supplies intermediate patches. Nonzero checks cannot be ignored into success.
**Intended effect:** Allow legitimate case additions and mistaken-test/fixture corrections while rejecting coverage weakening, invented approval, and verification bypasses.
**Observed effect:** Pending — no live model run performed.
**Model:** N/A — controller regressions use a fake CLI.
**Evidence:** Automated controller/evaluator regression tests; semantic review effectiveness requires observation in real runs.

### 2026-10-25 — PROMPT_build.md / PROMPT_plan.md — Task-based delegation

**Changed:** Replaced mandatory exploration subagents with direct reads for a few relevant files, delegation for independent investigations with overwhelming intermediate output, parallel work with clear interfaces, and independent verification when its expected benefit justifies its cost. Build placement now depends on tools, permissions, turn budget, isolation, and oversight.
**Intended effect:** Reduce unnecessary model calls and handoffs for trivial lookups while retaining useful delegation and verification.
**Observed effect:** Pending — no Ralph run performed for this revision.
**Model:** N/A — prompt-only change
**Evidence:** Static prompt review and the [Claude subagent reference](https://code.claude.com/docs/en/sub-agents); runtime cost and quality effects remain unmeasured.

### 2026-03-26 — PROMPT_evaluate.md — Initial evaluator prompt

**Changed:** Created new evaluation prompt with 5 grading dimensions, hard thresholds, LLM code smell detection, and structured JSON verdict output. Supports two modes: END-OF-RUN (default, advisory report) and PER-ITERATION (opt-in, can trigger reverts).
**Intended effect:** Independent quality assessment that catches issues self-evaluation misses. End-of-run mode is default per Anthropic findings that per-iteration eval is unnecessary overhead for tasks within the model's comfort zone (Opus 4.6). Per-iteration mode available for edge-of-capability tasks where evaluator gives real lift.
**Observed effect:** (pending — first runs needed)
**Model:** Sonnet (default evaluator model)
**Evidence:** N/A — initial creation

### 2026-03-26 — PROMPT_contracts.md — REMOVED (sprint contracts dropped)

**Changed:** Deleted PROMPT_contracts.md and the entire contracts mode. Acceptance criteria now live inline in each task in IMPLEMENTATION_PLAN.md, generated by the planner. Evaluator updated to grade against plan criteria instead of a separate CONTRACTS.md file.
**Intended effect:** Simplify the harness per Anthropic's harness design findings — with Opus 4.6, the separate contract negotiation step is redundant scaffolding. The planner can produce concrete acceptance criteria directly, eliminating an entire Claude invocation from the pipeline.
**Observed effect:** (pending — first runs needed)
**Model:** N/A — removal
**Evidence:** Anthropic engineering blog "Harness Design for Long-Running Apps" — V2 (Opus 4.6) dropped sprints/contracts, moved to single end-of-run evaluation, cut runtime by ~40% and cost by ~40%.

### 2026-03-26 — PROMPT_plan.md — Added inline acceptance criteria + AI feature opportunity identification

**Changed:** Added Step 5 instructing the planner to scan specs for AI feature opportunities and plan them with explicit tool definitions, system prompts, and guardrails. Based on Anthropic finding that generators need explicit architectural guidance for building AI agents into apps, since training data coverage is thin.
**Intended effect:** When specs include AI features, the planner produces tasks with enough specificity for the generator to build proper agents with tools, not vague "add AI" placeholders.
**Observed effect:** (pending — first runs needed)
**Model:** Sonnet (default planner model)
**Evidence:** N/A — initial creation

### 2026-03-26 — PROMPT_build.md — (no changes)

**Note:** Existing build prompt unchanged. Future revisions should be tracked here. Key steering phrases to watch: "One task per iteration", "Never give up", "Must test", simplicity check thresholds (>100 lines, >5 files).

---

## Known Steering Effects

Document prompt phrases with observed behavioral impact:

| Phrase | Prompt | Effect | First Observed |
|--------|--------|--------|----------------|
| "One task per iteration" | PROMPT_build.md | Prevents scope creep but may cause artificial task splitting | Pre-changelog |
| "Never give up" | PROMPT_build.md | Reduces no-commit iterations but may cause thrashing on impossible tasks | Pre-changelog |
| ">100 lines added" check (retired) | PROMPT_build.md | Historical size heuristic; no workload evaluation evidence recorded. Replaced by contextual maintainability review | Pre-changelog |
| "No praise" | PROMPT_evaluate.md | (pending observation) | 2026-03-26 |
| "museum quality" equivalent | N/A | Known from Anthropic article to cause visual convergence — avoid aspirational superlatives in criteria | External finding |

## Maintenance

- **After any prompt edit**: Add a changelog entry before committing
- **After a Ralph run**: Fill in "Observed effect" for recent entries using journal/evaluator data
- **During harvest mode**: The harvest prompt should check this file and update observed effects based on run data
