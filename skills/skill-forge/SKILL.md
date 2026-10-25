---
name: skill-forge
description: |
  Create, repair, and evaluate Claude Code skills. Use when a user asks to build
  a reusable skill, edit a SKILL.md workflow, improve skill triggering, reduce
  unnecessary context loading, or test whether a skill improves task outcomes.
  Ordinary prose editing or explaining a workflow does not require a new skill.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
effort: high
user-invocable: true
---

# Skill Forge

Build skills that change useful decisions and improve observable outcomes.
Use scripts for repeated deterministic operations, references for conditional
detail, and SKILL.md for the essential workflow. A short, self-contained skill
does not need scripts or references.

## Phase 1: Establish the task

Use the request and existing context to identify the capability, trigger,
expected output, and material constraints. Ask only about unresolved choices
that affect the result. Preserve the user's requested location, tools, scope,
and authorization; do not turn a one-off writing request into a skill.

For an existing skill, inspect SKILL.md and the resources used by the relevant
mode. Capture a demonstrated failure or representative request before changing
the workflow. Do not load all references just to inventory them.

## Phase 2: Build or repair

Write a discriminating `name` and `description`: explain the capability and when
it applies. Preserve supported frontmatter and existing invocation policy unless
the user asks to change them. `allowed-tools` grants prompt-free approval; it
does not restrict the complete tool set.

Include the instructions needed to make the actual task work. Avoid generic
advice, word-count targets, required numbers of headings, and exhaustive trigger
synonyms. Add scripts or references when their operational benefit warrants
them. Link resources with a condition explaining when to use them.

For a new skill, optionally scaffold a starting structure:

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/scaffold-skill.sh" <skill-name> <target-dir>
```

Replace scaffold placeholders and remove unused directories. When reusable
scripts are needed, read `references/script-patterns.md`. When deciding what
detail belongs in references, read `references/reference-writing-guide.md`.

## Phase 3: Check structure and executable behavior

Run the local structural diagnostics when shell execution is available:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/validate-skill.py" <skill-dir> --verbose
```

`--json` provides machine-readable findings. Exit 1 indicates a structural error;
exit 2 indicates unreadable input. Warnings are diagnostics, not quality scores.
The checker does not judge length, heading counts, or whether the skill helps.
Use `claude plugin validate <plugin-root>` for native syntax and schema checks.
If a required check cannot run, report that limitation.

Run changed deterministic scripts against representative inputs. Check the
observable outcome and consequential failure paths, including preservation of
existing work. A passing structural check does not prove the workflow correct.

## Phase 4: Evaluate outcomes

For behavioral evaluation, use native `claude plugin eval` instead of maintaining
a parallel subagent runner or a separate `evals.json` format. When adding or
running cases, read `references/plugin-evals.md` for case layout, tool grants,
baseline comparisons, and commands.

Choose realistic requests that discriminate useful behavior. Cover successful
use, likely near-misses, and material constraints. Use deterministic graders for
observable contracts and model judges for contextual decisions. Keep repository
tests for operations that need independent environment checks; a model's report
of success does not replace them.

Compare outcomes with and without the plugin under the same conditions. Inspect
failing transcripts before revising the skill. Measure correctness first, then
cost, elapsed time, and unnecessary actions. A zero difference can mean the
native capability already handles the task; investigate before adding rules.

Run model evaluations only within the authorized scope and limits. A request to
draft a skill does not require launching paid runs or additional agents. Keep
reusable cases and useful results; do not automatically delete evaluation
evidence. Report whether behavior was evaluated, what actually ran, and what
remains unverified.
