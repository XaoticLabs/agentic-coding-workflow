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
  - EnterWorktree
  - Agent
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
- A Jira/Linear ticket key or URL; retrieve its context through the shared CLI/API resolver

Optional modes:
- `--plan` — use plan mode and obtain plan approval before implementation
- `--worktree` — implement in an isolated worktree
- `--approve-tests` — prepare acceptance tests and obtain explicit approval of their behavioral expectations before implementation
- `--tracker jira|linear` — select the ticket provider
- `--ticket <key-or-url>` — associate an ad-hoc/spec task with a ticket
- `--start-ticket` — also transition the associated ticket to configured `in_progress` once scope and the working checkout are established
- `--review` — include independent review and supported repairs within the shared three-round budget before returning the final result

Parse these flags separately from the description or spec/task selector. Honor equivalent modes explicitly requested in the conversation or spec. A normal TDD request selects test-first development without automatically adding separate failing commits or a test-approval gate. Merely naming tests in a spec does not select contract mode.

## Instructions

### Ralph Mode Detection

**If `RALPH_MODE=1` environment variable is set OR `--ralph` flag is present in `$ARGUMENTS`:**

Switch to autonomous mode — skip all interactive prompts and implement exactly one task:

Ralph owns isolation, execution limits, progress preservation, and its test and verification integrity policy. Follow `skills/ralph/references/PROMPT_build.md` for its contract and verification requirements. Reject conflicting interactive `--plan`, `--approve-tests`, `--start-ticket`, or `--review` flags before starting; do not silently drop a selected mode. The interactive phases below do not change Ralph's gates.

1. **Parse spec location** from `$ARGUMENTS` or environment (`RALPH_SPEC_DIR`)
2. **Read `IMPLEMENTATION_PLAN.md`** from the spec directory
3. **Auto-pick task:** Select the highest-priority incomplete task (`[ ]`) whose dependencies are all met:
   - Priority order: HIGH > MEDIUM > LOW
   - Within same priority: lowest task number first
   - Skip tasks whose deps reference incomplete tasks
4. **Search codebase first:** Before implementing, search for existing code matching the task's spec. If already done, mark complete and exit.
5. **Read the task's spec file** (referenced in the plan's `Spec:` field)
6. **Implement** following the spec — use existing patterns, don't add extras
7. **Run tests** (resolve commands using `${CLAUDE_PLUGIN_ROOT}/references/shared-patterns.md`, which reads `.claude/project-commands.json` before auto-detection). Tests must pass.
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
The new `--start-ticket` and `--review` flags are interactive workflow modes;
reject them in Ralph mode rather than silently bypassing Ralph's executor and
verification contracts. Ralph can consume already fetched ticket criteria in
its spec without taking ownership of remote ticket updates.

---

### Phase 0: Inspect and Choose the Workflow

Follow **Proportional Workflow** in `${CLAUDE_PLUGIN_ROOT}/references/shared-patterns.md`. Read relevant project guidance, inspect the worktree status, search for existing behavior, and identify the intended outcome and verification approach. Preserve unrelated local changes.

For a ticket input or `--ticket`, follow **Ticket Context and Lifecycle** in
the shared patterns. Retrieve through `scripts/tickets.py get`, carry the exact
provider/scope/native ID/canonical URL, and use the title, description, relevant
comments, and acceptance criteria as the task input. Keep source requirements
distinct from your own derived checks. If a ticket input replaces a spec,
continue as an ad-hoc task after resolving material uncertainty. Do not treat
an unreadable ticket as permission to guess its implementation. `--start-ticket`
requires an associated ticket; reject it if none is available.

- **Small, clear change:** Proceed through the applicable implementation and verification phases without a separate plan document or approval round.
- **Substantial or ambiguous change:** Resolve material uncertainty, maintain a concise conversational plan, then implement. Save a plan or generate a spec only when requested or useful for handoff. Ask questions only when their answers could change implementation, acceptance criteria, or risk.
- **Ordinary unattended execution:** Follow **Native Goals and Session Continuity** in `${CLAUDE_PLUGIN_ROOT}/references/shared-patterns.md`. Use native `/goal` for continuation in the current isolated feature session. Run the same implementation and verification phases; do not require Ralph's task plan, generated briefings, commits, or a fresh session per task.
- **Enforced limits or coordinated recovery:** Select Ralph when required for external iteration/time bounds, dependency waves, rollback, or durable executor records. Honor an explicit Ralph request and its gates. Do not turn an interactive request into unattended execution without authorization.

Reassess after inspection. If a material scope or behavior decision emerges, explain it and resolve that decision before dependent work. Reuse decisions and authorization already supplied.

