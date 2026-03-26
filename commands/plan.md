---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash
  - AskUserQuestion
  - WebFetch
  - Agent
  - mcp__claude_ai_Linear__get_issue
  - mcp__claude_ai_Linear__list_issues
effort: high
---

# Feature Planning Partner

A unified planning command that combines brainstorming and plan formation into a single interactive session. Produces a comprehensive plan document that feeds directly into `/agentic-coding-workflow:write-spec`.

## Input

$ARGUMENTS - Either:
- A Linear ticket ID (e.g., `AI-1234`)
- A feature description string (e.g., `"batch conversation analysis"`)
- A path to an existing context document (e.g., `../other-repo/docs/research.md`)

## Instructions

### Phase A: Interactive Refinement (Read-Only)

> **CRITICAL — DO NOT SKIP THIS PHASE.**
> Phase A is the entire point of this command. You are a thinking partner, not a document generator. If you rush through questioning to get to writing, you have failed. The minimum bar is **3 rounds of back-and-forth** with the user before you may proceed to Phase B.

**Phase A is read-only.** Use only Read, Glob, Grep, and Agent (for research) during this phase. Do NOT write files or run destructive commands. Focus entirely on asking questions and exploring the codebase.

#### Step 1: Load Context

**Determine the target project.** The plan document will be saved to the project the user is working on, which may differ from where this plugin lives. If the user references a path outside the current directory (e.g., `../repo/docs/spec.md`), the target project is that directory's git root. Resolve and remember this path now — you'll need it in Phase B.

**Auto-load prime context if available:**
- Check if `.claude/prime-context/context.md` exists in the target project — if so, read it
- If the input is a path to a context file, read that instead

**If the input looks like a ticket ID** (pattern: letters-numbers like "AI-1234", "COMMS-567"):
- Use the Linear MCP tool to fetch the ticket details
- Extract: title, description, acceptance criteria, any linked tickets
- Use this as the starting point

**If the input is a feature description:**
- Use the description as-is for the starting point

#### Step 2: Iterative Refinement (The Core Loop)

This is NOT a one-and-done questionnaire. You are a thinking partner who keeps probing until the feature is crystal clear. Use `AskUserQuestion` repeatedly to dig deeper.

**Track your progress.** Maintain a mental checklist:
- [ ] Asked at least 3 rounds of questions (HARD REQUIREMENT)
- [ ] Identified at least 5 edge cases
- [ ] Pushed back on at least 2 assumptions
- [ ] Explored at least 1 simpler alternative
- [ ] Scope boundaries are clear
- [ ] Implementation approach is grounded in the actual codebase

**Round 1 — Problem space (MANDATORY before anything else):**
- What specific problem are we solving?
- Who exactly experiences this problem? (Be specific — not "users" but which users, in what context)
- Why does this matter now? What's the cost of not solving it?
- How are users currently working around this problem?

**Round 2 — Challenge and push back:**
- Play devil's advocate — question whether this feature is even needed
- Ask "what if we did nothing?" and make them justify the investment
- Suggest simpler alternatives and see if they'd work
- Push back on scope creep — ask "is that really part of this feature?"
- Question assumptions — "you said X, but have you validated that?"

**Round 3+ — Explore deeper (continue until the checklist is complete):**

*Happy path:*
- Walk through the ideal user journey step by step
- What does success look like?
- How will users discover this feature?
- What's the simplest possible version that delivers value?

*Edge cases (surface at least 5):*
- What happens when things go wrong?
- What if the user has no data? Too much data?
- What about concurrent users/operations?
- What about permissions/authorization edge cases?
- What if external dependencies are unavailable?
- What about backward compatibility?

*Integration points:*
- What existing systems does this touch?
- What APIs need to change?
- What data needs to flow where?
- What are the system boundaries?

*Failure modes:*
- What can go wrong?
- How do we recover from failures?
- What's the blast radius of a bug here?
- What monitoring/alerting do we need?

*Security considerations:*
- What data is involved? PII? Sensitive?
- Who should have access? Who shouldn't?
- What's the threat model?

*Scope boundaries:*
- What is explicitly NOT part of this feature?
- What's being deferred to future work?
- What adjacent features are we NOT building?

#### Step 3: Implementation Approach (Codebase Research)

After the problem and solution are well-defined, shift to technical planning. Use Agent subagents (with `subagent_type: "Explore"`) to research the codebase in parallel. This keeps your main context clean.

**Recommended pattern:**
- What architectural pattern fits best?
- Are there existing patterns in the codebase to follow?
- Read relevant codebase areas to ground decisions in reality

