---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Edit
  - Bash
  - AskUserQuestion
  - EnterPlanMode
  - ExitPlanMode
effort: high
---

# Implement a Task

Implements a spec task or an ad-hoc request, with planning and verification proportional to its uncertainty, impact, reversibility, and scope.

## Input

$ARGUMENTS - Either:
- A task number (e.g., `3`) — will look for the most recent spec or ask which spec to use
- A spec path and task number (e.g., `.claude/specs/feature-name-spec.md 3`)
- A spec path and task name (e.g., `.claude/specs/feature-name-spec.md "Create migration"`)
- An ad-hoc description (e.g., `"add a health check endpoint"`)

Optional modes:
- `--plan` — use plan mode and obtain plan approval before implementation
- `--worktree` — implement in an isolated worktree
- `--approve-tests` — write failing contract tests, commit them, and obtain explicit approval before implementation; approved contract tests are immutable

Parse these flags separately from the description or spec/task selector. Honor equivalent modes explicitly requested in the conversation or spec. A normal TDD request selects test-first development without automatically adding immutable contracts or a test-approval gate. Merely naming tests in a spec does not select contract mode.

## Instructions

### Ralph Mode Detection

**If `RALPH_MODE=1` environment variable is set OR `--ralph` flag is present in `$ARGUMENTS`:**

Switch to autonomous mode — skip all interactive prompts and implement exactly one task:

Ralph owns isolation, execution limits, progress preservation, and its RED/GREEN contract-testing policy. Follow `skills/ralph/references/PROMPT_build.md` for its contract and verification requirements. Reject conflicting interactive `--plan` or `--approve-tests` flags before starting; do not silently drop an approval request. The interactive phases below do not change Ralph's gates.

1. **Parse spec location** from `$ARGUMENTS` or environment (`RALPH_SPEC_DIR`)
2. **Read `IMPLEMENTATION_PLAN.md`** from the spec directory
3. **Auto-pick task:** Select the highest-priority incomplete task (`[ ]`) whose dependencies are all met:
   - Priority order: HIGH > MEDIUM > LOW
   - Within same priority: lowest task number first
   - Skip tasks whose deps reference incomplete tasks
4. **Search codebase first:** Before implementing, search for existing code matching the task's spec. If already done, mark complete and exit.
5. **Read the task's spec file** (referenced in the plan's `Spec:` field)
6. **Implement** following the spec — use existing patterns, don't add extras
7. **Run tests** (resolve commands using `commands/shared-patterns.md`, which reads `.claude/project-commands.json` before auto-detection). Tests must pass.
8. **Run lint** (use the same structured command configuration). Lint must pass.
9. **Commit** with a descriptive message:
   ```
   feat: <what this task accomplishes>

   Implements task N from IMPLEMENTATION_PLAN.md
   ```
10. **Update `IMPLEMENTATION_PLAN.md`:**
    - Mark task: `- [ ]` → `- [x]`
    - Add learnings if any
    - If last task, set `## Status: COMPLETE`
    - Commit the plan update separately
11. **Exit cleanly** — do NOT pick up another task

**In Ralph mode, these are disabled:**
- All `AskUserQuestion` calls — no interactive prompts
- `EnterPlanMode` / `ExitPlanMode` — no planning phases
- `TodoWrite` — no todo tracking
- Summary reports — the commit and plan update are the record

**If not in Ralph mode**, proceed with the normal interactive flow below.

---

### Phase 0: Inspect and Choose the Workflow

Follow **Proportional Workflow** in `commands/shared-patterns.md`. Read relevant project guidance, inspect the worktree status, search for existing behavior, and identify the intended outcome and verification approach. Preserve unrelated local changes.

- **Small, clear change:** Proceed through the applicable implementation and verification phases without a separate plan document or approval round.
- **Substantial or ambiguous change:** Resolve material uncertainty, maintain a concise conversational plan, then implement. Save a plan or generate a spec only when requested or useful for handoff. Ask questions only when their answers could change implementation, acceptance criteria, or risk.
- **Unattended execution:** Use Ralph with agreed scope and limits, isolated work, and durable progress. Do not turn an interactive request into an unattended run without authorization.

Reassess after inspection. If a material scope or behavior decision emerges, explain it and resolve that decision before dependent work. Reuse decisions and authorization already supplied.

**If `--plan` is selected:** Call `EnterPlanMode` before research. Present the concrete plan and use `ExitPlanMode` for approval when ready; do not add a second approval prompt with `AskUserQuestion`. Once approved, continue with Phase 2. For spec inputs, load Phase 1 during research first. Skip a new approval round if the same plan is already approved and the scope has not changed.

**For ad-hoc inputs:** Derive acceptance criteria and verification from the request and relevant code; skip Phase 1 and continue at Phase 2. A spec is optional.

### Phase 1: Load and Parse Spec

