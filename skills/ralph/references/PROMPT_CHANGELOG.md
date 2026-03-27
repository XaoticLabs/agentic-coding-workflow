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

### 2026-03-26 — PROMPT_evaluate.md — Initial evaluator prompt

**Changed:** Created new evaluation prompt with 5 grading dimensions, hard thresholds, LLM code smell detection, and structured JSON verdict output. Supports two modes: END-OF-RUN (default, advisory report) and PER-ITERATION (opt-in, can trigger reverts).
**Intended effect:** Independent quality assessment that catches issues self-evaluation misses. End-of-run mode is default per Anthropic findings that per-iteration eval is unnecessary overhead for tasks within the model's comfort zone (Opus 4.6). Per-iteration mode available for edge-of-capability tasks where evaluator gives real lift.
**Observed effect:** (pending — first runs needed)
**Model:** Sonnet (default evaluator model)
**Evidence:** N/A — initial creation

### 2026-03-26 — PROMPT_contracts.md — Initial contract generation prompt

**Changed:** Created sprint contract prompt that generates measurable acceptance criteria per task.
**Intended effect:** Give the evaluator specific, binary criteria to grade against instead of vague spec language. Reduce evaluator drift by anchoring to concrete observables.
**Observed effect:** (pending — first runs needed)
**Model:** Sonnet (default)
**Evidence:** N/A — initial creation

### 2026-03-26 — PROMPT_plan.md — Added AI feature opportunity identification

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
| ">100 lines added" check | PROMPT_build.md | Triggers self-review but threshold may be too high/low for some projects | Pre-changelog |
| "No praise" | PROMPT_evaluate.md | (pending observation) | 2026-03-26 |
| "museum quality" equivalent | N/A | Known from Anthropic article to cause visual convergence — avoid aspirational superlatives in criteria | External finding |

## Maintenance

- **After any prompt edit**: Add a changelog entry before committing
- **After a Ralph run**: Fill in "Observed effect" for recent entries using journal/evaluator data
- **During harvest mode**: The harvest prompt should check this file and update observed effects based on run data
