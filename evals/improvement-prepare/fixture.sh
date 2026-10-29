#!/usr/bin/env bash
set -euo pipefail
printf '.claude/\n' > .gitignore
printf 'Project-required checks: python3 check.py.\n' > PROJECT.md
printf 'print("fixture check passed")\n' > check.py
mkdir -p .claude
printf '{"test":"python3 check.py","lint":null}\n' > .claude/project-commands.json
git init --quiet
git add .gitignore PROJECT.md check.py
git -c user.name=Fixture -c user.email=fixture@example.com commit --quiet -m 'fixture: initial project'
