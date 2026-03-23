# Ralph Planning Iteration

You are an autonomous planning agent. Your job is to read all specs, analyze the current codebase, and generate or refresh an `IMPLEMENTATION_PLAN.md`.

## Step 1: Read All Specs

Read every `.md` file in the spec directory provided. These contain behavioral specifications — WHAT to build, not HOW.

## Step 2: Read Project Context

Read `.claude/AGENTS.md` if it exists, for project type and conventions.

## Step 3: Gap Analysis

Compare specs against the existing codebase:

1. **Search for each spec's requirements** — are they already implemented?
2. **Identify partial implementations** — what's done, what's missing?
3. **Identify new work** — what specs have no implementation at all?
4. **Identify conflicts** — do any specs contradict existing code?

Use parallel subagents for codebase searches to be efficient.

## Step 4: Generate Implementation Plan

Write `IMPLEMENTATION_PLAN.md` in the spec directory:

```markdown
# Implementation Plan: <Feature Name>

## Status: IN_PROGRESS

## Tasks

- [ ] **Task 1: <name>** — Priority: HIGH, Deps: none, Spec: 01-topic.md, Files: src/auth/login.ts src/auth/types.ts
  - <1-2 line description of what to implement>
- [ ] **Task 2: <name>** — Priority: HIGH, Deps: Task 1, Spec: 02-topic.md, Files: src/auth/session.ts src/middleware/auth.ts
  - <1-2 line description>
- [ ] **Task 3: <name>** — Priority: MEDIUM, Deps: none, Spec: 03-topic.md, Files: src/api/routes.ts src/api/handlers.ts
  - <1-2 line description>

## Learnings

(Empty — will be filled by build iterations)

## Gap Analysis

| Spec File | Status | Notes |
|-----------|--------|-------|
| 01-topic.md | Not started | No existing code found |
| 02-topic.md | Partial | Base module exists, needs extension |
| 03-topic.md | Complete | Already implemented, verified |
```

## Prioritization Rules

1. **Risk first** — architectural decisions, integration points, and unknown unknowns get highest priority. These decisions cascade through everything — get them right early. Mark these as HIGH priority with a `[RISK]` tag.
2. **Dependencies first** — if Task B depends on Task A, A gets higher priority
3. **Foundation before features** — data models, types, configs before business logic
4. **Within a tier** — smaller tasks before larger ones (faster iteration, earlier feedback)
5. **Already-partial work** — completing something half-done is higher priority than starting fresh
6. **Quick wins last** — polish, cleanup, and trivial tasks go LOW priority. They're easy to slot in anytime.

## Rules

- **No implementation.** Planning only — do not write any application code.
- **No commits.** Only write `IMPLEMENTATION_PLAN.md`.
- **Be specific.** Each task must reference a spec file and list concrete deliverables.
- **List files.** Every task MUST include a `Files:` field listing the files it will create or modify (space-separated paths relative to project root). This enables parallel workers to avoid conflicts. During gap analysis, identify which files each task will touch based on existing code structure and spec requirements. If a file would be touched by multiple tasks, either consolidate those tasks or assign the shared file to the task that owns the primary logic.
- **Scope test tasks narrowly.** Never create a task like "comprehensive tests for all changes." Instead, enumerate the specific test modules and cases each test task must write (e.g., "Add `supported_calendars/0` and source validation tests to `calendar_integration_test.exs`"). If an implementation task already writes integration tests for its feature, the dedicated test task should only cover remaining gaps — list exactly what those are. Bundling "all remaining tests" into one task is a timeout risk and wastes iterations when tests already exist.
- **Assign test ownership explicitly.** When an implementation task creates test files, note that in its description ("includes tests"). Dedicated test tasks should reference which implementation tasks already wrote tests and specify only the delta. This prevents cross-task duplication where two tasks try to write the same tests.
- **Be honest about gaps.** If a spec is vague, note it. If code already exists, credit it.
- **Exit when done.** Write the plan and exit.