**Locate the spec document:**
- If full path provided, read it directly
- If only task number provided:
  - List files in `.claude/specs/` directory
  - If one spec exists, use it
  - If multiple specs exist, ask user to select one
- If spec not found, show available specs and exit

Also read the corresponding plan in `.claude/plans/` if available, for example `.claude/plans/foo.md` for `.claude/specs/foo-spec.md`.

**Extract the target task:**
- Parse the spec document to find the specified task (by number or name)
- Extract all task details:
  - Summary
  - Dependencies
  - Files to create/modify
  - Detailed specification
  - Edge cases
  - Acceptance criteria
  - Testing requirements
  - Test mode (`standard`, `approved-contract`, or `ralph-contract`) and any explicit legacy contract policy
  - Notes/Warnings

**Validate dependencies:**
- Check if dependent tasks are mentioned as completed in the spec or codebase
- If dependencies appear incomplete, warn the user and ask whether to proceed
- List what the dependent tasks were supposed to deliver

### Phase 2: Pre-Implementation Analysis

**Choose the checkout:** Use the current checkout by default when project policy permits. For `--worktree`, concurrent work that needs isolation, or project-required isolation, reuse an appropriate existing worktree or create one using **Worktree Creation** in `commands/shared-patterns.md`.

Derive a valid, unused branch name from the spec slug or ad-hoc description, preserving a ticket prefix. Use a supplied name when present; a routine derived name needs no confirmation. Report the branch and path. Copy relevant untracked or ignored plan/spec files and project command configuration into a new worktree when needed. Do not overwrite existing files or assume a new worktree includes uncommitted inputs; resolve any dependency on local changes before switching. Perform remaining phases in the selected checkout.

For substantial work, maintain a concise checklist of implementation steps and acceptance checks. A small change does not need a separate todo artifact.

**Understand the context:**
- Read all files mentioned in "Files to create/modify"
- Read any files mentioned in the detailed specification
- If the spec references existing patterns, read those examples
- Understand the existing code structure before making changes

**Identify risks:**
- Note any warnings from the spec
- Consider edge cases listed
- Resolve questions that affect behavior, acceptance criteria, or risk; record reasonable assumptions for minor details

### Phase 3: Select and Prepare Verification

Resolve test and lint commands using **Project Context: Test and Lint Command Detection** in `commands/shared-patterns.md`, including `.claude/project-commands.json` overrides and explicit disables. Honor project-required checks.

**Standard mode:** Identify existing tests that demonstrate the outcome. Add behavioral or regression tests when they provide useful coverage, using the project's framework and conventions. For a bug fix, confirm a regression test fails for the reported behavior before the fix when practical. Ordinary TDD may write tests first without freezing them. No test-approval prompt or separate test commit is required. Correct erroneous tests with a reason; never weaken assertions to hide an implementation defect.

For changes without testable behavior, use direct inspection or appropriate targeted validation. Do not invent tests for a reversible documentation or mechanical change simply to complete a phase.

**Approved contract mode (`--approve-tests` or an explicit equivalent request):**

1. Encode the acceptance criteria as failing behavioral tests. Use a spec's Contract Tests section when available.
2. Run the tests and confirm they fail for the missing behavior, rather than syntax, import, or fixture errors.
3. Commit only the contract tests with `test: RED — failing tests for <task name>`. Preserve unrelated changes in the index.
4. Present the tests, criteria they establish, and failure evidence using `AskUserQuestion`. Obtain approval before implementation. If adjustments are requested, update and rerun the tests, then commit the corrections and ask again.
5. Record the approved contract commit. Its test files are frozen: do not modify, delete, rename, skip, or mark those tests as expected failures during implementation. Additional tests may be added in new files. If the approved contract is wrong or cannot be met, stop for a user decision instead of weakening it.

If the spec selects `approved-contract`, use the approval flow above. If an existing spec selects `ralph-contract` or explicitly requires immutable contracts without approval, run the same RED/commit/lock workflow without the approval prompt; those files lock on the RED commit. A task without testable behavior skips contract creation and reports the alternative verification. Never label such work as having an approved test contract.

### Phase 4: Implementation

Implement the requested behavior with a focused, readable change that satisfies the acceptance criteria.

Before writing new code, ask in this order:
1. **Can I delete code** to make this work? Removing a special case beats adding a new one.
2. **Can I compose existing functions/modules?** A 2-line call beats a 20-line reimplementation.
3. **Can I add a parameter to existing code** rather than a new function/module?
4. **Can I use stdlib/framework features** instead of custom logic?
5. **Can I use data (maps, config) instead of code** (conditionals, new functions)?
6. Only after exhausting 1-5: write new code, and write the minimum.

**Follow the agreed task:**
- Implement the behavior and acceptance criteria from the request or spec
- Use existing project patterns and conventions
- Respect defined data structures, API contracts, and file locations
- Resolve material deviations with the user; record minor implementation choices

