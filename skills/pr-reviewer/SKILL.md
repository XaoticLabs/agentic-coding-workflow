---
name: pr-reviewer
description: |
  Review pull requests for code quality, readability, maintainability, and security.
  Uses the PERFECT framework: Purpose, Edge Cases, Reliability, Form, Evidence, Clarity, Taste.
  Supports Elixir and Python. Auto-detects language from changed files.
  Use when: review code, review PR, code review, check PR, review pull request,
  review elixir, review python, PR analysis, code quality, review changes,
  review branch, check code, analyze PR, review for bugs, review for security.
  Keywords: review, PR, pull request, code review, code quality, PERFECT, Elixir, Python,
  OTP, Phoenix, Ecto, GenServer, pytest, ruff, pyright, mix test, credo, dialyzer.
allowed-tools: Bash, Read, Grep, Glob, WebSearch, WebFetch
effort: high
user-invocable: false
---

# PR Reviewer

Review pull requests using the PERFECT framework with structured output, repository-grounded findings, and language-specific checks. Auto-detects language from changed files.

Read `references/perfect-framework.md` for the full PERFECT phase definitions, severity mapping, and confidence level requirements.

When a finding depends on external semantics, load `references/source-registry.md` for relevant documentation by phase and language. External references explain semantics; repository evidence establishes whether a defect exists locally. Ordinary local correctness findings do not require web verification.