Continue related tasks in this session and reuse relevant code context and user
decisions. Use native compaction as needed; preserve the task's constraints and
verification approach. After resume, inspect current state before retrying an
interrupted operation. Keep required independent review in a separate context.

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

**Choose the checkout:** Use the current checkout by default when project policy permits. For `--worktree`, concurrent work that needs isolation, or project-required isolation, reuse an appropriate existing worktree or create one using **Worktree Creation** in `${CLAUDE_PLUGIN_ROOT}/references/shared-patterns.md`.

Derive a valid, unused branch name from the spec slug or ad-hoc description, preserving a ticket prefix. Use a supplied name when present; a routine derived name needs no confirmation. Report the branch and path. Copy relevant untracked or ignored plan/spec files and project command configuration into a new worktree when needed. Do not overwrite existing files or assume a new worktree includes uncommitted inputs; resolve any dependency on local changes before switching. Perform remaining phases in the selected checkout.

Carry `.claude/ticket-tracker.json` into an isolated checkout when needed,
preserving its project-selected settings and any existing destination file.
After setup and scope are established, `--start-ticket` authorizes preparing
and applying the `in_progress` transition through the resolver. Use the
canonical ticket URL and any selected tracker. A repeated request already at
the target status is a no-op. Report failures without claiming the ticket moved;
continue authorized local work unless project policy requires synchronization.

For substantial work, maintain a concise checklist of implementation steps and acceptance checks. A small change does not need a separate todo artifact.

Choose reviewable behavior/interface boundaries using
`${CLAUDE_PLUGIN_ROOT}/references/review-policy.md`. Keep each proposed change
understandable and verifiable; identify dependent follow-ups explicitly. When
the review queue is the bottleneck, finish evidence and address open feedback
before increasing parallel implementation. Do not change team WIP policy or
split tightly coupled code/tests just to meet a size target.

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

Resolve test and lint commands using **Project Context: Test and Lint Command Detection** in `${CLAUDE_PLUGIN_ROOT}/references/shared-patterns.md`, including `.claude/project-commands.json` overrides and explicit disables. Honor project-required checks.

**Standard mode:** Identify existing tests that demonstrate the outcome. Add behavioral or regression tests when they provide useful coverage, using the project's framework and conventions. For a bug fix, confirm a regression test fails for the reported behavior before the fix when practical. Ordinary TDD may write tests first without freezing them. No test-approval prompt or separate test commit is required. Follow **Test and Verification Integrity** in `${CLAUDE_PLUGIN_ROOT}/references/shared-patterns.md`: explain and independently review test corrections or changes that could weaken coverage; never weaken assertions to hide an implementation defect.

For changes without testable behavior, use direct inspection or appropriate targeted validation. Do not invent tests for a reversible documentation or mechanical change simply to complete a phase.

**Approved contract mode (`--approve-tests` or an explicit equivalent request):**

1. Encode the acceptance criteria as behavioral tests. Use a spec's Contract Tests section when available. Confirm RED for missing behavior when practical; separate failing commits are optional unless explicitly requested.
2. Run the tests and distinguish missing behavior from syntax, import, or fixture errors.
3. Present the cases, criteria, proposed expectations, and actual results using `AskUserQuestion`. Obtain approval before implementation. Prepare any requested adjustments and rerun before seeking approval of the revised expectations.
4. Record the approved cases/assertions, criteria, baseline commit or diff, and the user's approval reference. Approval protects those behavioral expectations, not entire files. Add cases in existing files and correct fixtures/helpers under the shared integrity policy.
5. If an approved expectation needs changing, prepare a concrete correction with its rationale, preserved/replacement coverage, and validation evidence, then obtain explicit human approval before treating the changed expectation as accepted. Independent review cannot substitute for that approval.

If the spec selects `approved-contract`, use the approval flow above. Treat legacy `ralph-contract` as autonomous behavioral testing with independent integrity review, not human approval or a file freeze. Honor a user's explicit stricter policy when it applies. A task without testable behavior uses direct validation and reports the evidence. Never label agent-authored tests as human-approved.

### Phase 4: Implementation

Implement the requested behavior with a focused, readable change that satisfies the acceptance criteria.

Choose structure from the task's context:
- Reuse existing functions, stdlib, and framework features when their semantics and contracts fit
- Remove obsolete code or duplication when it supports the task and preserves required behavior
- Choose functions, modules, parameters, or data structures for clear responsibilities and dependencies
- Use named helpers, including single-use helpers, when they clarify a domain operation, isolate side effects, or separate validation from execution; keep logic inline when easier to follow
- Retain validation and failure handling needed by the spec, trust boundaries, security, and integration contracts