**Implementation order:**
1. Data/Schema changes first (migrations, types, models)
2. Core business logic
3. API/Interface layer
4. Integration points

**Rules:**
- Make small, incremental changes
- Keep changes focused on the agreed task
- Don't refactor unrelated code
- Don't add features outside the agreed scope
- Follow existing codebase conventions
- Don't add abstractions for single use sites — inline is fine
- Don't add error handling for conditions that can't occur
- Don't add docstrings, comments, or type annotations to code you didn't functionally change
- When immutable contract mode is selected, keep its test files frozen

Run the relevant tests after implementation and fix failures caused by the change. In immutable contract mode, all contract tests must pass without changing their files.

**As you complete each item:**
- Update the checklist or saved plan when one is being maintained
- Note any deviations from spec (and why)

### Phase 4b: REFACTOR (Optional)

If the green implementation has obvious duplication or awkwardness, clean it up now:
- Tests must stay green after every change
- No new behavior — refactoring is structure-only
- Contract tests remain untouched when immutable contract mode is selected
- If the code is clean enough, skip this step

### Phase 5: Verification

Run the test, lint, and other checks selected in Phase 3. Use focused checks when appropriate and run broader regression checks when shared behavior or project policy calls for them. Configured required checks must pass. Explicitly report checks that are disabled, unavailable, or not run.

**Check each acceptance criterion:**
Go through the acceptance criteria one by one and verify:
- [ ] Each criterion is met
- [ ] Tests or direct validation provide evidence for the criterion
- [ ] Edge cases are handled

**Code quality check:**
- Review your changes for obvious issues
- Ensure no debug code or TODOs left behind
- Verify no secrets or sensitive data exposed
- Check that error handling is appropriate
- In immutable contract mode, verify contract test files were not modified after the contract was locked

### Phase 6: Summary Report

Report what changed, what was verified with actual outcomes, and any unresolved limitations. For a small change, a short paragraph is sufficient. For a substantial task, use the following structure and omit inapplicable sections:

```markdown
## Implementation Complete: Task [N] - [Name]

### Changes Made
- `path/to/file.ex` - [what was done]
- `path/to/other.ex` - [what was done]

### Acceptance Criteria Status
- [x] [Criterion] - [test or direct validation evidence]

### Contract Testing (only when selected)
- Contract commit: [SHA and approval status when approval was requested]
- Test results: [RED/GREEN evidence]
- Contract integrity: [whether frozen test files were preserved]

### Test Results
[Pass/Fail summary]

### Deviations from the Agreed Task
[None, or list any necessary deviations and why]

### Notes for Reviewer
[Any context helpful for code review]

### Remaining Work
[Unresolved limitations, blockers, or follow-up tasks, if any]
```

## Error Handling

**If the request or spec has material ambiguity:**
- Inspect available context, then use AskUserQuestion for the decision that remains
- Document the clarification for future reference

**If implementation is blocked:**
- Clearly explain what's blocking
- Suggest how to unblock (missing dependency, unclear requirement, etc.)
- Don't leave partial implementations without clear status

**If tests fail:**
- Show the failure output
- Attempt to fix
- If unable to fix, report what was tried and ask for help

## Important Constraints

- **Keep the workflow proportional** - Plan and clarify until material uncertainty is resolved; honor selected modes
- **Honor contracts when selected** - Approved or explicitly immutable test contracts remain frozen
- **Stay focused** - Implement the agreed task and preserve unrelated work
- **Document deviations** - If you must deviate from spec, explain why
- **Verify behavior** - Run checks appropriate to the change and all project-required gates
- **Keep it atomic** - This should be a single, mergeable PR
- **Commit when requested** - Standard interactive work does not require automatic commits; selected contract mode and Ralph have their own commit requirements

## Example Usage

```
/agentic-coding-workflow:implement 3
```

This would:
1. Find the spec file (or ask which one)
2. Also read the corresponding plan doc from `.claude/plans/` if available
3. Extract Task 3's specification
4. Choose planning and isolation based on the task and selected modes
5. Implement the task following the spec
6. Write and run tests
7. Verify acceptance criteria
8. Report completion status

```
/agentic-coding-workflow:implement .claude/specs/batch-analysis-spec.md 5
```

This would implement Task 5 from the specified spec file.

```
/agentic-coding-workflow:implement .claude/specs/auth-spec.md "Add JWT validation"
```

This would find and implement the task named "Add JWT validation" from the auth spec.

```
/agentic-coding-workflow:implement "add a health check endpoint to the API"
```

This inspects relevant context, implements directly when clear, verifies, and reports. If inspection reveals material uncertainty, it resolves that uncertainty and maintains a concise plan before implementation.

Optional modes can be combined:
```
/agentic-coding-workflow:implement --plan --worktree --approve-tests "add JWT validation"
```
This selects plan approval, isolation, and explicit approval of immutable contract tests before implementation.
