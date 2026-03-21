# Deterministic Script Patterns

## Table of Contents

1. [Why Scripts Matter](#why-scripts-matter)
2. [When to Script vs When to Leave to AI](#when-to-script)
3. [Bash Patterns](#bash-patterns)
4. [Python Patterns](#python-patterns)
5. [Error Handling Conventions](#error-handling-conventions)
6. [Portability Checklist](#portability-checklist)
7. [Working with Claude's Bash Tool](#working-with-claudes-bash-tool)

---

## Why Scripts Matter

Scripts are the most context-efficient resource in a skill. A 300-line Python validation script costs **zero context tokens** — it executes via the Bash tool and only the output enters the conversation. Compare that to putting the same logic inline in SKILL.md, which would consume ~400 tokens of context on every invocation whether needed or not.

Beyond context efficiency, scripts provide:
- **Determinism** — Same input always produces same output. No hallucinated file paths, no creative reinterpretation of validation rules.
- **Speed** — A script runs in milliseconds. An AI reasoning through the same logic takes seconds.
- **Testability** — Scripts can be tested independently outside of Claude.
- **Reliability** — No risk of the AI skipping a step or reordering operations.

---

## When to Script

### Script It (Deterministic)

| Operation | Why Script |
|-----------|-----------|
| File/directory scaffolding | Exact structure matters, no creativity needed |
| Input validation | Rules are fixed, checking is mechanical |
| Format conversion | Transformation is algorithmic |
| Data extraction (structured) | Parsing rules are deterministic |
| Git operations | Commands are exact, order matters |
| Dependency checks | Binary: installed or not |
| Aggregation & statistics | Math doesn't need AI |
| Template rendering | Fill-in-the-blanks from data |

### Leave to AI (Judgment Required)

| Operation | Why AI |
|-----------|--------|
| Code review feedback | Requires understanding intent |
| Architecture decisions | Needs context and tradeoffs |
| Natural language generation | Creative output |
| Debugging novel issues | Requires reasoning |
| Choosing between approaches | Needs judgment |
| Explaining concepts | Audience-dependent |

### The Hybrid Pattern

The most powerful skills combine both. The script handles the mechanical parts and the AI handles the judgment parts:

```
1. Script detects project type and collects facts
2. AI reads facts and applies judgment
3. Script formats and validates the output
4. AI presents results to the user
```

---

## Bash Patterns

### Scaffolding Script Template

```bash
#!/usr/bin/env bash
# scaffold-thing.sh — Create a [thing] directory structure
# Usage: scaffold-thing.sh <name> [target-dir]
set -euo pipefail

# --- Argument handling ---
NAME="${1:?Usage: scaffold-thing.sh <name> [target-dir]}"
TARGET="${2:-.}"

# --- Validate name format ---
if ! echo "$NAME" | grep -qE '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'; then
    echo "Error: Name must be kebab-case" >&2
    exit 1
fi

# --- Check target doesn't exist ---
DEST="$TARGET/$NAME"
if [ -d "$DEST" ]; then
    echo "Error: $DEST already exists" >&2
    exit 2
fi

# --- Create structure ---
mkdir -p "$DEST"/{src,tests,docs}
cat > "$DEST/config.json" <<EOF
{
  "name": "$NAME",
  "version": "0.1.0"
}
EOF

echo "Created: $DEST"
```

**Key patterns:**
- `set -euo pipefail` — fail on errors, undefined vars, pipe failures
- `${1:?message}` — required argument with error message
- `${2:-.}` — optional argument with default
- Validate inputs before acting
- Check for existing files/dirs to avoid overwriting
- Output what was created

### Validation Script Template

```bash
#!/usr/bin/env bash
# validate-thing.sh — Check a [thing] for correctness
# Usage: validate-thing.sh <path>
# Exit: 0 = valid, 1 = invalid (errors on stderr), 2 = bad args
set -euo pipefail

TARGET="${1:?Usage: validate-thing.sh <path>}"
ERRORS=0

check() {
    local desc="$1"
    shift
    if ! "$@" 2>/dev/null; then
        echo "FAIL: $desc" >&2
        ((ERRORS++))
    fi
}

check "config.json exists" test -f "$TARGET/config.json"
check "config.json is valid JSON" python3 -c "import json; json.load(open('$TARGET/config.json'))"
check "name is set" test -n "$(python3 -c "import json; print(json.load(open('$TARGET/config.json')).get('name',''))")"

if [ "$ERRORS" -gt 0 ]; then
    echo "$ERRORS check(s) failed" >&2
    exit 1
fi
echo "All checks passed"
```

**Key pattern:** The `check()` function encapsulates test-and-report so adding new checks is trivial.

### Git Integration Pattern

```bash
#!/usr/bin/env bash
# git-info.sh — Collect git state as JSON
# Usage: git-info.sh [repo-path]
set -euo pipefail

REPO="${1:-.}"
cd "$REPO"

# Verify this is a git repo
if ! git rev-parse --git-dir &>/dev/null; then
    echo '{"error": "not a git repository"}'
    exit 1
fi

# Collect state
BRANCH=$(git branch --show-current 2>/dev/null || echo "detached")
SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "none")
DIRTY=$(git status --porcelain | wc -l | tr -d ' ')
MODIFIED=$(git diff --name-only 2>/dev/null | head -20)

# Output as JSON (no jq dependency)
cat <<EOF
{
  "branch": "$BRANCH",
  "sha": "$SHA",
  "dirty_files": $DIRTY,
  "modified": [$(echo "$MODIFIED" | sed 's/.*/"&"/' | paste -sd, - )]
}
EOF
```

**Key pattern:** Output JSON for machine readability. Avoid jq dependency — generate JSON with heredocs and basic string manipulation.

### Dependency Check Pattern

```bash
#!/usr/bin/env bash
# check-deps.sh — Verify required tools are installed
set -euo pipefail

MISSING=()

require() {
    if ! command -v "$1" &>/dev/null; then
        MISSING+=("$1")
    fi
}

require git
require python3
require jq        # optional: only if needed

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Missing required tools: ${MISSING[*]}" >&2
    echo "Install them before continuing." >&2
    exit 1
fi
echo "All dependencies satisfied"
```

---

## Python Patterns

### Validation Script Template

```python
#!/usr/bin/env python3
"""validate-thing.py — Validate [thing] against quality rules.

Usage: python validate-thing.py <path> [--json] [--verbose]
Exit:  0 = score >= 70, 1 = score < 70, 2 = bad args
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Finding:
    severity: str  # "error", "warning", "info"
    message: str
    suggestion: str = ""


@dataclass
class Category:
    name: str
    score: float
    weight: float
    findings: list = field(default_factory=list)


def check_something(path: Path) -> Category:
    """One check category — returns score and findings."""
    cat = Category(name="something", score=100, weight=0.25)

    if not (path / "important.txt").exists():
        cat.score -= 30
        cat.findings.append(Finding(
            "error",
            "Missing important.txt",
            "Create important.txt with the required configuration"
        ))

    return cat


def validate(path: Path) -> dict:
    categories = [check_something(path)]
    total_weight = sum(c.weight for c in categories)
    score = sum(c.score * c.weight for c in categories) / total_weight

    return {
        "score": round(score, 1),
        "categories": [
            {"name": c.name, "score": c.score, "findings": [
                {"severity": f.severity, "message": f.message, "suggestion": f.suggestion}
                for f in c.findings
            ]}
            for c in categories
        ]
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = validate(args.path)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"Score: {results['score']}/100")
        for cat in results["categories"]:
            for f in cat["findings"]:
                print(f"  [{f['severity']}] {f['message']}")

    sys.exit(0 if results["score"] >= 70 else 1)
```

**Key patterns:**
- Dataclasses for structured findings (no external dependencies)
- Category-based scoring with weights
- Both JSON and human-readable output modes
- Exit code reflects pass/fail

### Data Processing Template

```python
#!/usr/bin/env python3
"""process-data.py — Transform input data deterministically.

Usage: python process-data.py <input-file> [--output <path>]
"""

import argparse
import json
import sys
from pathlib import Path


def process(data: dict) -> dict:
    """Pure transformation — no side effects, no AI needed."""
    result = {
        "processed": True,
        "item_count": len(data.get("items", [])),
        "items": sorted(data.get("items", []), key=lambda x: x.get("name", "")),
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", type=Path)
    parser.add_argument("--output", "-o", type=Path, default=None)
    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"Error: {args.input_file} not found", file=sys.stderr)
        sys.exit(1)

    data = json.loads(args.input_file.read_text())
    result = process(data)
    output = json.dumps(result, indent=2)

    if args.output:
        args.output.write_text(output)
        print(f"Written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
```

**Key patterns:**
- Pure function for the core logic (testable, predictable)
- File I/O in main(), not in the logic
- Both stdout and file output modes
- Early validation of inputs

---

## Error Handling Conventions

### Exit Codes

Use consistent exit codes across all scripts:

| Code | Meaning | When |
|------|---------|------|
| 0 | Success | Operation completed normally |
| 1 | Failure | Operation failed (check stderr for details) |
| 2 | Bad arguments | Missing/invalid arguments, wrong usage |
| 3 | Environment issue | Missing dependency, permissions, etc. |

### Stderr for Errors, Stdout for Data

Scripts called by Claude's Bash tool should:
- Print results/data to **stdout** (this is what Claude sees)
- Print errors/warnings to **stderr** (visible but separated)
- Never mix diagnostic output with data output

```bash
# Good
echo "Result: 42"                    # stdout — the answer
echo "Warning: slow network" >&2     # stderr — diagnostic

# Bad
echo "Processing..."                 # Pollutes stdout with non-data
echo "Result: 42"
```

### Failing Gracefully

When a script fails, provide actionable context:

```bash
if ! git rev-parse --git-dir &>/dev/null; then
    echo "Error: Not a git repository" >&2
    echo "Run this script from within a git repo, or pass the repo path as an argument" >&2
    exit 3
fi
```

Include: what went wrong, what the user can do about it.

---

## Portability Checklist

Scripts in skills run across different machines. Follow these rules:

### Bash Scripts

- [ ] Use `#!/usr/bin/env bash` (not `#!/bin/bash` — different path on macOS vs Linux)
- [ ] Use `set -euo pipefail` for safety
- [ ] Don't use bash 4+ features (macOS ships bash 3.2 by default) unless checking first
  - No associative arrays (`declare -A`)
  - No `${var,,}` lowercase syntax
  - No `readarray` / `mapfile`
- [ ] Use `command -v` not `which` for dependency checks
- [ ] Quote all variable expansions (`"$var"` not `$var`)
- [ ] Use `$(...)` not backticks for command substitution
- [ ] Avoid GNU-specific flags (`sed -i ''` on macOS vs `sed -i` on Linux)
  - Safest: write to temp file and `mv`
- [ ] Don't assume `jq` is installed — use Python for JSON if needed
- [ ] Test with both macOS and Linux if possible

### Python Scripts

- [ ] Use `#!/usr/bin/env python3`
- [ ] Stick to standard library — no pip dependencies
  - `json`, `pathlib`, `argparse`, `re`, `dataclasses`, `subprocess` cover 90% of needs
- [ ] Minimum Python 3.8 compatibility (widely available)
  - OK: f-strings, dataclasses, `pathlib`, walrus operator
  - Careful: `match` statements (3.10+), `type` aliases (3.12+)
- [ ] Use `Path` objects not string paths
- [ ] Handle encoding: `encoding='utf-8'` in file operations

---

## Working with Claude's Bash Tool

Claude executes scripts via its Bash tool, which has specific characteristics:

### What Claude Sees

- **stdout** — The primary output. Claude reads this to understand results.
- **stderr** — Also visible, but typically treated as diagnostic/warning info.
- **exit code** — Claude checks this. Non-zero signals failure.
- **The script source is NOT loaded** — The script file is executed but its contents don't enter the conversation context. This is why scripts are context-free.

### Designing for Bash Tool Execution

**Structured output is best.** JSON output lets Claude parse results precisely:

```bash
# Good — Claude can parse this
echo '{"status": "pass", "score": 85, "issues": 2}'

# OK — Claude can understand this
echo "Score: 85/100 (2 issues found)"

# Poor — Claude has to parse unstructured text
echo "Well, I checked the thing and it was mostly OK..."
```

**Keep output concise.** Long outputs consume context. If a script produces a lot of data, summarize in stdout and write details to a file:

```bash
# Process and summarize
TOTAL=$(wc -l < results.json)
ERRORS=$(grep -c '"error"' results.json)
echo "Processed $TOTAL items, $ERRORS errors. Details: results.json"
```

**Use `${CLAUDE_SKILL_DIR}` for paths.** This environment variable points to the skill's root directory, making scripts portable:

```markdown
## In SKILL.md:
Run validation: `bash ${CLAUDE_SKILL_DIR}/scripts/validate.sh <path>`
```

**Avoid interactive prompts.** The Bash tool doesn't support stdin interaction. Scripts must be fully non-interactive — take all input via arguments or environment variables.

### Script Invocation Patterns in SKILL.md

```markdown
## Scripts

### Scaffolding
Create the project structure:
bash ${CLAUDE_SKILL_DIR}/scripts/scaffold.sh <name> <target-dir>

### Validation
Check skill quality (returns JSON with --json flag):
python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py <skill-dir> --json

### Detection
Identify project type and collect metadata:
bash ${CLAUDE_SKILL_DIR}/scripts/detect.sh <project-dir>
The output JSON contains `type`, `language`, and `framework` fields.
Use these to select the appropriate reference file.
```

Note: Document what the script outputs so the AI knows how to interpret results without reading the script source.
