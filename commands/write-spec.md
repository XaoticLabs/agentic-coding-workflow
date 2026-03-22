---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash
  - AskUserQuestion
  - Task
---

# Implementation Spec Generator

Transforms a brainstorming document into a detailed implementation specification with atomic, actionable tasks.

## Input

$ARGUMENTS - Either:
- A path to a plan document (e.g., `.claude/plans/feature-name.md`)
- A path to a brainstorming document (e.g., `brainstorming/feature-name.md`)
- A feature slug (e.g., `feature-name`) — will look in `.claude/plans/` first, then `brainstorming/`
- An inline quoted prompt (e.g., `"add rate limiting to the API"`) — treated as a lightweight plan

## Instructions

### Phase 1: Load and Parse Brainstorming Document

**Locate the document:**
- If full path provided, read it directly
- If slug provided, look for `.claude/plans/<slug>.md` first, then fall back to `brainstorming/<slug>.md`
- If an inline quoted prompt is provided (no file match), treat the string as a lightweight plan and proceed directly to Phase 2 (codebase analysis) using the prompt as context
- If file not found, list available docs from both `.claude/plans/` and `brainstorming/` and ask user to select one

**Extract key information:**
- Problem statement and goals
- Proposed solution and user journey
- Architecture (data model, APIs, integrations)
- Edge cases and decisions
- Security considerations
- Open questions

### Phase 2: Codebase Analysis

**Before writing any spec, understand the existing codebase:**

1. **Identify relevant areas** based on the feature:
   - Search for similar patterns already implemented
   - Find the modules/directories this feature will touch
   - Identify existing abstractions to leverage

2. **Document technical constraints:**
   - What frameworks/libraries are in use?
   - What patterns does this codebase follow?
   - Are there existing conventions for similar features?

3. **Map dependencies:**
   - What existing code will this feature depend on?
   - What existing code might need modification?

### Phase 3: Clarify Open Questions

**If the brainstorming doc has unresolved questions:**
- Use AskUserQuestion to resolve any that are critical for implementation
- Mark questions that can be deferred to implementation time
- Document assumptions made for questions that can't be answered now

### Phase 4: Reduce Ambiguity Pass

**Before breaking into tasks, explicitly surface and resolve vague areas.**

Scan the plan/brainstorming document and your Phase 2 analysis for ambiguity:

1. **Identify vague language:**
   - Look for words like "appropriate", "as needed", "various", "etc.", "should handle", "properly"
   - Flag any requirement that two engineers could reasonably interpret differently
   - Highlight any "TBD", "TODO", or handwave-y sections

2. **Identify implicit assumptions:**
   - What behavior is assumed but never stated?
   - What error handling is expected but not specified?
   - What performance characteristics are assumed?
   - What user permissions/roles are assumed?

3. **Identify missing specifics:**
   - API contracts without defined error responses
   - Data models without stated constraints (nullable? unique? max length?)
   - Flows without defined timeout/retry behavior
   - UI descriptions without defined empty/loading/error states

4. **Resolve or document each ambiguity:**
   - For critical ambiguities: Use AskUserQuestion to get a definitive answer
   - For non-critical ambiguities: State a reasonable default and document the assumption
   - For each resolved item, note the decision in the spec so implementers don't re-discover the same question

**Output:** A list of ambiguities found and their resolutions, which gets included in the spec's "Technical Context" section.

### Phase 5: Break Down into Atomic Tasks

**Rules for atomic tasks:**
- Each task should be completable in a single commit (ideally 1-4 hours of work)
- Each task should be independently testable
- Each task should have clear acceptance criteria
- Tasks should have minimal dependencies on other tasks
- Tasks should be orderable (what must come before what)

**Task categories to consider:**
1. **Data/Schema tasks** - migrations, models, types
2. **Core logic tasks** - business logic, services, domain code
3. **API tasks** - endpoints, request/response handling
4. **Integration tasks** - connecting to existing systems
5. **UI tasks** - components, pages, user interactions (if applicable)
6. **Testing tasks** - unit tests, integration tests, e2e tests
7. **Infrastructure tasks** - config, deployment, monitoring

