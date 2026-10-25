# Shared Command Patterns

Reference for common patterns used across commands. Commands should reference this file instead of duplicating these blocks inline.

## Proportional Workflow

Use the least elaborate workflow that resolves material uncertainty and produces verifiable results. Add planning, clarification, isolation, or review as the task requires. Honor explicitly selected modes and project requirements.

| Task | Default workflow |
|------|------------------|
| Small, clear change | Inspect relevant context → implement → verify → report |
| Substantial feature | Clarify material uncertainty → maintain a concise plan → implement → verify → review |
| Long unattended task | Approve scope and limits → execute in isolation → preserve progress → verify outcomes → present evidence |

- Choose the initial path from the task's uncertainty, impact, reversibility, and scope. A short permissions change may require careful planning; a broad mechanical edit may be straightforward.
- Inspect relevant code and existing behavior first. Reassess the path when inspection reveals a material decision, dependency, or risk. Explain a change of path briefly; ask only when a decision needs user input.
- Proceed when the intended outcome, scope, material decisions, and verification approach are sufficiently clear. Ask questions whose answers could change implementation, acceptance criteria, or risk. Use repository evidence before asking the user, and state reasonable assumptions for minor details.
- Keep plans as short as useful. A conversational plan is sufficient unless a saved artifact is requested or needed for handoff or unattended execution. There are no question, edge-case, challenged-assumption, task-count, or document-length quotas.
- An explicit request to plan or write a spec authorizes generating that artifact. Additional confirmation is needed for a material scope or permission decision, or an explicitly selected approval step. Existing authorization persists.
- Interviews, detailed specs, teaching, plan approval, and acceptance-test approval are selected modes. Ordinary TDD does not itself select a test-approval gate or separate failing commits. Offer deeper modes when they would help without making them prerequisites for routine work.

- Use the current checkout for clear interactive work when project policy permits. Use an isolated worktree for unattended execution, concurrent changes, or an explicit isolation request; reuse an appropriate existing worktree.
- Verify every change using checks appropriate to its behavior and consequences, including project-required gates. Add behavioral or regression tests where useful; use direct inspection or targeted validation for changes without testable behavior. Report actual checks, outcomes, and unresolved limitations. Never imply an unrun check passed.
- Before unattended execution, establish scope, completion checks, iteration/time limits, allowed operations, and stop conditions. Preserve commits, task status, and recovery evidence. If a material decision exceeds the agreed scope, preserve progress and stop for input. Build authorization does not itself authorize publishing.

## Test and Verification Integrity

- Preserve the user's acceptance criteria. Tests are evidence for those criteria and can contain mistakes; an agent-authored test or RED commit is not human approval.
- Record human-approved acceptance tests by case/assertion, criterion, baseline commit or diff, and approval reference when that mode is selected. Protect their behavioral expectations, not entire files. New cases and fixture/helper corrections in the same file are allowed when existing expectations remain covered and runnable.
- Ordinary agent-authored tests may be corrected. For any changed expectation, deletion, skip/xfail, reduced input range, relaxed tolerance, snapshot update, or fixture/mock change that could weaken coverage, record the affected criterion, old/new expectation, evidence the old test was wrong, coverage retained or replaced, and validation results. Obtain independent review from a human or separate read-only reviewer before treating the change as verified; the author's own rationale is not review. A passing suite alone is insufficient justification.
- A human-approved behavioral expectation requires explicit human approval to change. Prepare the proposed correction and its evidence for that decision; an agent or reviewer cannot approve a scope reduction on the human's behalf. During unattended work, leave the task pending and stop for review if that approval is missing.
- Never alter tests, acceptance criteria, fixtures, mocks, discovery, runner configuration, lint rules, thresholds, or verification commands merely to get a pass. Do not swallow failures, forge evidence, special-case test inputs, or replace real behavior with mocks. Legitimate verification changes require the same rationale and independent review, plus human approval if they reduce agreed requirements.
- Prefer TDD for behavior changes and regression fixes when practical. Confirm failure for the missing behavior before the fix when useful; do not require separate failing commits for every task. Use direct validation for work without testable behavior and report checks that were not run.

## Git: Branch and Base Detection

Use this whenever you need the current branch and the main/master base branch:

```bash
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null)

# Find base branch (main or master)
for candidate in main master; do
  if git show-ref --verify --quiet "refs/heads/$candidate"; then
    BASE="$candidate"
    break
  fi
done
```

