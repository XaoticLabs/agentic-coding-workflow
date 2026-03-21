#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_FILE="${REPO_ROOT}/hooks/hooks.json"

if [ ! -f "$HOOKS_FILE" ]; then
  echo "Error: hooks/hooks.json not found" >&2
  exit 1
fi

if ! python3 -c "import json; json.load(open('${HOOKS_FILE}'))" 2>/dev/null; then
  echo "Error: hooks/hooks.json is not valid JSON" >&2
  exit 1
fi

echo "hooks/hooks.json is valid JSON"

# Extract command-type hook paths
SCRIPTS=$(HOOKS_FILE="$HOOKS_FILE" python3 - <<'EOF'
import json, os

with open(os.environ["HOOKS_FILE"]) as f:
    data = json.load(f)

paths = []
hooks_map = data.get("hooks", {})
for event_hooks in hooks_map.values():
    for group in event_hooks:
        for hook in group.get("hooks", []):
            if hook.get("type") == "command":
                cmd = hook.get("command", "")
                if cmd:
                    paths.append(cmd)

for p in paths:
    print(p)
EOF
)

if [ -z "$SCRIPTS" ]; then
  echo "No command hooks found"
  exit 0
fi

ERRORS=0
TOTAL=0
while IFS= read -r script_path; do
  resolved="${script_path/\$\{CLAUDE_PLUGIN_ROOT\}/$REPO_ROOT}"
  TOTAL=$((TOTAL + 1))
  if [ ! -f "$resolved" ]; then
    echo "ERROR: $resolved (not found)"
    ERRORS=$((ERRORS + 1))
    continue
  fi
  if [ ! -x "$resolved" ]; then
    echo "ERROR: $resolved (not executable)"
    ERRORS=$((ERRORS + 1))
    continue
  fi
  # Check for binary file
  if LC_ALL=C grep -qP '\x00' "$resolved" 2>/dev/null; then
    echo "WARNING: $resolved (binary file, skipping shebang check)"
    continue
  fi
  # Check shebang
  first_line=$(head -1 "$resolved" 2>/dev/null || true)
  if [ -z "$first_line" ]; then
    echo "ERROR: $resolved (empty file)"
    ERRORS=$((ERRORS + 1))
  elif [[ "$first_line" == "#!"* ]]; then
    echo "OK: $resolved ($first_line)"
  else
    echo "ERROR: $resolved (no shebang)"
    ERRORS=$((ERRORS + 1))
  fi
done <<< "$SCRIPTS"

if [ "$ERRORS" -gt 0 ]; then
  echo "$ERRORS of $TOTAL hook scripts have issues"
  exit 1
else
  echo "All $TOTAL hook scripts valid"
fi
