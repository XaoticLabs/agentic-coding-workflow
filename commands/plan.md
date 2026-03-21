---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash
  - AskUserQuestion
  - Task
  - WebFetch
  - EnterPlanMode
  - ExitPlanMode
  - mcp__claude_ai_Linear__*
---

# Feature Planning Partner

A unified planning command that combines brainstorming and plan formation into a single interactive session. Produces a comprehensive plan document that feeds directly into `/write-spec`.

## Input

$ARGUMENTS - Either:
- A Linear ticket ID (e.g., `AI-1234`)
- A feature description string (e.g., `"batch conversation analysis"`)
- A path to existing prime-context (e.g., `prime-context/context.md`)

## Instructions

### Phase A: Plan Mode (Read-Only Interactive Session)

**Enter Plan Mode immediately:**
Call `EnterPlanMode` before any interactive work. All questioning, analysis, and plan formation happens in read-only mode.

#### Step 1: Load Context

**Auto-load prime context if available:**
- Check if `prime-context/context.md` exists — if so, read it and use as background context
- If the input is a path to a context file, read that instead

**If the input looks like a ticket ID** (pattern: letters-numbers like "AI-1234", "COMMS-567"):
- Use the Linear MCP tool to fetch the ticket details
- Extract: title, description, acceptance criteria, any linked tickets
- Use this as the starting point

**If the input is a feature description:**
- Use the description as-is for the starting point

#### Step 2: Iterative Refinement (The Core Loop)

This is NOT a one-and-done questionnaire. You are a thinking partner who keeps probing until the feature is crystal clear. Use AskUserQuestion repeatedly to dig deeper.

**Start with the problem space:**
- What specific problem are we solving?
- Who exactly experiences this problem? (Be specific — not "users" but which users, in what context)
- Why does this matter now? What's the cost of not solving it?
- How are users currently working around this problem?

**Challenge and push back:**
- Play devil's advocate — question whether this feature is even needed
- Ask "what if we did nothing?" and make them justify the investment
- Suggest simpler alternatives and see if they'd work
- Push back on scope creep — ask "is that really part of this feature?"
- Question assumptions — "you said X, but have you validated that?"

**Explore the happy path:**
- Walk through the ideal user journey step by step
- What does success look like?
- How will users discover this feature?
- What's the simplest possible version that delivers value?

**Dig into edge cases (surface at least 5):**
- What happens when things go wrong?
- What if the user has no data? Too much data?
- What about concurrent users/operations?
- What about permissions/authorization edge cases?
- What if external dependencies are unavailable?
- What about backward compatibility?
- What about internationalization/localization?
- What about mobile vs desktop?

**Probe integration points:**
- What existing systems does this touch?
- What APIs need to change?
- What data needs to flow where?
- What are the system boundaries?

**Explore failure modes:**
- What can go wrong?
- How do we recover from failures?
- What's the blast radius of a bug here?
- What monitoring/alerting do we need?

**Security considerations:**
- What data is involved? PII? Sensitive?
- Who should have access? Who shouldn't?
- What's the threat model?
- What could an attacker do with this feature?

**Define scope boundaries:**
- What is explicitly NOT part of this feature?
- What's being deferred to future work?
- What adjacent features are we NOT building?

#### Step 3: Implementation Approach

After the problem and solution are well-defined, shift to technical planning:

**Recommended pattern:**
- What architectural pattern fits best?
- Are there existing patterns in the codebase to follow?
- Read relevant codebase areas to ground decisions in reality

**Key technical decisions:**
- What are the major decision points?
- What are the trade-offs for each?
- What's the recommended choice and why?

**Rough task breakdown:**
- What are the major chunks of work?
- What's the dependency order?
- What can be parallelized?
- What's the riskiest part?

#### Step 4: Synthesis Check

Before generating the document, verify:
- Have you asked at least 3 rounds of questions?
- Have you identified at least 5 edge cases?
- Have you pushed back on at least 2 assumptions?
- Have you explored at least one simpler alternative?
- Are the scope boundaries clear?
- Is the implementation approach grounded in the actual codebase?

If not, go back to Step 2 and keep probing.

### Phase B: Write Mode (Document Generation)

**Exit Plan Mode:**
Once the user confirms the plan is solid, call `ExitPlanMode` to enable writing.

**Use extended thinking** to synthesize everything discussed into a comprehensive document.

**Create the output directory** if it doesn't exist:
```bash
mkdir -p .claude/plans
```

**Generate a slug** from the feature name (lowercase, hyphens, no special chars).

**Write the document** to `.claude/plans/<feature-slug>.md` with this structure:

