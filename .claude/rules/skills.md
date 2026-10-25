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
