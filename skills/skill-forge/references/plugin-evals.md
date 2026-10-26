# Native plugin evaluations

Use this reference when adding or running behavioral cases. The maintained
format and options are documented in [Claude Code plugin evals](https://code.claude.com/docs/en/plugin-evals).
The command requires Claude Code v2.1.269 or later and model access.

## Cases and graders

Keep reusable cases in the plugin's `evals/<case>/` directory:

```text
evals/<case>/
├── prompt.md
└── graders/
    └── outcome.md
```

`prompt.md` contains a realistic user request, optionally preceded by frontmatter
with `name`, `tags`, `allowed_tools`, `max_turns`, and `timeout_seconds`. Grant only
the tools the case needs. Preserve the same task and constraints in both arms.

A grader is a Markdown file with frontmatter such as `type: llm` and a body
describing the observable passing outcome. Native deterministic types include
`regex`, `tool_used`, `tool_order`, and `file_exists`. For file contents, point a
regex `target` or model judge `focus` to `{source: file, path: relative/path}`.
Do not grade only a claim of success when the output can be inspected.

Use model judges for semantic quality, and deterministic tests outside the model
run for script exit codes, environment state, data preservation, and other
repository contracts. Regex presence alone cannot prove a script works.

## Tuning and final holdout

Tag every case with exactly one split: `tuning` or `holdout`. Existing cases
already used to guide this plugin belong to tuning. Keep the case, fixtures,
and graders in version control; do not move a known failure into holdout to
make the next score look independent. The repository's case inventory and
reporting policy are in `${CLAUDE_PLUGIN_ROOT}/evals/README.md`.

Use tuning cases to compare descriptions and instructions. Decide the success
criteria and freeze the candidate and graders before running holdout. Report
all holdout outcomes, including failures and incomplete runs. If a holdout
result informs another change, mark that set as consumed, treat it as tuning,
and reserve fresh cases for the next final comparison. Version control makes
cases reproducible; it does not make repeatedly inspected cases independent.

## Running and interpreting results

From the trusted plugin checkout, run tuning cases with local reports:

```bash
claude plugin eval . --tag tuning --allow-tools Write Edit --no-publish
```

After freezing the candidate and criteria, run final holdout separately:

```bash
claude plugin eval . --tag holdout --allow-tools Write Edit --no-publish
```

Do not use an unfiltered suite command during tuning: it includes holdout.

This suite drafts files but does not need shell execution. Read-only tools must
also appear in each case's `allowed_tools`; native evals require separate
`--allow-tools` grants for writes and shell commands. For shell-based fixtures,
use a `case.yaml` with `context.scaffold_script` and explicitly pass `--scaffold`.

Native evaluation normally runs each case three times with the plugin and three
times without it. Compare outcome graders across both arms; plugin-specific
invocation graders diagnose triggering rather than proving an outcome improved.
Record the candidate revision, case/graders revision, CLI version, execution
and judge models, run count per arm, correctness per case and arm, cost, and
duration when comparing changes. Separate triggering diagnostics from outcome
scores. A single exploratory run is not a reliable quality claim.

Choose cases and cost limits to fit the authorized evaluation. The runner's
`--max-cost-usd` checks estimated spend before starting runs; already running
calls can exceed it. An interrupted or partial suite is incomplete evidence.
Keep sanitized benchmark summaries under `evals/benchmarks/` in version control;
`evals/results/` remains ignored runtime output. Include the exact command,
failures, missing runs, limitations, and local report path or retained artifact
location. When runs are unavailable, record `NOT_RUN` and the reason without
inventing scores. Preserve useful failure evidence before removing a disposable
workspace; never delete the case definitions or benchmark history as cleanup.

Do not generate a second custom evaluation engine or treat native eval scores
as a substitute for `python3 -m pytest -q`. Native schema checks, behavioral
evaluations, and deterministic repository tests answer different questions.