```markdown
# Plan: [Feature Name]

> Generated from planning session on [date]
> Source: [ticket ID if applicable]

## Problem Statement

[Clear articulation of the problem being solved]

### Who experiences this?
[Specific user personas and contexts]

### Why now?
[Business/user motivation for solving this]

### Current workarounds
[How users cope today]

## Goals

- [Specific, measurable goal 1]
- [Specific, measurable goal 2]

## Non-Goals (Explicit Scope Boundaries)

- [Thing we are NOT doing 1]
- [Thing we are NOT doing 2]
- [Adjacent feature we're explicitly deferring]

## Proposed Solution

### Conceptual Overview
[High-level description of the solution — the "what", not the "how"]

### User Journey
[Step-by-step happy path from the user's perspective]

## Architecture

### Data Model
[Entities, relationships, key attributes — conceptual, not schema definitions]

### System Boundaries
[What systems are involved, where does this feature live]

### API Surface
[What endpoints/interfaces are needed — conceptual, not specifications]

### Integration Points
[How this connects to existing systems]

## Implementation Approach

### Recommended Pattern
[Architectural pattern and why it fits. Reference existing codebase patterns where applicable.]

### Key Technical Decisions
| Decision | Choice | Rationale | Trade-offs |
|----------|--------|-----------|------------|
| [Decision 1] | [Choice] | [Why] | [What we're giving up] |
| [Decision 2] | [Choice] | [Why] | [What we're giving up] |

### Rough Task Breakdown
1. [Major chunk 1] — [brief description, dependencies]
2. [Major chunk 2] — [brief description, dependencies]
3. [Major chunk 3] — [brief description, dependencies]

### Riskiest Part
[What's most likely to go wrong or take longer than expected, and why]

## Edge Cases & Decisions

| Edge Case | Decision | Rationale |
|-----------|----------|-----------|
| [Case 1] | [What we'll do] | [Why] |
| [Case 2] | [What we'll do] | [Why] |
| ... | ... | ... |

## Security Considerations

- [Data sensitivity assessment]
- [Access control requirements]
- [Threat model considerations]
- [Compliance implications if any]

## Failure Modes & Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| [Risk 1] | Low/Med/High | Low/Med/High | [Strategy] |
| [Risk 2] | Low/Med/High | Low/Med/High | [Strategy] |

## Open Questions

- [ ] [Unresolved question 1]
- [ ] [Unresolved question 2]

## Alternatives Considered

### [Alternative 1 Name]
**Description:** [What this approach would look like]
**Rejected because:** [Why we're not doing this]

### [Alternative 2 Name]
**Description:** [What this approach would look like]
**Rejected because:** [Why we're not doing this]

---

*This plan captures the "what", "why", and high-level "how" of the feature. It is intended as input for `/write-spec`, which will produce the detailed implementation specification. All artifacts are stored in `.claude/` to keep the project repo clean.*
```

## Important Constraints

- **Phase A is read-only** — all interactive work happens in plan mode, no file writes
- **Phase B is write-only** — just document generation, no more questions
- **Be a skeptic** — your job is to poke holes, not be a yes-man
- **Keep iterating** — don't rush to document generation
- **Ground in reality** — read relevant codebase files to validate technical assumptions
- **Implementation Approach is key** — this is what makes `/plan` more useful than brainstorming alone
- **This is NOT a full implementation spec** — leave detailed task specs for `/write-spec`

## Example Session Flow

1. User runs `/plan AI-1234`
2. Claude enters plan mode, fetches the ticket, loads prime-context if available
3. Summarize starting point, ask first round of clarifying questions
4. User answers, Claude asks follow-up questions probing deeper
5. Claude pushes back: "Do we really need X? What if we just did Y instead?"
6. User defends or adjusts scope
7. Claude surfaces edge cases: "What happens when Z?"
8. User provides decisions on edge cases
9. Claude probes security: "Who should NOT have access to this?"
10. Claude explores implementation approach: reads codebase, suggests patterns
11. More back and forth until plan is solid...
12. User confirms → Claude exits plan mode
13. Document saved to `.claude/plans/feature-name.md`

## Example Usage

```
/plan AI-1234
/plan "batch conversation analysis for admin dashboard"
/plan prime-context/context.md
```

## Error Handling

- If Linear MCP unavailable or ticket not found, ask user to provide the feature description directly
- If user wants to skip questions, gently push back — the value is in the refinement process
- If `.claude/plans/` directory can't be created, save to current directory with clear filename
- If `prime-context/context.md` doesn't exist, proceed without it (don't error)