### Phase 6: Write Detailed Specs

For each atomic task, write a complete specification:

```markdown
### Task [N]: [Descriptive Name]

**Summary:** One sentence describing what this task accomplishes.

**Dependencies:** [List task numbers that must be completed first, or "None"]

**Files to create/modify:**
- `path/to/file.ex` - [brief description of changes]
- `path/to/other_file.ex` - [brief description of changes]

**Detailed specification:**

[Detailed description of what to implement. Include:]
- Specific functions/modules to create
- Data structures and their fields
- API contracts (inputs, outputs, errors)
- Business logic rules
- Error handling requirements

**Edge cases to handle:**
- [Edge case 1 from brainstorming doc]
- [Edge case 2]

**Acceptance criteria:**
- [ ] [Specific, verifiable criterion 1]
- [ ] [Specific, verifiable criterion 2]
- [ ] [Test coverage criterion]

**Testing requirements:**
- Unit tests for: [specific functions/modules]
- Integration tests for: [specific flows]

**Notes/Warnings:**
- [Any gotchas, performance considerations, or things to watch out for]
```

### Phase 7: Generate Implementation Spec Document

**Create the output directory:**
```bash
mkdir -p .claude/specs
```

**Write the document** to `.claude/specs/<feature-slug>-spec.md`:

```markdown
# Implementation Spec: [Feature Name]

> Generated from: `.claude/plans/<slug>.md` (or `brainstorming/<slug>.md` or inline prompt)
> Generated on: [date]

## Overview

[1-2 paragraph summary of what we're building and why]

## Technical Context

### Relevant Codebase Areas
- `path/to/module/` - [what it does, why it's relevant]
- `path/to/other/` - [what it does, why it's relevant]

### Existing Patterns to Follow
- [Pattern 1]: [where it's used, why we should follow it]
- [Pattern 2]: [where it's used, why we should follow it]

### Key Dependencies
- [Existing module/service 1]: [how we'll use it]
- [Existing module/service 2]: [how we'll use it]

### Ambiguity Resolutions
| Area | Ambiguity | Resolution | Source |
|------|-----------|------------|--------|
| [area] | [what was unclear] | [decision made] | [user input / assumed default] |
| ... | ... | ... | ... |

## Implementation Tasks

### Summary

| Task | Name | Dependencies | Estimated Complexity |
|------|------|--------------|---------------------|
| 1 | [Name] | None | Low/Medium/High |
| 2 | [Name] | 1 | Low/Medium/High |
| ... | ... | ... | ... |

### Critical Path
[Visual or textual representation of task dependencies - what can be parallelized, what must be sequential]

---

### Task 1: [Name]
[Full task spec as defined above]

---

### Task 2: [Name]
[Full task spec as defined above]

---

[... more tasks ...]

## Testing Strategy

### Unit Testing
- [What to unit test and why]

### Integration Testing
- [What integration tests are needed]

### Manual Testing Checklist
- [ ] [Manual test scenario 1]
- [ ] [Manual test scenario 2]

## Rollout Considerations

### Feature Flags
- [Any feature flags needed? What behavior behind each?]

### Migration Strategy
- [Any data migrations? How to handle existing data?]

### Rollback Plan
- [How to roll back if something goes wrong]

## Open Items

- [ ] [Any remaining questions or decisions]
- [ ] [Things to verify during implementation]

---

*This spec is implementation-ready. Each task is designed to be picked up independently (respecting dependencies) and completed in a single commit.*
```

### Phase 8: Ralph-Compatible Output (conditional)

**Only run this phase if `--ralph` flag is present in `$ARGUMENTS`.**

After generating the monolithic spec (Phase 7), create a Ralph-compatible directory structure:

**Create the spec directory:**
```bash
mkdir -p .claude/specs/<slug>
```

**Split into topic files:**

Read the monolithic spec's Implementation Tasks section. For each task, create a separate spec file:

- File naming: `.claude/specs/<slug>/NN-<topic-slug>.md` (e.g., `01-database-schema.md`, `02-auth-middleware.md`)
- Each file contains ONLY:
  - Behavioral outcomes (WHAT to build)
  - Acceptance criteria
  - Edge cases
  - Testing requirements
