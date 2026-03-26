---
name: skill-forge
description: |
  Build, fix, and optimize Claude Code skills with expert-level progressive disclosure, deterministic scripts, and eval-driven iteration. ALWAYS use this skill — not general knowledge — when the user wants to create a skill, build a skill, make a skill, write a SKILL.md, scaffold a skill, improve a skill, fix a bloated skill, optimize a skill description, reduce context usage in a skill, restructure skill references, turn a workflow into a reusable skill, capture a process as a skill, package scripts into a skill, or ask about skill architecture, progressive disclosure, conditional reference loading, or skill triggering. Also use when a user describes doing the same multi-step process repeatedly and wants to automate it as a slash command, or when they complain a skill "eats context", "triggers on everything", "never triggers", or "loads too much". This skill has validation scripts, scaffolding tools, and deep reference materials on skill architecture that general knowledge cannot match.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Agent
effort: high
user-invocable: true
---

# Skill Forge

Build world-class skills through a structured craftsman process: interview, architect, build bottom-up, validate, iterate.

The core philosophy: **scripts for determinism, references for depth, SKILL.md for orchestration.** Every skill should consume the minimum context needed for the task at hand. Only add context Claude doesn't already have — challenge every paragraph: "Does this justify its token cost?"

## Figuring out where the user is

Not every user starts from zero. Assess the situation:

- **"I want to create a skill for X"** → Start at Phase 1 (Discovery Interview)
- **"Turn this into a skill"** (conversation has a workflow) → Extract answers from conversation history first, confirm gaps, then Phase 2
- **"My skill is too bloated / loads too much context"** → Read the skill, run validation (`scripts/validate-skill.py`), jump to Phase 5 (Refactor)
- **"I have a draft, help me improve it"** → Read the draft, run validation, jump to Phase 4 (Validate & Iterate)
- **User has a skill and wants better triggering** → Jump to Phase 6 (Description Optimization)

Adapt — the phases are a guide, not a cage.

## Phase 1: Discovery Interview

Before writing anything, understand what the skill needs to do. Extract these answers through conversation (some may already be clear from context):

1. **Problem** — What does this skill enable Claude to do that it can't do well on its own?
2. **Trigger** — What user phrases or contexts should activate it?
3. **Audience** — Who uses this? (expertise level matters for how instructions are written)
4. **Degrees of freedom** — For each operation, decide the freedom level:
   - **Low freedom** (fragile, exact sequence matters) → deterministic script, no variation
   - **Medium freedom** (preferred pattern exists) → pseudocode or parameterized script
   - **High freedom** (multiple valid approaches) → text instructions, let Claude decide
5. **Tools & Dependencies** — What external tools, commands, or APIs are involved?
6. **Edge cases** — What could go wrong? What are the unusual inputs?
7. **Output** — What should the final result look like?
8. **References needed** — What domain knowledge exists or needs to be written?

Proactively ask about gaps. Check available MCPs for research if helpful. Come prepared with context to reduce burden on the user.

## Phase 2: Architecture Design

Before writing content, design the progressive disclosure tree. Present this to the user for alignment:

```
skill-name/
├── SKILL.md (orchestrator — what goes here?)
├── scripts/ (deterministic ops — what gets scripted?)
├── references/ (domain depth — what topics?)
└── [examples/] (if needed — working code samples?)
```

For each component, decide:
- **SKILL.md** — Workflow phases, decision points, routing logic, output format. Target: 1,500-2,000 words.
- **Scripts** — List each script with: name, purpose, inputs, outputs, exit codes. Anything deterministic (validation, scaffolding, format conversion, detection) should be a script.
- **References** — List each reference with: topic, estimated length, when it should load (the condition). Each should be a self-contained knowledge unit (2,000-5,000 words).
- **allowed-tools** — Only list tools the skill actually needs.

**Critical rules:**
- All references must be **one level deep** from SKILL.md. Never chain references (SKILL.md → ref-a.md → ref-b.md) — Claude may only partially read nested references.
- **No "always-loaded" references.** If content is needed on every invocation, it belongs as a compact inline section in SKILL.md (a table or short checklist), not as a separate file that costs a full Read. The point of references is conditional loading — a reference loaded every time is just a monolith with extra steps.

For deeper guidance on scripts or reference documents, read the appropriate reference:
- Script design decisions → Read `references/script-patterns.md`
- Reference document planning → Read `references/reference-writing-guide.md`

## Phase 3: Build (Bottom-Up)

Build in this order — foundation first, orchestrator last:

### Step 1: Scaffold

