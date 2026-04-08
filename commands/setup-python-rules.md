---
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
effort: low
---

# Setup Python Rules

Installs Python conventions as `.claude/rules/python.md` in the consumer's project. Rules are adapted from Google Python Style Guide and PEP 8, focused on human-judgment checks that ruff, basedpyright, and CI won't catch.

## Input

$ARGUMENTS — Optional flags:
- `--preview` — show the rules without installing
- `--force` — overwrite existing rules file without asking
- Empty — install with confirmation

## Instructions

### Phase 1: Check Existing State

1. Check if `.claude/rules/python.md` already exists in the project:
   ```bash
   ls "${CLAUDE_PROJECT_DIR}/.claude/rules/python.md" 2>/dev/null
   ```

2. If it exists and `--force` not specified, read the existing file and ask:
   > A Python rules file already exists at `.claude/rules/python.md`. Options:
   > 1. **Merge** — add missing rules to your existing file
   > 2. **Replace** — overwrite with the latest version
   > 3. **Cancel** — keep your current file

3. Check what Python tooling the project uses:
   ```bash
   # Check pyproject.toml for tooling
   cat "${CLAUDE_PROJECT_DIR}/pyproject.toml" 2>/dev/null | grep -E '(ruff|basedpyright|pyright|mypy|black|flake8|pytest|pydantic)'
   ```

### Phase 2: Adapt Rules

Read the reference rules from the plugin:
```bash
cat "${CLAUDE_PLUGIN_ROOT}/.claude/rules/python.md"
```

Adapt based on what the project actually uses:
- If project uses `mypy` instead of `basedpyright`, adjust type checker references
- If project uses `pyright` instead of `basedpyright`, adjust accordingly
- If project uses `pip`/`poetry` instead of `uv`, adjust package manager references
- If project doesn't use `pydantic`, remove the Pydantic section
- If project uses `black` instead of ruff formatter, note that
- Keep all human-judgment rules regardless of tooling

### Phase 3: Install

1. If `--preview` flag, display the adapted rules and stop.

2. Ensure the directory exists:
   ```bash
   mkdir -p "${CLAUDE_PROJECT_DIR}/.claude/rules"
   ```

3. Write the adapted rules file to `${CLAUDE_PROJECT_DIR}/.claude/rules/python.md`

4. Report what was installed:
   > Installed Python rules at `.claude/rules/python.md`
   >
   > These rules are automatically loaded when editing `**/*.py` files and cover:
   > - Type design (abstract types, generics, Self)
   > - Naming (semantic quality beyond what ruff catches)
   > - Pydantic v2 patterns
   > - Function/class design guidelines
   > - Error handling judgment calls
   > - Async concurrency patterns
   > - Security checks easy to miss
   > - Logging conventions
   >
   > Rules focus on human-judgment items that ruff and basedpyright don't catch.

## Error Handling

- If the project has no Python files (`**/*.py`), warn but still install if user confirms
- If `.claude/` directory doesn't exist, create it along with `rules/`

## Example Usage

```
/setup-python-rules              # Install with confirmation
/setup-python-rules --preview    # Show rules without installing
/setup-python-rules --force      # Overwrite existing without asking
```
