# Model selection and provenance

Use the team's chosen strongest available model for substantial implementation
and review. Keep selectors configurable; availability changes. Do not silently
substitute a cheaper family to reduce token spend.

Ralph build/planning/harvest, independent evaluation/review, and merge resolution share
`scripts/workflow_models.py`. Precedence is:

1. `WORKFLOW_BUILD_MODEL`, `WORKFLOW_EVALUATOR_MODEL`, or `WORKFLOW_MERGE_MODEL`.
2. `WORKFLOW_MODEL` for the whole workflow.
3. `ANTHROPIC_MODEL` from the invoking environment.
4. Native Claude configuration, with no plugin `--model` override.

For example, `export WORKFLOW_MODEL=best` selects the current native `best`
alias where supported. Full provider IDs work too. Model settings survive tmux
launches, including removal of stale overrides in an existing server.

A separate process cannot infer an interactive session's `/model` selection.
Set `WORKFLOW_MODEL` when that choice must carry into separate workers.
Interactive roles otherwise retain their native selection behavior.
New spawned roles and generic tmux panes use the same model policy; resumed
sessions retain their saved model selection without a new role-specific override.

Stream traces record observed model IDs from initialization and assistant
messages. Evaluator verdicts retain requested selectors and observed IDs from
the CLI result. Missing IDs mean unknown; an alias alone does not identify the
model that answered. Use explicit version IDs for final comparisons and retain
native evaluation reports with execution and judge data.

Compare task acceptance, failed attempts, human correction effort, elapsed time,
and total spend. A lower token price alone does not establish better economics.

Source: [native model configuration](https://code.claude.com/docs/en/model-config).
