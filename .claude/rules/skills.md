---
globs:
  - "skills/**/*"
description: Rules for building and modifying skills
---

# Skill Development Rules

## SKILL.md Frontmatter
- `name`: lowercase, hyphenated
- `description`: exhaustive trigger phrases — this is the most important field. Include exact user phrases, synonyms, adjacent concepts, and anti-patterns (when NOT to trigger)
- `allowed-tools`: minimum set needed
- `user-invocable: true` if it's a slash command skill

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
