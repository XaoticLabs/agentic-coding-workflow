---
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
effort: low
---

# Test — Detect and Run Project Tests

Detects the project's test framework, runs the test suite (or a subset), and reports results in a structured format.

## Input

$ARGUMENTS - Either:
- Empty — runs the full test suite
- A file path (e.g., `test/auth_test.exs`) — runs only that test file
- A directory (e.g., `test/models/`) — runs tests in that directory
- A pattern (e.g., `auth`) — finds and runs matching test files
- `--changed` — runs tests only for files changed on this branch
- `--failing` — re-runs only previously failing tests (if test runner supports it)

## Instructions

### Phase 1: Detect Test Runner

Check for project indicators in order of specificity:

```bash
# Check what exists at the repo root
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
ls "$REPO_ROOT"
```

**Detection order:**

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

If no test runner detected, report: "No test framework detected. Add a test command to your project or run tests manually."

Also check for `.claude/AGENTS.md` which may specify custom test/lint commands:
```bash
if [ -f "${REPO_ROOT}/.claude/AGENTS.md" ]; then
  grep -A2 -i "test command" "${REPO_ROOT}/.claude/AGENTS.md"
  grep -A2 -i "lint command" "${REPO_ROOT}/.claude/AGENTS.md"
fi
```

Custom commands from `AGENTS.md` take precedence over auto-detection.

### Phase 2: Determine Scope

**Full suite (no arguments):**
Run the detected test command as-is.

**Specific file or directory:**
Append the path to the test command:
- `mix test test/auth_test.exs`
- `pytest test/models/`
- `npm test -- test/auth.test.js`
- `cargo test --test auth`
- `go test ./pkg/auth/...`

**Pattern match:**
Find matching test files:
```bash
# Find test files matching the pattern
find "$REPO_ROOT" -type f \( -name "*${PATTERN}*test*" -o -name "*test*${PATTERN}*" -o -name "*${PATTERN}*spec*" -o -name "*spec*${PATTERN}*" \) \
  ! -path '*/node_modules/*' ! -path '*/_build/*' ! -path '*/target/*' ! -path '*/.venv/*' ! -path '*/.claude/*'
```

If multiple matches, run all of them. If none, report: "No test files matching '${PATTERN}' found."

**--changed flag:**
Find files changed on this branch and map to their test files:
```bash
# Get changed files
BASE=$(git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null)
CHANGED=$(git diff --name-only "$BASE"...HEAD)
```

For each changed source file, look for a corresponding test file:
- `src/auth/handler.py` → `test/auth/test_handler.py` or `tests/test_auth_handler.py`
- `lib/my_app/auth.ex` → `test/my_app/auth_test.exs`
- `src/components/Auth.tsx` → `src/components/Auth.test.tsx` or `__tests__/Auth.test.tsx`

Run the discovered test files. If no test files found for the changes, fall back to running the full suite and note why.

**--failing flag:**
Use the runner's built-in failing test support if available:
- `mix test --failed` (Elixir)
- `pytest --lf` (Python)
- `npm test -- --onlyFailures` (Jest)

Otherwise, fall back to the full suite.

### Phase 3: Run Tests

Run the test command:

```bash
# Run with a timeout to avoid hanging
timeout 300 <test-command> 2>&1
TEST_EXIT=$?
```

Capture the full output.

### Phase 4: Run Lint (if available)

If a lint command was detected, run it:

```bash
timeout 120 <lint-command> 2>&1
LINT_EXIT=$?
```

### Phase 5: Report

Output a structured report:

```markdown
## Test Results

**Runner:** <detected runner> (`<test command>`)
**Scope:** <full suite / specific file / changed files / pattern match>

### Tests
- **Status:** PASS / FAIL
- **Total:** <count>
- **Passed:** <count>
- **Failed:** <count>
- **Skipped:** <count>
- **Duration:** <time>

### Failures
(Only if there are failures)

**<test name>**
File: `<file>:<line>`
```
<error output>
```

### Lint
- **Status:** PASS / FAIL / SKIPPED
- **Issues:** <count>

### Lint Issues
(Only if there are issues)

**<file>:<line>** — <description>
```

Parse the test output to extract counts where possible. Different runners format output differently:

- **mix test:** Look for `X tests, Y failures` at the end
- **pytest:** Look for `X passed, Y failed` summary line
- **npm test:** Look for `Tests: X passed, Y failed`
- **cargo test:** Look for `test result: ok. X passed; Y failed`
- **go test:** Look for `ok` or `FAIL` lines per package

If the output can't be parsed reliably, show the raw output under the structured report.

## Error Handling

- **Test command not found:** Suggest installing the test framework
- **Timeout:** Report which tests were still running and suggest running a subset
- **Permission denied:** Suggest `chmod +x` or checking dependencies
- **Compilation errors (not test failures):** Distinguish from test failures — report as "Build failed" not "Tests failed"

## Example Usage

```
/agentic-coding-workflow:test
```
Runs the full test suite.

```
/agentic-coding-workflow:test test/auth_test.exs
```
Runs a specific test file.

```
/agentic-coding-workflow:test auth
```
Finds and runs all test files matching "auth".

```
/agentic-coding-workflow:test --changed
```
Runs tests for files changed on this branch.

```
/agentic-coding-workflow:test --failing
```
Re-runs only previously failing tests.