Judge maintainability through readability, cohesion, coupling, and ease of safe change. Line counts, file counts, and addition-to-deletion ratios do not establish quality. Apply numeric size thresholds only when our own evaluations establish their benefit for the particular workload and record that evidence.

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
- Avoid abstractions and extension points without a current requirement or useful boundary
- Flag redundant error handling only with evidence about the actual call path and invariants
- Keep docstrings, comments, and type annotations relevant to the change and its comprehension
- Preserve acceptance criteria and human-approved expectations; explain and independently review corrections or coverage reductions under the shared integrity policy

Run the relevant tests after implementation and fix failures caused by the change. Review test and verification changes against the original criteria, including discovery, fixtures, mocks, snapshots, configuration, and failure handling. All required checks must pass.

**As you complete each item:**
- Update the checklist or saved plan when one is being maintained
- Note any deviations from spec (and why)

### Phase 4b: REFACTOR (Optional)

If the green implementation has obvious duplication or awkwardness, clean it up now:
- Tests must stay green after every change
- No new behavior — refactoring is structure-only
- Preserve behavioral expectations and coverage; review any test corrections under the shared integrity policy
- If the code is clean enough, skip this step

### Phase 5: Verification

Run the test, lint, and other checks selected in Phase 3. Use focused checks when appropriate and run broader regression checks when shared behavior or project policy calls for them. Configured required checks must pass. Explicitly report checks that are disabled, unavailable, or not run.

Use `${CLAUDE_PLUGIN_ROOT}/references/project-readiness.md` for Go, Python,
TypeScript, and mixed-project command selection. When relevant, exercise the
actual API, integration, or browser flow and retain concise evidence. Report
the checked revision or working-input fingerprint and what remains unverified.

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
- Review test and verification diffs for weakened coverage or bypasses; record rationale, independent review, and any required human approval

### Phase 5b: Independent Review and Repair (when `--review` is selected)

Use the existing review command/pr-reviewer guidance in a separate read-only
context. Give it the full diff, original criteria, base/head or working-input
fingerprint, verification evidence, and prior findings/round count. A model's
agreement does not replace runnable evidence. The implementation session owns
all edits; do not launch another writer on the same branch.

Follow `${CLAUDE_PLUGIN_ROOT}/references/review-policy.md` for the initial full
review, actionable findings, incremental re-review, and at most three completed
rounds per logical change across local and remote stages. Fix supported defects,
retain evidence for rejected findings, and rerun affected/required checks on
the final source state. Preserve the current round and dispositions in the
continuing session or `.claude/reviews/<ticket-or-branch>.json` for handoff; this
record is context, not trusted approval. Existing rounds do not reset at push.
If an independent reviewer is unavailable, report independent review NOT_RUN.
If material findings remain at the budget, hand off without claiming completion
or a clean review. An ordinary implementation without this flag retains its
existing one-session verification path and project-required review rules.

### Phase 6: Summary Report

Report what changed, what was verified with actual outcomes, and any unresolved limitations. For a small change, a short paragraph is sufficient. For a substantial task, use the following structure and omit inapplicable sections:

Include the **PR evidence** facts from
`${CLAUDE_PLUGIN_ROOT}/references/review-policy.md`: behavior, important decision,
observed verification and source state, remaining reviewer decisions, and
recovery when consequential. An authorized author/reviewer loop follows the
same policy's three-round budget; ordinary implementation does not start one.
For ticket work, include the canonical ticket identity and actual transition
outcome. For `--review`, include the reviewed source, completed rounds, remaining
findings, and the next action so shipping can resume the same history.

```markdown
## Implementation Complete: Task [N] - [Name]

### Changes Made
- `path/to/file.ex` - [what was done]
- `path/to/other.ex` - [what was done]

### Acceptance Criteria Status
- [x] [Criterion] - [test or direct validation evidence]

### Contract Testing (only when selected)
- Acceptance baseline: [cases/assertions, criteria, commit or diff, and human approval reference when selected]
- Test results: [actual behavioral/regression evidence; RED/GREEN when used]
- Verification integrity: [test corrections, coverage impact, independent review, and any renewed human approval]

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
- **Preserve verification integrity** - Follow the shared policy for acceptance criteria, human-approved expectations, justified corrections, and independent review
- **Stay focused** - Implement the agreed task and preserve unrelated work
- **Document deviations** - If you must deviate from spec, explain why
- **Verify behavior** - Run checks appropriate to the change and all project-required gates
- **Keep it atomic** - This should be a single, mergeable PR
- **Commit when requested** - Interactive testing or acceptance-test approval does not require separate commits; Ralph commits completed work
- **Continue related work** - Native goals and compaction do not impose a fresh session, spec, or commit after each task

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
This selects plan approval, isolation, and explicit approval of acceptance-test expectations before implementation.