When invoked in learn mode (from the review command's `--learn` flag), load `references/learn-mode-prompts.md` for phase-specific quiz prompts and teaching templates.

## Language Detection

Determine the project language from changed files:

```bash
# Check changed file extensions
git diff origin/main...HEAD --name-only 2>/dev/null | grep -E '\.(ex|exs)$' && echo "ELIXIR"
git diff origin/main...HEAD --name-only 2>/dev/null | grep -E '\.py$' && echo "PYTHON"
```

Fallback: check for `mix.exs` (Elixir) or `pyproject.toml`/`setup.py` (Python) in the repo root.

If both languages are present, review both. If the caller specifies a language, use that.

## Worktree Setup

Always review in an isolated worktree to keep the user's working directory clean:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
source "${CLAUDE_PLUGIN_ROOT}/scripts/lib/worktree-safety.sh"
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
DIR_NAME="pr-review-$(echo "$BRANCH" | sed 's/[\/]/-/g' | sed 's/[^a-zA-Z0-9._-]//g')"
WORKTREE_PATH="${WORKTREE_BASE}/${DIR_NAME}"

mkdir -p "$WORKTREE_BASE"
git fetch origin "$BRANCH"
git worktree add "$WORKTREE_PATH" "origin/$BRANCH" --detach
register_worktree_owner "$REPO_ROOT" "$WORKTREE_PATH" "$(git -C "$WORKTREE_PATH" rev-parse HEAD)"
cd "$WORKTREE_PATH"
```

Clean up after review:
```bash
cd "$REPO_ROOT"
release_worktree "$REPO_ROOT" "$WORKTREE_PATH"
preserve_worktree_artifacts "$REPO_ROOT" "$WORKTREE_PATH" "${REPO_ROOT}/.claude/worktree-archives/$(date +%s)-${DIR_NAME}" &&
  remove_owned_worktree "$REPO_ROOT" "$WORKTREE_PATH" "" --keep-branch
```

Carry the same `WORKTREE_OWNER_TOKEN` across setup and cleanup calls. If ownership,
activity, cleanliness, ancestry, or preservation checks fail, report the retained path.
The review launcher (`scripts/launch-reviews.sh`) and its review process own exit
cleanup for the exact worktrees they create; no global SessionEnd hook sweeps reviews.
After uncatchable termination, retain the checkout for explicit recovery with the
same ownership and preservation checks. Never force-remove it by name.

## Review Workflow — PERFECT Phases

Review bottom-up: automated checks first, human judgment last. Each phase produces findings tagged with a PERFECT phase and confidence level. Failed or unavailable checks affect verification and merge readiness, but do not stop code inspection.

For every finding, explain the triggering condition, affected execution path, concrete consequence, supporting repository evidence or reproduction, and any uncertainty (write "None" when established). Use exact file/line references and trace relevant callers, inputs, and guards. For convention or clarity findings, identify the affected usage or maintenance task and an applicable repository rule or concrete cost. A pattern deviation, tool warning, CWE page, or style guide alone does not establish a defect. Treat language-specific reference checklists as candidate cues subject to these evidence requirements. See the framework's confidence definitions before assigning a tag.

### Phase 0: Gather Context

Before starting phases, collect the raw materials:

- Read the PR description (`gh pr view <number>`) or commit history (`git log origin/main..HEAD --oneline`)
- Run `git diff origin/main...HEAD` to see all changes
- **Read the actual changed files** — diffs alone are insufficient for line-accurate feedback
- Note the stated purpose of the PR for the Purpose phase later

### Phase 1: Evidence (Automated Checks)

Record failures and verification limitations, then continue the remaining phases. Distinguish checks that ran and found a failure from checks blocked by missing dependencies, credentials, services, tools, or CI access. Run other independent checks where possible.

Run all validation tools and report results:

**Elixir:**
```bash
mix test
mix format --check-formatted
mix credo        # if configured
mix dialyzer     # if configured
```

**Python:** Resolve the project's existing checks from `.claude/project-commands.json`, CI, and task/tool configuration. Use its chosen environment, formatter, linter, type checker, test runner, and file scope. Do not infer uv, Ruff, basedpyright, or pytest merely from Python files. Report missing required checks as verification limitations. The uv/Ruff/basedpyright profile is optional; see **Project Context: Test and Lint Command Detection** in `commands/shared-patterns.md`.

Also check CI status if PR number is available: `gh pr checks <number>`

Record each command, result, relevant output, and scope of verification. A reproduced check failure can be **Verified** as an observed failure; diagnose its cause separately. Tool warnings do not automatically verify a code defect. Confirmed required-check failures remain merge **BLOCKER**s. Unavailable or skipped required checks are verification limitations, not proof of a code defect; report incomplete verification and what remains to be run.

### Phase 2: Reliability

Scan for performance and security issues:

1. Review static analysis output from Phase 1 for security-relevant warnings
2. Check for: hardcoded secrets, SQL injection, unsafe deserialization, missing auth checks, N+1 queries, unbounded memory, race conditions
3. **Verification**: Trace the input or resource through the affected callers, validation/authentication guards, and sensitive operation. Establish a reachable trigger and concrete security or performance consequence using repository evidence or a reproduction. Consult external documentation only when needed to establish relevant API or security semantics; OWASP/CWE links classify a weakness, not prove a vulnerable call path.

Load language-specific references conditionally:
- **Elixir**: `references/elixir/elixir_otp_best_practices.md` — when reviewing concurrency, GenServers, supervision
- **Python**: `references/python/python_review_checklist.md` — security section

Tag findings using the framework's definitions: **Verified** requires a reproduction or complete repository-backed causal argument; **Likely** has local evidence with a stated unresolved assumption; **Uncertain** lacks enough evidence to establish the defect. A source URL or tool flag alone does not raise confidence.
Severity: **MAJOR**, escalate to **BLOCKER** for confirmed security vulnerabilities.

### Phase 3: Form

Check alignment with design principles and codebase conventions:

1. **Search for existing patterns first** — grep the codebase for similar implementations before flagging deviations. This is the highest-priority check.
2. Check module structure, import ordering, public API surface
3. Verify high cohesion / low coupling
4. **Verification**: Cite affected callers, repository rules, configured lint checks, or comparable implementations, and explain the concrete compatibility or maintenance consequence. Pattern matches and style guides establish conventions, not that a local abstraction is defective. Include external references only when they clarify applicable semantics or an adopted rule.

Load language-specific references conditionally:
- **Elixir**: `references/elixir/elixir_style_guide.md` — formatting, naming, module structure
- **Elixir**: `references/elixir/ecto_phoenix_patterns.md` — schemas, changesets, controllers, LiveView
- **Python**: `references/python/python_style_guide.md` — contextual design review; apply the project's configured tools, conventions, and library versions
- **Python**: `references/python/python_review_checklist.md` — code quality section

Severity: **MAJOR** for demonstrated design or compatibility problems, **MINOR** for evidenced convention violations. Personal preferences belong in Taste.

### Phase 4: Clarity

Assess whether code communicates its intent:

1. Check variable/function naming — are they self-documenting?
2. Check function length — can you understand at a glance?
3. Check comments — do they explain "why" not "what"?
4. Check public API documentation (@doc, docstrings)
5. Flag dead code, commented-out code, TODO debris
6. **Verification**: Show the affected usage or maintenance task and the concrete ambiguity or cost. Check the project's own conventions and cite local examples or rules. External naming/documentation guides are optional context; they do not establish a local defect.

Load conditionally:
- **Elixir**: `references/elixir/elixir_style_guide.md` — if not already loaded in Form phase
- **Python**: `references/python/python_style_guide.md` — if not already loaded in Form phase (docstrings, comments, naming sections)

Severity: **MINOR**.

### Phase 5: Edge Cases

Identify boundary conditions and failure modes:

1. Flag nil/None handling gaps, empty collection handling, boundary values
2. Check error paths — do they return meaningful errors?
3. Check external service failure handling (timeouts, retries)
4. Check concurrent access safety
5. **Verification**: Trace how a boundary input or failure can reach the code, accounting for caller contracts and guards. Show the resulting crash or degraded behavior with repository evidence or a focused reproduction. Document unresolved reachability assumptions. External references may clarify semantics but are not required to verify a local edge case.

Load conditionally:
- **Elixir**: `references/elixir/testing_practices.md` — for test coverage of edge cases

Severity: **BLOCKER** for crash-causing gaps, **MAJOR** for degraded behavior.

### Phase 6: Purpose

Verify code solves the stated task:

1. Compare PR description/ticket/commit messages against the actual diff
2. Flag scope creep — changes unrelated to stated purpose
3. Flag missing implementation — stated goals not addressed
4. Assess whether the approach is appropriate (not over/under-engineered)
5. **Verification**: This is a comparison phase — cite the PR description and specific diff sections as evidence.

Severity: **BLOCKER**.

### Phase 7: Taste

Note personal preferences. These are **non-blocking observations only**.

- Alternative approaches worth considering
- Stylistic preferences beyond established conventions
- "I would have done it differently" observations

Severity: **NITPICK** only. Must never block a merge. No confidence tagging needed.

### Phase 8: Test Coverage Assessment

Cross-cutting check across all phases:

- Happy path tested?
- Error cases and edge cases covered? (ties to Phase 5)
- Tests are behavior-based (test what code does, not how)?
- Test organization follows existing patterns? (ties to Phase 3)
- Test code gets the same review rigor as production code

## Output Format

Structure all reviews using this format. Use PASS only when required checks are complete and no blocking findings remain; FAIL for established blockers; INCOMPLETE when required verification is unavailable and no blocker is established.

````markdown
# PR Review: {branch_name}

**PR Number:** {number or "N/A"}
**Status:** {PASS / FAIL / INCOMPLETE}

## Summary
{3-5 sentences: what changed, quality assessment, overall verdict}

## Test Results
- **Tests:** {PASS / FAIL / SKIPPED / UNAVAILABLE}
- **Formatting/Linting:** {PASS / FAIL / SKIPPED / UNAVAILABLE}
- **Static Analysis:** {PASS / FAIL / SKIPPED / UNAVAILABLE}

## Verification Limitations
{Commands, outcomes, relevant output, and scope of checks; reasons for skipped/unavailable checks and what remains unverified, or "None". Include limitations even when status is FAIL.}

## Strengths
- {positive aspects}

## Issues Found

### {SEVERITY_EMOJI} {SEVERITY}: {Issue Title}
**File:** `{file_path}:{line_number}`
**Phase:** {Evidence | Reliability | Form | Clarity | Edge Cases | Purpose | Taste}
**Confidence:** {Verified | Likely | Uncertain}

**Current Code:**
```{lang}
{actual code from the file}
```

**Problem:** {what's wrong and why}
**Trigger:** {input, state, or event that exposes the issue}
**Execution Path:** {entry point/caller → relevant guards → affected operation; for conventions, the affected usage or maintenance task}
**Consequence:** {observable failure, impact, or concrete maintenance cost}
**Repository Evidence / Reproduction:** {file:line references and causal reasoning, or command/input with expected vs actual result}
**Uncertainty:** {unresolved assumptions and verification limits, or "None"}
**Reference (optional):** [{documentation name}]({URL}) — {specific semantics or adopted rule it establishes; omit when unnecessary}

**Suggested Fix:**
```{lang}
{concrete fix}
```
---

## PERFECT Summary

| Phase | Issues | Top Severity | Human Action Needed |
|-------|--------|-------------|-------------------|
| Evidence | {n} | {severity} | {None / action} |
| Reliability | {n} | {severity} | {None / action} |
| Form | {n} | {severity} | {None / action} |
| Clarity | {n} | {severity} | {None / action} |
| Edge Cases | {n} | {severity} | {None / action} |
| Purpose | {n} | {severity} | {None / action} |
| Taste | {n} | NITPICK | Author discretion |

## Recommendations
1. {prioritized recommendations}

## Issue Totals
**Total Issues:** {count}
- Blockers: {count}
- Major: {count}
- Minor: {count}
- Nitpicks: {count}
- By confidence: {verified} Verified, {likely} Likely, {uncertain} Uncertain
````

## Severity Levels

| Level | Emoji | Meaning |
|-------|-------|---------|
| BLOCKER | Red circle | Must fix before merge — broken functionality, security, test failures |
| MAJOR | Orange circle | Should fix before merge — demonstrated maintainability, compatibility, or test coverage problems |
| MINOR | Yellow circle | Should address — code smell, missing docs, minor improvements |
| NITPICK | White circle | Optional — style, formatting, preferences |

## Critical Requirements

- Every issue MUST include exact file path and line number
- Every issue MUST include the actual code snippet (not just the diff)
- Every issue MUST include a concrete fix with code example
- Every issue MUST include a Phase tag; every non-Taste issue MUST include a Confidence tag
- Every finding MUST explain its trigger, affected execution path, consequence, repository evidence or reproduction, and uncertainty
- Assign confidence from local evidence using the framework definitions; URLs, pattern matches, and tool warnings alone do not verify a defect
- Read the actual files — do not rely solely on diffs
- Check callers of modified functions to verify compatibility
- Focus on actionable, copy-paste-ready suggestions
- Acknowledge good work alongside issues
- Investigate uncertain findings through callers, contracts, tests, or a focused reproduction. State remaining uncertainty; do not make an uncertain candidate a blocking defect
- Use external references when they establish relevant semantics; ordinary local correctness findings do not require web verification
- Record failed or unavailable checks and continue useful inspection; preserve their effect on merge readiness without treating unavailable infrastructure as a code defect
