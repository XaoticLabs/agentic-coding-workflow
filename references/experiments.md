# Batch investigation and comparison

For uncertain debugging, performance work, or design choices, build a repeatable
comparison before asking the user to steer every attempt. Define outcomes,
constraints, plausible alternatives, and an observable check for each. Let
uncertainty determine the number of alternatives; no fixed quota applies.

Save a matrix under `.claude/experiments/`, for example:

```json
{
  "version": 1,
  "experiments": [
    {
      "name": "baseline",
      "criterion": "representative workload passes correctness assertions",
      "command": ["python3", "bench.py", "--variant", "baseline"],
      "runs": 5,
      "timeout_seconds": 60
    },
    {
      "name": "candidate",
      "criterion": "same workload and correctness assertions",
      "command": ["python3", "bench.py", "--variant", "candidate"],
      "runs": 5,
      "timeout_seconds": 60
    }
  ]
}
```

From the consuming project:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-experiments.py" .claude/experiments/matrix.json
```

Outputs include raw stdout/stderr, exits, timings, JSON, and a filterable
`comparison.html` under `.claude/experiments/<run>/`. Commands are argument arrays;
use an explicit `bash -o pipefail -c` array when shell syntax is necessary.
Optional fields: `cwd` (inside the project), `runs` (1–50), `timeout_seconds`,
and `expected_exit` (default 0).

Execution is sequential on the current machine. Use the
[private environment](execution-environments.md) for setup/services or separate
candidates. Keep workloads fixed and interleave orders when caches/drift matter.
Wall time includes process startup. Exit status checks only the command's own
assertions; interpret metrics from output. Source changes invalidate a
fixed-source comparison.

For visual alternatives, generate a project-native preview with controls to
compare/combine variants, and exercise the selected result. The runner's HTML
compares command outcomes; it does not generate visual alternatives itself.