Run the scaffolding script to create the directory structure:

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/scaffold-skill.sh <skill-name> <target-dir>
```

Use `--full` flag if the skill needs examples/ and assets/ directories.

### Step 2: Write scripts

Create each script identified in Phase 2. For patterns and templates:
- Read `references/script-patterns.md` for bash and python templates, error handling conventions, and portability guidelines.

Key principles for every script:
- Shebang line (`#!/usr/bin/env bash` or `#!/usr/bin/env python3`)
- `set -euo pipefail` for bash
- Structured output (JSON preferred for complex results)
- Stderr for diagnostics, stdout for data
- Help text with `--help` flag
- No interactive prompts (Claude's Bash tool doesn't support stdin)

### Step 3: Write references

Create each reference document identified in Phase 2. For structure and style guidance:
- Read `references/reference-writing-guide.md` for organization patterns, optimal length, and self-containment rules.

Key principles for every reference:
- Title + purpose statement at the top
- Table of contents if > 100 lines (so Claude can see scope even when previewing)
- Self-contained — doesn't require other references to make sense
- Concrete examples, not just abstract rules
- 2,000-5,000 words
- Scripts should **solve errors, not punt** — handle edge cases explicitly instead of failing and hoping Claude figures it out

### Step 4: Write SKILL.md