- Each file must pass the **"one sentence without 'and'" scope test**: you should be able to describe what this file covers in one sentence without using "and"
- Do NOT include implementation details (HOW) — that's for the implementer to decide

**Topic file format:**
```markdown
# <Topic Name>

## Behavioral Outcomes

- <What the system should do>
- <Observable behavior from user/API perspective>

## Acceptance Criteria

- [ ] <Specific, verifiable criterion>
- [ ] <Specific, verifiable criterion>

## Edge Cases

- <Edge case and expected behavior>

## Testing Requirements

- <What to test and expected outcomes>
```

**Generate IMPLEMENTATION_PLAN.md:**

Write `.claude/specs/<slug>/IMPLEMENTATION_PLAN.md`:

```markdown
# Implementation Plan: <Feature Name>

## Status: IN_PROGRESS

## Tasks

- [ ] **Task 1: <name>** — Priority: HIGH, Deps: none, Spec: 01-topic.md
  - <1-2 line description of concrete deliverable>
- [ ] **Task 2: <name>** — Priority: HIGH, Deps: Task 1, Spec: 02-topic.md
  - <1-2 line description>
- [ ] **Task 3: <name>** — Priority: MEDIUM, Deps: none, Spec: 03-topic.md
  - <1-2 line description>

## Learnings

(Populated by Ralph build iterations)
```

**Prioritization rules for tasks:**
1. Dependencies first — if B depends on A, A gets higher priority
2. Foundation before features — data models, types, configs before business logic
3. Within a tier — smaller tasks first (faster iteration, earlier feedback)

**Both formats coexist:** The monolithic `.claude/specs/<slug>-spec.md` (for interactive `/agentic-coding-workflow:implement`) and the directory `.claude/specs/<slug>/` (for `/agentic-coding-workflow:ralph`) are generated together. No conflict.

**Report:** After generating, show the directory structure and task summary:
```
Ralph-compatible specs generated:

  .claude/specs/<slug>/
    01-topic-a.md
    02-topic-b.md
    03-topic-c.md
    IMPLEMENTATION_PLAN.md

  Tasks: N total (X HIGH, Y MEDIUM, Z LOW priority)
  Ready for: /agentic-coding-workflow:ralph <slug>
```

## Quality Checklist

Before finalizing the spec, verify:

- [ ] Every task has clear acceptance criteria
- [ ] Every task specifies which files to modify
- [ ] Dependencies between tasks are explicit
- [ ] Edge cases from brainstorming are assigned to specific tasks
- [ ] Security considerations are addressed in relevant tasks
- [ ] Testing requirements are clear for each task
- [ ] The critical path is identified
- [ ] Tasks are small enough for single PRs
- [ ] Existing codebase patterns are referenced

## Important Constraints

- **Be specific** - vague specs lead to implementation confusion
- **Reference actual code** - don't write specs in a vacuum, point to real files and patterns
- **Keep tasks atomic** - resist the urge to bundle related work
- **Make dependencies explicit** - no hidden assumptions about task ordering
- **Include the "why"** - link back to brainstorming decisions where relevant
- **Don't over-specify** - leave room for implementation judgment on minor details

## Example Usage

```
/agentic-coding-workflow:write-spec batch-conversation-analysis
```

This would:
1. Look for `.claude/plans/batch-conversation-analysis.md`, then `brainstorming/batch-conversation-analysis.md`
2. Analyze relevant parts of the codebase
3. Surface and resolve ambiguous requirements
4. Break the feature into 5-15 atomic tasks
5. Write detailed specs for each task
6. Output to `.claude/specs/batch-conversation-analysis-spec.md`

```
/agentic-coding-workflow:write-spec .claude/plans/batch-analysis.md
```

This would read the plan doc directly and generate a spec from it.

```
/agentic-coding-workflow:write-spec "add rate limiting to the API"
```

This would treat the inline prompt as a lightweight plan, analyze the codebase, and generate a spec.
