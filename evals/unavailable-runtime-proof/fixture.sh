#!/usr/bin/env bash
set -euo pipefail
mkdir -p .claude
printf 'Please recieve this message.\n' > message.txt
printf '{"test":"workflow-missing-integration-runtime-8b4f --verify","lint":null}\n' > .claude/project-commands.json