Now write the orchestrator — it references everything built in steps 2-3. The SKILL.md should:
- Start with YAML frontmatter — available fields:
  - `name` (kebab-case, max 64 chars, no reserved words like "anthropic"/"claude")
  - `description` (max 1024 chars, third-person, trigger-rich, slightly "pushy")
  - `allowed-tools` (only what the skill needs)
  - `user-invocable` (default true; set false for background knowledge)
  - `disable-model-invocation` (set true for manual-only skills like `/deploy`)
  - `argument-hint` (shown during autocomplete, e.g., `[issue-number]`)
  - `context: fork` (run in isolated subagent — needs explicit task instructions)
  - `agent` (which subagent type when `context: fork` is set)
  - `model` (override model for this skill)
  - `hooks` (scoped to this skill's lifecycle)
- Contain the workflow with clear phases and decision points
- Reference scripts with `${CLAUDE_SKILL_DIR}/scripts/name.sh` — this variable resolves to the skill's own directory
- Reference each reference file with **conditional loading instructions** (when to read, not "read everything first")
- Define the output format
- Stay under 500 lines / 2,000 words

**Dynamic context injection:** Use `!`command`` syntax to run shell commands before the skill content reaches Claude. The output replaces the placeholder — useful for injecting live data (git status, API state, etc.) into the skill prompt.

**String substitutions:** `$ARGUMENTS` (user input), `$ARGUMENTS[N]` or `$N` (positional), `${CLAUDE_SESSION_ID}`, `${CLAUDE_SKILL_DIR}`.

**Writing style:**
- Imperative form ("Check the file" not "You should check the file")
- Explain *why* things matter — Claude has good theory of mind and responds better to reasoning than rigid MUSTs
- Third-person in the description field
- Be concise — only add context Claude doesn't already have

## Phase 4: Validate & Iterate

### Run quality validation

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/validate-skill.py <skill-dir> --verbose
```

For JSON output (useful for programmatic checks):
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/validate-skill.py <skill-dir> --json
```

Address any errors and warnings before proceeding. Target score: 80+.

### Create test cases

Come up with 2-3 realistic test prompts — things a real user would actually type, with detail and personality. Share them with the user for review.

Save test cases to `<skill-name>-workspace/evals/evals.json`:

```json
{
  "skill_name": "the-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "Realistic user prompt with detail and context",
      "expected_output": "Description of what good output looks like",
      "files": []
    }
  ]
}
```

### Run test cases

For each test case, spawn two subagents in the **same turn** — one with the skill, one without (baseline):

**With-skill subagent:**
```
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Save outputs to: <workspace>/iteration-<N>/eval-<ID>/with_skill/outputs/
```

**Baseline subagent** (same prompt, no skill):
```
Execute this task (no skill):
- Task: <eval prompt>
- Save outputs to: <workspace>/iteration-<N>/eval-<ID>/without_skill/outputs/
```

Launch all runs in parallel. While they run, draft assertions for quantitative evaluation — objective, verifiable checks with descriptive names.

### Grade and review

When runs complete, capture `total_tokens` and `duration_ms` from task notifications into `timing.json`.

Grade each run against assertions — use scripts for programmatic checks where possible, spawn a grader subagent for judgment calls. Save results to `grading.json` in each run directory using fields: `text`, `passed`, `evidence`.

Generate the eval viewer so the user can review qualitative output alongside quantitative benchmarks. Present both tabs (Outputs + Benchmark) and wait for feedback.

### Iterate

Read the user's feedback. Generalize from specific complaints — the goal is a skill that works across many prompts, not just these test cases. Revise the skill, rerun tests into a new iteration directory, and repeat until:
- The user is happy
- Feedback is empty (everything looks good)
- Progress has plateaued

When improving, focus on **why** not **what**. Explain reasoning in the skill rather than adding rigid rules. If a prompt performs badly, read the transcript to understand where the skill led Claude astray, and fix the root cause.

## Phase 5: Refactor (for existing skills)

When improving an existing skill's progressive disclosure, **always start with validation to establish a baseline score:**

1. **Run validation FIRST** — this is the diagnostic step, do not skip it:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/validate-skill.py <skill-dir> --verbose
   ```
   Record the baseline score. This tells you exactly what's wrong and prioritizes fixes.

2. Read SKILL.md and identify the specific anti-patterns:
   - Content that should be references (domain knowledge blocks > 500 words)
   - Inline code that should be scripts (deterministic operations)
   - **Unconditional reference loading** ("always read X", "first load all references") — this is the most common and most costly anti-pattern
   - **Always-loaded references** — references that claim to be "cross-cutting" or "always needed" are almost always better as a compact inline table in SKILL.md. If it's truly needed every time, it should be in SKILL.md, not a reference that costs a full file read.
   - Missing conditional loading instructions
3. Check against anti-patterns checklist:
   - **The Monolith** — everything in SKILL.md (3,000+ words). Fix: extract to references/scripts.
   - **The Eager Loader** — "first, read all references". Fix: conditional loading only.
   - **The Orphaned Reference** — ref exists but isn't mentioned in SKILL.md. Fix: mention with condition, or delete.
   - **The Implicit Script** — inline bash/python blocks regenerated every time. Fix: extract to script.
   - **The "Always Needed" Reference** — claimed cross-cutting but loaded every time. Fix: distill to inline table in SKILL.md; move details to conditional ref.
   - **The Everything Reference** — single 8,000+ word file. Fix: split by topic.
4. Restructure: extract references, create scripts, slim SKILL.md
5. **Re-validate and compare scores** — the score should improve. If it doesn't, something went wrong.

## Phase 6: Description Optimization

After the skill content is solid, optimize the description for trigger accuracy.

### Generate eval queries

Create 20 queries — realistic, detailed, with personality. Mix of should-trigger (8-10) and should-not-trigger (8-10).

**Should-trigger queries** should be diverse: different phrasings, casual vs formal, explicit vs implicit need. Include edge cases where the skill should win over competitors.

**Should-not-trigger queries** should be near-misses — things that share keywords but need something different. Avoid obviously irrelevant queries ("write a fibonacci function" as a negative for a deployment skill tests nothing).

All queries should be substantive — simple one-liners won't trigger skill consultation regardless of description quality.

### Review with user

Present the eval set for the user to review and edit. Adjust based on their feedback — bad eval queries lead to bad descriptions.

### Run optimization

Save the eval set and run the optimization loop. This automatically:
- Splits 60/40 into train/test sets
- Evaluates current description (3 runs per query for reliability)
- Uses Claude with extended thinking to propose improvements based on failures
- Re-evaluates on both train and test sets
- Iterates up to 5 times
- Selects best description by test score (prevents overfitting)

Apply the winning description to SKILL.md frontmatter. Show before/after with scores.

## Key Principles

- **Context is expensive** — every token loaded is a token that can't carry working memory. Minimize what loads per invocation. Challenge every paragraph: "Does Claude really need this?"
- **Scripts are free** — they execute without entering context. Bias toward scripting deterministic operations. Scripts should solve errors explicitly, not punt to Claude.
- **One level deep** — all reference files link directly from SKILL.md. Never chain references (A → B → C). Claude may partially read nested files.
- **Degrees of freedom** — match instruction specificity to task fragility. Fragile operations (migrations, deployments) get exact scripts. Flexible tasks (code review, analysis) get high-level guidance.
- **Feedback loops** — for quality-critical tasks, build validate → fix → repeat cycles. A validation script that catches errors early is worth more than instructions that hope Claude gets it right.
- **Explain the why** — Claude responds better to reasoning than rigid rules. "Check for SQL injection because user input flows to the query builder" beats "ALWAYS check for SQL injection."
- **Generalize, don't overfit** — skills run millions of times across diverse prompts. Avoid fiddly changes targeted at specific test cases.
- **Build bottom-up** — scripts and references first, SKILL.md last. The orchestrator can't reference what doesn't exist yet.

## Phase 7: Cleanup

When the skill is finalized and the user is satisfied, clean up all workspace artifacts created during development:

1. **Delete the workspace directory** — `<skill-name>-workspace/` contains evals, iteration outputs, grading results, timing data, and trigger eval files. All of this is disposable once the skill is done.
   ```bash
   rm -rf <skill-name>-workspace/
   ```

2. **Confirm with user first** — before deleting, briefly list what will be removed and ask for confirmation. If the user wants to keep any specific artifacts (e.g., final benchmark results), save those elsewhere first.

Always run this phase at the end of skill creation or optimization work. Don't leave workspace directories behind — they clutter the repo and have no value after iteration is complete.