**On-base-branch guard:** If the command requires a feature branch, check after detection:
```bash
if [ "$BRANCH" = "$BASE" ]; then
  echo "ON_BASE_BRANCH"
fi
```

## Git: Repository Root

```bash
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

## Git: Changed Files on Branch

```bash
BASE=$(git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null)
CHANGED=$(git diff --name-only "$BASE"...HEAD)
```

## Git: Push with Upstream Tracking

```bash
git push -u origin "${BRANCH}"
```

## Project Context: Test and Lint Command Detection

Read overrides from `.claude/project-commands.json` before framework auto-detection:

```bash
TEST_CONFIG_STATUS=0
TEST_CMD=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project-commands.py" get "$REPO_ROOT" test) || TEST_CONFIG_STATUS=$?
LINT_CONFIG_STATUS=0
LINT_CMD=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project-commands.py" get "$REPO_ROOT" lint) || LINT_CONFIG_STATUS=$?
if [ "$TEST_CONFIG_STATUS" -gt 1 ] || [ "$LINT_CONFIG_STATUS" -gt 1 ]; then
  exit 1
fi
```

The JSON object accepts `build`, `test`, `lint`, `format`, and `run` keys with shell command strings. A status of `0` means the action is configured: use its value, including `null` or an empty string to disable it. A status of `1` means the file or key is missing: use the table below for that action. Other statuses indicate errors: stop and report the configuration path rather than skipping verification. Preserve command quoting, pipes, and operators when executing the resolved strings.

Generate initial configuration with `skills/ralph/scripts/generate-agents-md.sh`. Existing values are preserved on refresh. Move any custom commands from `.claude/AGENTS.md` into the JSON file; Markdown is no longer parsed for commands.

**Auto-detection order (only for missing keys):**

| Indicator | Runner | Test Command | Lint Command |
|-----------|--------|-------------|--------------|
| `mix.exs` | Mix (Elixir) | `mix test` | `mix format --check-formatted && mix credo` |
| `pyproject.toml` with `[tool.pytest]` | pytest | `pytest -v` | `ruff check .` |
| `pyproject.toml` with uv | pytest via uv | `uv run pytest -v` | `uv run ruff check .` |
| `setup.py` or `setup.cfg` | pytest | `python -m pytest -v` | `ruff check .` |
| `package.json` with `"test"` script | npm | `npm test` | `npm run lint` (if exists) |
| `Cargo.toml` | cargo | `cargo test` | `cargo clippy` |
| `go.mod` | go test | `go test ./...` | `go vet ./...` |
| `Makefile` with `test` target | make | `make test` | `make lint` (if exists) |
| `Gemfile` with `rspec` | rspec | `bundle exec rspec` | `bundle exec rubocop` |

## Input: Spec/Plan Loading

Standard pattern for locating spec and plan documents from `$ARGUMENTS`:

1. **If full path provided** — read it directly
2. **If slug or name provided** — search `.claude/specs/` for a matching file or directory
3. **If only a task number** — list `.claude/specs/`, use the single spec or ask user to pick
4. **Also check for corresponding plan** — for `.claude/specs/foo-spec.md`, look for `.claude/plans/foo.md`

## Input: File or Directory Handling

When a command accepts a file path, directory, or pattern:

```
- File path → read directly
- Directory → list contents and either process all or ask user to select
- Pattern/keyword → search for matching files, run all matches or ask if ambiguous
- Empty → use sensible default (full suite, current branch, etc.)
```

## Worktree Creation

Standard worktree setup for commands that need branch isolation:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"

# Ensure .claude/worktrees/ is gitignored
grep -q '\.claude/worktrees/' "${REPO_ROOT}/.gitignore" 2>/dev/null || \
  echo -e '\n.claude/worktrees/' >> "${REPO_ROOT}/.gitignore"

mkdir -p "$WORKTREE_BASE"

# Create worktree on a new branch
git worktree add -b "<branch-name>" "${WORKTREE_BASE}/<branch-name>"
```

## Error Handling Template

Standard error categories to address in every command's Error Handling section:

- **Input not found/invalid** — clear message about what was expected
- **Dependencies missing** — suggest installation or configuration
- **Blocked by state** — explain what's blocking and how to unblock
- **Partial failure** — report what succeeded, what failed, and how to recover

## Report Structure

Commands that produce a summary report should follow this structure:

```markdown
## [Action] Complete

### What Was Done
- (key changes or results)

### Status
- (pass/fail, counts, metrics)

### Next Steps
- (what the user should do next — specific commands if applicable)
```
