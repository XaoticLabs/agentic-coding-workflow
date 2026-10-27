# Relay supervisor and graph-engineering cleanup

Baseline: `3b3ef2f`. Candidate: working-tree plugin version `2.0.0`.
This record describes controller/adapter validation, not a measured delivery
speedup or live model-quality comparison.

## Implemented contract

Relay replaces the Ralph shell executor with one fixed execution graph:
eligible task, implementation, configured checks, independent review, guarded
integration, and whole-graph acceptance. State has one controller writer;
workers have owned worktrees and separate CLI contexts. Failed/changed/conflicted
candidates are preserved rather than reset or automatically published.

The Ralph skill and shell launcher were removed without compatibility aliases.
Retired scheduling,
worker-edited-plan enforcement, automatic merge/cleanup paths, override scripts,
and their mode-specific tests were removed. Regression coverage was ported to
the new contract rather than retaining a second executor. The project-command
generator and historical stream/trace readers moved to shared `scripts/` paths.

Optional failure observations, explicit Jev-compatible classification, native
desktop notifications, readiness reporting, advisory early checks, runtime QA,
developer-experience review, and test auditing use the existing project and
verification contracts. Ordinary native sessions remain the default.

## Observed validation

| Check | Result |
| --- | --- |
| Complete deterministic repository suite | PASS: 387 tests, 98.19 seconds |
| Relay controller regressions | PASS, included in the full suite: success, rejected/malformed results, verification failures, frozen guidance, protected scope, stale source, bounded repair, one-call execution, timeouts/descendant termination, dependencies, concurrency, integration conflicts, resume/counter integrity, original limits, stop, exclusive ownership |
| Failure observations and lifecycle hooks | PASS: 25 cases included in the full suite; default no-network behavior, explicit model request/response contracts, unknown fallback, readiness without execution, advisory checks, and Linux notification argv |
| Ruff checks and formatting | PASS: all 21 changed Python files; final formatting preserved the AST of the five reformatted existing files |
| Registered hook scripts | PASS: nine registrations; quoted executable paths resolve |
| Changed shell entrypoints | PASS: syntax validation; the removed Ralph launcher is no longer an entrypoint |
| Skill structural diagnostics | PASS: all 12 entrypoints, no errors or warnings; not behavioral skill-effectiveness evidence |
| Relative Markdown links | PASS: maintained guides/commands/skills have no unresolved relative targets |
| Native `claude plugin validate .` | PASS with warnings, Claude Code 2.1.310 |
| `git diff --check` | PASS |

The complete test command was:

```bash
uv run --offline --cache-dir /tmp/agentic-coding-workflow-uv-cache --python 3.11 --with pytest python -m pytest -q
```

The cached Python 3.11 environment avoided modifying the host installation or
fetching dependencies. The host's default Python/pytest installation lacked a
pytest dependency. Model processes in controller tests were local fixtures;
project checks, Git/worktree operations, deadlines, and process termination were
actually exercised. Mocked decision responses establish adapter behavior only.

Native validation used an existing local CLI with its configuration isolated
under `/tmp/relay-cli-validation`. Raw output is retained locally at
`.claude/proofs/relay-validation/native-validation.txt`.

## Native warnings and limits

The root `CLAUDE.md` is a repository development guide; it is not automatically
installed as consuming-project context. Shipped workflows reference their own
skills and shared contracts. Command descriptions and quoted hook paths now
validate without their previous warnings.

The native validator's additional catalog-submission checks still report no
chosen license and no listing icon. Those checks do not fail ordinary plugin
validation. No license was assigned on the owner's behalf, and no catalog
submission was attempted.

Live Claude implementation/reviewer effectiveness, live Jev/Laya compatibility
and accuracy, native skill-trigger behavioral evaluations, actual desktop
notification delivery, and company onboarding/productivity outcomes are
**NOT_RUN**. No paid model run, external workflow-pack install, deployment,
publishing, schedule, or remote notification was started. Follow the existing
evaluation/pilot process before claiming improved quality, lower cost, or
reduced reviewer effort.

Prompts and local state are workflow controls, not an OS security boundary.
Shell-capable implementation/runtime nodes require external containment when a
hard filesystem/network boundary is needed. Classifier observations cannot
change acceptance, grant permission, waive checks, or authorize delivery.
