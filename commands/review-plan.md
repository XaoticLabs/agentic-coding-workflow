---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Agent
  - AskUserQuestion
---

# Plan Review — Staff Engineer Critique

Spawns a subagent with a "staff engineer" persona to critically review a plan document and surface gaps, risks, and improvements.

## Input

$ARGUMENTS - Either:
- A path to a plan document (e.g., `.claude/plans/feature-name.md`)
- A feature slug (e.g., `feature-name`) — will look in `.claude/plans/` directory
- Empty — will auto-detect from `.claude/plans/` directory

## Instructions

### Phase 1: Locate the Plan

**If a full path is provided:**
- Verify the file exists and read it

**If a slug is provided:**
- Look for `.claude/plans/<slug>.md`
- Fall back to `brainstorming/<slug>.md` for backward compatibility

**If no argument is provided:**
- List files in `.claude/plans/` directory
- If one plan exists, use it
- If multiple plans exist, ask the user which one to review
- If no plans found, check `brainstorming/` as fallback
- If nothing found, inform the user and exit

### Phase 2: Launch Review Subagent

Read the plan document, then spawn a subagent for review. This is ideal subagent territory — read-only analysis with structured output.

**Load the agent context:** Read `${CLAUDE_PLUGIN_ROOT}/agents/code-reviewer.md` for base review conventions, then extend with the staff engineer prompt below.

**Subagent prompt:**

> You are a staff engineer reviewing a feature plan before it goes to implementation spec. Your job is to be thorough and constructively critical — find what's missing, what's risky, and what could be better. You are NOT a yes-man.
>
> Here is the plan to review:
>
> [INSERT FULL PLAN CONTENT]
>
> **Review the plan across these dimensions:**
>
> ### 1. Feasibility
> - Is this technically achievable as described?
> - Are there hidden complexities the plan doesn't account for?
> - Are the technical decisions well-justified?
> - Read relevant codebase files to verify assumptions about existing patterns and systems.
>
> ### 2. Scope
> - Is the scope well-defined?
> - Are the non-goals actually non-goals, or are some of them things we'll be forced to do?
> - Is there scope creep hiding in the proposed solution?
> - Could the scope be reduced further while still delivering value?
>
> ### 3. Missing Considerations
> - What edge cases were missed?
> - What failure modes weren't considered?
> - Are there performance implications not discussed?
> - Are there observability/monitoring gaps?
> - What about data migration or backward compatibility?
>
> ### 4. Architecture Gaps
> - Does the proposed architecture fit the existing system?
> - Are there better patterns to use?
> - Are the integration points well-understood?
> - What about scalability concerns?
>
> ### 5. Risk Assessment
> - Are the identified risks complete?
> - Are the mitigations realistic?
> - What's the actual blast radius if this goes wrong?
> - Is there a rollback story?
>
> ### 6. Alternative Approaches
> - Were the right alternatives considered?
> - Is there a simpler approach that was overlooked?
> - Would a phased rollout be better than a big-bang release?
>
> ### 7. Open Questions
> - Are the open questions the right ones?
> - Are there critical questions that should be answered before implementation starts?
> - Which open questions are actually blockers vs. nice-to-know?
>
> **Output format:**
>
> ```markdown
> # Plan Review: [Feature Name]
>
> > Reviewed on [date]
> > Plan: [path to plan file]
>
> ## Overall Assessment
> [1-2 paragraph summary: is this plan ready for implementation spec, or does it need more work?]
>
> ## Strengths
> - [What the plan does well]
>
> ## Critical Issues (Must Address)
> - [Issue 1: description and recommendation]
> - [Issue 2: description and recommendation]
>
> ## Suggestions (Should Consider)
> - [Suggestion 1: description and trade-off]
> - [Suggestion 2: description and trade-off]
>
> ## Minor Notes
> - [Nit 1]
> - [Nit 2]
>
> ## Verdict
> [ ] Ready for `/agentic-coding-workflow:write-spec`
> [ ] Needs minor revisions — update plan and proceed
> [ ] Needs significant rework — revisit with `/agentic-coding-workflow:plan`
> ```

### Phase 3: Present Review

Display the subagent's review to the user. If the review identifies critical issues, suggest running `/agentic-coding-workflow:plan` again to address them. If the plan is ready, suggest proceeding with `/agentic-coding-workflow:write-spec`.

## Important Constraints

- **This is a read-only command** — no files are written
- **The subagent must read codebase files** — reviews grounded in the actual code are far more valuable
- **Be constructively critical** — the goal is to improve the plan, not to block progress
- **Don't re-brainstorm** — the review critiques the plan, it doesn't redo the planning

## Example Usage

```
/agentic-coding-workflow:review-plan feature-name
/agentic-coding-workflow:review-plan .claude/plans/batch-analysis.md
/agentic-coding-workflow:review-plan
```

## Error Handling

- If no plans found in `.claude/plans/` or `brainstorming/`, inform user and suggest running `/agentic-coding-workflow:plan` first
- If the plan document is empty or malformed, flag it and suggest regenerating
