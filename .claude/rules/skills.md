---
paths:
  - "skills/**/*"
---

# Skill Development Rules

## SKILL.md Frontmatter
- `name`: lowercase, hyphenated
- `description`: concise capability and relevant use cases; distinguish likely near-misses. Evaluate triggering with representative prompts rather than requiring exhaustive synonyms.
- `allowed-tools`: minimum prompt-free approval grants needed, not a restriction on all available tools (see CLI `--tools` / `--disallowedTools`)
- `user-invocable: true` if it's a slash command skill
- `disable-model-invocation: true` for workflows requiring explicit timing or side-effect control, such as publishing, launching workers, merging, or worktree cleanup. Keep them user-invocable. `user-invocable: false` means model-only invocation; it does not disable a workflow or prevent automatic execution.
- Prefer a skill for new workflows. When consolidating a duplicate command/skill name, preserve its invocation and arguments in one skill and remove the duplicate command file.

## Directory Structure
```
skills/<name>/
├── SKILL.md          # Orchestrator — workflow logic, conditional loading
├── scripts/          # Deterministic operations (bash/python)
│   └── *.sh / *.py
└── references/       # Domain knowledge, loaded conditionally
    └── *.md
```

## Progressive Disclosure
- Don't dump all references at the top — load them when the phase needs them
- Use conditional loading: "If the project uses Elixir, read references/elixir_patterns.md"
- Challenge every paragraph: "Does this justify its token cost?"

## Scripts
- Scripts handle deterministic work: file operations, git commands, parsing, validation
- Always use `${CLAUDE_PLUGIN_ROOT}` for paths to plugin files
- Always use `${CLAUDE_PROJECT_DIR}` for paths to the consuming project
- Make scripts executable (`chmod +x`) with proper shebangs
- Scripts should be idempotent where possible

## Evaluation Evidence
- Structural diagnostics and native schema validation establish standards compliance, not behavioral effectiveness.
- Keep representative native eval cases, fixtures, graders, and sanitized benchmark summaries in version control. Keep raw reports under ignored `evals/results/`; preserve useful evidence before cleaning disposable workspaces.
- Tune only against `tuning` cases. Freeze candidates and criteria before final `holdout` runs. If holdout feedback guides an edit, treat those cases as tuning and reserve fresh final cases. See `evals/README.md`.