**Key technical decisions:**
- What are the major decision points?
- What are the trade-offs for each?
- What's the recommended choice and why?

**Rough task breakdown:**
- What are the major chunks of work? (3-7 chunks, not 20)
- What's the dependency order?
- What can be parallelized?
- What's the riskiest part?

#### Step 4: Synthesis Check (GATE — Do Not Proceed Unless All Pass)

Before moving to Phase B, verify EVERY item:
- [ ] Asked at least 3 rounds of questions
- [ ] Identified at least 5 edge cases
- [ ] Pushed back on at least 2 assumptions
- [ ] Explored at least one simpler alternative
- [ ] Scope boundaries are clear
- [ ] Implementation approach is grounded in the actual codebase

**If any item fails, go back to Step 2.** Tell the user which items are incomplete and ask targeted questions to fill the gaps.

When all items pass, tell the user: "The plan is ready to write. Shall I generate the document?" Wait for confirmation before proceeding.

### Phase B: Document Generation

**Confirm with the user before writing.** Present a concise summary (3-5 bullet points covering: the problem, proposed solution, key decisions, and scope boundaries) and ask if they're ready to generate the document using `AskUserQuestion`. Once confirmed, proceed to write the full document.

**Create the output directory** in the TARGET PROJECT (not the plugin repo):
```bash
mkdir -p <target-project-path>/.claude/plans
```

**Generate a slug** from the feature name (lowercase, hyphens, no special chars). **If the input was a ticket ID** (e.g., `AI-1234`), prefix the slug with the ticket ID: `AI-1234-feature-name`. This ticket-prefixed slug becomes the canonical name for all downstream artifacts (specs, worktrees, branches). If the input was a description string with no ticket, use just the feature name slug.

**Write the document** to `<target-project-path>/.claude/plans/<slug>.md` using the template below.

> **LEVEL OF DETAIL CHECK:** Before writing, review your draft mentally. If it contains specific file paths with line-level changes, code snippets, class/function definitions, or per-file modification tables — **STOP**. You are writing an implementation spec, not a plan. Strip it back to conceptual descriptions. The plan captures "what" and "why" and high-level "how". The `/agentic-coding-workflow:write-spec` command produces the detailed implementation specification.

#### Document Template

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
[What endpoints/interfaces are needed — conceptual, not full specifications]

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

*This plan captures the "what", "why", and high-level "how" of the feature. It is intended as input for `/agentic-coding-workflow:write-spec`, which will produce the detailed implementation specification.*
```

## Important Constraints

- **Phase A is the core value** — do NOT rush through it. 3 rounds of questions is the MINIMUM
- **Phase B is write-only** — just document generation, no more questions
- **Be a skeptic** — your job is to poke holes, not be a yes-man
- **Ground in reality** — read relevant codebase files to validate technical assumptions
- **This is NOT an implementation spec** — no file paths, no code snippets, no per-file change lists. If your document has those, rewrite it at a higher level. Leave detailed specs for `/agentic-coding-workflow:write-spec`
- **Save to the target project** — the plan goes in `<target-project>/.claude/plans/`, NOT in this plugin's directory and NOT in `~/.claude/plans/`
- **Confirm before writing** — summarize the plan and get user confirmation via `AskUserQuestion` before generating the document

## Example Session Flow

1. User runs `/agentic-coding-workflow:plan AI-1234`
2. Claude loads context (ticket, prime-context if available)
3. Claude summarizes starting point, asks first round of clarifying questions (problem space)
4. User answers → Claude asks follow-up questions probing deeper
5. Claude pushes back: "Do we really need X? What if we just did Y instead?"
6. User defends or adjusts scope
7. Claude surfaces edge cases: "What happens when Z?"
8. User provides decisions on edge cases
9. Claude probes security: "Who should NOT have access to this?"
10. Claude explores implementation approach: uses Explore agents to research codebase, suggests patterns
11. More back and forth until the synthesis checklist passes...
12. Claude says "The plan is ready to write. Shall I generate the document?"
13. User confirms → Claude writes document to `<target-project>/.claude/plans/feature-name.md`

## Example Usage

```
/agentic-coding-workflow:plan AI-1234
/agentic-coding-workflow:plan "batch conversation analysis for admin dashboard"
/agentic-coding-workflow:plan ../other-repo/docs/research-spec.md
```

## Error Handling

- If Linear MCP unavailable or ticket not found, ask user to provide the feature description directly
- If user wants to skip questions, gently push back — the value is in the refinement process. If they insist, note which synthesis checklist items are incomplete in the document's Open Questions section
- If the target project's `.claude/plans/` directory can't be created, ask the user where to save
- If prime-context doesn't exist, proceed without it (don't error)
