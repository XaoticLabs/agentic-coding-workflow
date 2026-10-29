#!/usr/bin/env bash
set -euo pipefail
mkdir -p .claude/improvements/context-loading/evidence
printf '.claude/\n__pycache__/\n' > .gitignore
printf 'Use python3 check.py for required verification.\n' > PROJECT.md
printf 'def normalize(values):\n    return sorted(values)\n' > work.py
cat > check.py <<'PY'
from work import normalize
import sys

if normalize([2, 1]) != [1, 2]:
    print("PRODUCT_CHECK_FAILED: normalize must sort values")
    sys.exit(1)
print("PRODUCT_CHECK_PASSED")
PY
printf '{"test":"python3 check.py","lint":null}\n' > .claude/project-commands.json
git init --quiet
git add .gitignore PROJECT.md work.py check.py
git -c user.name=Fixture -c user.email=fixture@example.com commit --quiet -m 'fixture: passing baseline'
python3 check.py > .claude/improvements/context-loading/evidence/baseline.log 2>&1
printf 'def normalize(values):\n    return list(values)\n' > work.py
if python3 check.py > .claude/improvements/context-loading/evidence/candidate.log 2>&1; then
    echo 'Expected a failed candidate fixture' >&2
    exit 1
fi
python3 - <<'PY'
import json
from pathlib import Path
import subprocess

directory = Path('.claude/improvements/context-loading')
record = {
    "version": 1,
    "id": "context-loading",
    "idea": "Reduce repeated context while preserving required verification",
    "stage": "compare",
    "next_action": "Recheck the candidate with python3 check.py and retain the outcome; native evaluations are unavailable.",
    "baseline": {
        "source": {"revision": subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(), "scope": "revision"},
        "accepted_experiment": None
    },
    "candidate": {"source": None},
    "plan": {
        "hypothesis": "Less context reduces turnaround without changing behavior.",
        "success_criteria": ["Required check passes and comparable trials support a turnaround benefit."],
        "protections": ["python3 check.py must pass without changing its expectations."],
        "authorized_budget_usd": None
    },
    "evidence": [
        {"arm": "baseline", "outcome": "passed", "report": "evidence/baseline.log"},
        {"arm": "candidate", "outcome": "failed", "report": "evidence/candidate.log"}
    ],
    "decisions": [{"outcome": "revise", "reason": "Candidate failed; latency has not been measured."}]
}
(directory / 'experiment.json').write_text(json.dumps(record, indent=2) + '\n')
(directory / 'report.md').write_text('Candidate check failed. Native evaluations NOT_RUN. Resume verification; do not promote the baseline.\n')
PY
