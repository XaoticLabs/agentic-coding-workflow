# Progressive Disclosure Mastery

## Table of Contents

1. [The Three Levels](#the-three-levels)
2. [Decision Framework: What Goes Where](#decision-framework)
3. [Anti-Patterns](#anti-patterns)
4. [Context Budget Awareness](#context-budget-awareness)
5. [Real-World Examples](#real-world-examples)
6. [The Conditional Loading Pattern](#the-conditional-loading-pattern)

---

## The Three Levels

Progressive disclosure in skills is about respecting the context window as a finite, expensive resource. Every token loaded is a token that could carry working memory, user context, or code. The three levels form a hierarchy of increasing detail and decreasing frequency of use.

### Level 1: Metadata (Always Loaded)

**What it is:** The skill's `name` and `description` from SKILL.md frontmatter. This is always in Claude's context as part of the available skills list.

**Budget:** ~100 words. Treat this like a search index entry — it determines whether the skill triggers at all.

**What belongs here:**
- Skill name (kebab-case identifier)
- Trigger-optimized description with specific phrases, keywords, and use cases
- Nothing else — no instructions, no examples

**Quality signals:**
- Description mentions specific user actions ("create a PR", "review Terraform plans")
- Includes keywords a user would naturally say
- Written in third-person ("This skill should be used when...")
- Slightly "pushy" — errs toward triggering rather than missing

### Level 2: SKILL.md Body (Loaded on Trigger)

**What it is:** The markdown body after the frontmatter. Loaded into context whenever Claude decides to use the skill.

**Budget:** 1,500-2,000 words ideal, under 500 lines. This is the skill's "working memory" — everything here is loaded every single time.

**What belongs here:**
- The core workflow — phases, decision points, branching logic
- Tool usage instructions and script invocations
- Pointers to references with conditional loading instructions
- Output format definitions
- Quick reference tables or checklists

**What does NOT belong here:**
- Exhaustive domain knowledge (→ references)
- Complete API documentation (→ references)
- Long examples with full code (→ references or scripts)
- Multiple alternative approaches spelled out in full (→ references)

### Critical Rule: One Level Deep

All reference files must link **directly from SKILL.md**. Never chain references where SKILL.md points to ref-a.md which points to ref-b.md. Claude may use partial reads (`head -100`) on nested references, resulting in incomplete information. Keep the tree flat.

### Level 3: Bundled Resources (Loaded on Demand)

**What it is:** Files in `references/`, `scripts/`, `examples/`, and `assets/` subdirectories.

**Budget:** Unlimited in storage, but each file loaded costs context. References should be 2,000-5,000 words each.

**Sub-categories:**

| Directory | Purpose | Loaded How |
|-----------|---------|------------|
| `references/` | Domain knowledge docs | Read into context when needed |
| `scripts/` | Executable helpers | Executed via Bash — code doesn't enter context |
| `examples/` | Working code samples | Read when user needs a starting point |
| `assets/` | Templates, images, data | Used in output generation |

**Key insight:** Scripts are the most context-efficient resource because they execute without being loaded into the conversation. A 200-line Python script costs zero context tokens — it just runs and returns results.

---

## Decision Framework

When deciding where content belongs, ask these questions in order:

### 1. "Can this be a script?"

If the operation is deterministic (same input → same output), make it a script. Scripts:
- Cost zero context tokens (executed, not loaded)
- Produce reliable, consistent results
- Can be tested independently
- Run faster than AI-generated alternatives

**Examples:** File scaffolding, validation checks, data transformation, git operations, format conversion.

### 2. "Is this needed every time the skill runs?"

If yes → SKILL.md. If only sometimes → reference file.

The test: imagine 10 different users invoking this skill with different prompts. If 8+ of them need this content, it belongs in SKILL.md. If only 2-3 need it, it's a reference.

**Example:** A deployment skill always needs the deployment workflow (SKILL.md), but only sometimes needs the AWS-specific configuration details (references/aws.md).

### 3. "Is this a decision or a detail?"

Decisions, branching logic, and workflow steps → SKILL.md. Detailed specifications, exhaustive lists, and deep explanations → references.

**Example:** "If the project uses TypeScript, read references/typescript-patterns.md" is a SKILL.md decision. The actual TypeScript patterns are reference content.

### 4. "Could a human skim this in 30 seconds?"

Quick-reference tables, checklists, and short decision trees belong in SKILL.md because they're compact and frequently needed. Multi-page deep dives belong in references.

---

## Anti-Patterns

### The Monolith

**Problem:** Everything crammed into a single SKILL.md file — 3,000+ words, full examples, API docs, edge cases, all inline.

**Why it hurts:** Every invocation loads all of it. A user asking a simple question triggers the same 3,000-word context load as a complex multi-step task. Context is wasted on irrelevant sections.

**Fix:** Extract domain knowledge into references, move deterministic operations into scripts, keep SKILL.md as the orchestrator.

### The Eager Loader

**Problem:** SKILL.md starts with "First, read all reference files" or "Always load references/config.md and references/patterns.md".

**Why it hurts:** Defeats the entire purpose of having references. You've effectively made a monolith with extra steps — the content still loads every time, just from multiple files.

**Fix:** Use conditional loading: "If the user is working with AWS, read references/aws.md." Never load all references upfront.

### The Orphaned Reference

**Problem:** Reference files exist in the directory but aren't mentioned in SKILL.md. The skill doesn't know they exist.

**Why it hurts:** The reference is dead weight — it adds complexity to the directory structure but never gets used. Worse, it might contain important content that the skill should be using.

**Fix:** Every reference file must be mentioned in SKILL.md with a clear condition for when to read it. If a reference isn't worth mentioning, delete it.

### The Implicit Script

**Problem:** SKILL.md contains inline bash commands or Python snippets that get regenerated every invocation instead of being a script.

**Why it hurts:** The code takes up context space AND is regenerated (possibly with variations) every time. A script runs deterministically and costs zero context.

**Fix:** If you find yourself writing `Run this command: ...` with more than 2-3 lines of code in SKILL.md, extract it into a script.

### The "Always Needed" Reference

**Problem:** A reference file that's marked as "always load" because it contains "cross-cutting" or "foundational" knowledge. For example: "Always read `references/common-patterns.md` before starting."

**Why it hurts:** If it's truly needed every invocation, it should be inline in SKILL.md as a compact table or checklist — not a separate file that costs a full Read operation. A reference that always loads is a monolith with extra steps. It also sets a bad precedent: if one reference is "always needed," others tend to follow.

**Fix:** Take the essential content from the "always needed" reference and distill it into a compact inline section in SKILL.md (usually a table or short checklist). Move the detailed explanations to a conditionally-loaded reference that's only read when the user asks "why?" or needs deeper context.

### The Everything Reference

**Problem:** A single massive reference file (8,000+ words) that covers every aspect of the domain.

**Why it hurts:** When the skill needs just one piece of information from the reference, it loads the entire file. It's a monolith in disguise.

**Fix:** Split by topic or use case. Instead of `references/everything.md`, use `references/setup.md`, `references/patterns.md`, `references/troubleshooting.md`. Each file should be a self-contained knowledge unit on a focused topic.

---

## Context Budget Awareness

### The Conciseness Principle

Before adding content to any skill, ask three questions:
1. "Does Claude really need this explanation?" — Claude is already very smart. Don't explain what PDFs are or how libraries work.
2. "Can I assume Claude knows this?" — Only add context Claude doesn't already have.
3. "Does this paragraph justify its token cost?" — Every token competes with conversation history.

### The Math

A typical Claude conversation has a context window of 200K tokens. Here's how skill content maps to that budget:

| Content | Approximate Tokens | % of Context |
|---------|-------------------|-------------|
| Skill metadata (L1) | ~150 | 0.08% |
| SKILL.md body (L2, 2000 words) | ~2,700 | 1.35% |
| One reference (3000 words) | ~4,000 | 2.0% |
| Two references loaded | ~8,000 | 4.0% |
| Five references loaded | ~20,000 | 10.0% |

Loading five reference files consumes 10% of the context window before the user has even started working. This is why conditional loading matters — not every invocation needs every reference.

### Budget Guidelines

- **SKILL.md body:** Aim for 1,500-2,000 words (~2,000-2,700 tokens). This is the "always pay" cost.
- **References:** 2,000-5,000 words each. Load at most 1-2 per invocation.
- **Total skill footprint per invocation:** Ideally under 10,000 tokens (5% of context).
- **Scripts:** Zero context cost. Use generously.

### When Overloading is OK

Sometimes a skill genuinely needs a lot of context. A complex code review skill might need style guides, security checklists, and framework-specific patterns simultaneously. In these cases:
- Acknowledge the context cost in SKILL.md with a note
- Make sure every loaded reference is actively used (no "just in case" loading)
- Consider whether a script could replace any of the reference content (e.g., a linting script vs. a linting reference doc)

---

## Real-World Examples

### Good: Domain-Variant Pattern

A deployment skill that supports multiple cloud providers:

```
cloud-deploy/
├── SKILL.md           (800 words — workflow + provider detection)
├── scripts/
│   └── detect-provider.sh    (checks for aws/gcp/azure CLI tools)
└── references/
    ├── aws.md         (3000 words — AWS-specific configs)
    ├── gcp.md         (3000 words — GCP-specific configs)
    └── azure.md       (3000 words — Azure-specific configs)
```

SKILL.md contains the universal deployment workflow and a decision point: "Run `detect-provider.sh` to identify the cloud provider, then read the corresponding reference file." Only one reference is loaded per invocation. Total context cost: ~5,400 tokens (SKILL.md + one reference).

### Good: Script-Heavy Pattern

A data transformation skill where most operations are deterministic:

```
data-transform/
├── SKILL.md           (600 words — workflow + script catalog)
├── scripts/
│   ├── detect-format.py      (identifies input format)
│   ├── csv-to-json.py        (CSV → JSON conversion)
│   ├── normalize-dates.py    (date format standardization)
│   └── validate-output.py    (schema validation)
└── references/
    └── format-specs.md       (2000 words — edge cases per format)
```

SKILL.md is tiny because the scripts do the real work. The reference is only loaded when the script encounters an unusual format. Total context cost per invocation: ~800 tokens (just SKILL.md).

### Poor: The Monolith

```
code-reviewer/
└── SKILL.md           (5000 words — style guide + security checklist
                        + framework patterns + output format + examples)
```

Everything is in one file. Every review loads the security checklist even for style-only reviews. The style guide loads for security reviews. Total context cost: ~6,700 tokens, most of it irrelevant to any given invocation.

### Better: Refactored

```
code-reviewer/
├── SKILL.md           (1200 words — review workflow + routing logic)
├── scripts/
│   └── detect-languages.sh
├── references/
│   ├── style-guide.md        (2500 words)
│   ├── security-checklist.md (3000 words)
│   └── framework-patterns.md (2500 words)
```

SKILL.md routes to the right references based on what the user asked for. A "check this for security issues" request loads only the security checklist. Total context cost: ~5,600 tokens (SKILL.md + one reference), with most of it directly relevant.

---

## The Conditional Loading Pattern

The most important pattern in progressive disclosure is how SKILL.md references its bundled resources. Here are effective patterns:

### Branch-on-Need

```markdown
## Reference materials

Load these based on the task:

- **Security review requested** → Read `references/security-checklist.md`
- **Style/readability focus** → Read `references/style-guide.md`
- **Framework-specific code** → Run `scripts/detect-framework.sh`, then read the matching reference
- **All of the above** → Read references in order of priority: security first, then style, then framework
```

### Phase-Based Loading

```markdown
## Phase 2: Deep Analysis

After initial scan, load the relevant reference for detailed analysis:

- If security issues were flagged in Phase 1, read `references/security-patterns.md`
- If performance concerns were found, read `references/performance-guide.md`
- If the code is well-structured, skip to Phase 3 (no additional context needed)
```

### Script-First, Reference-Fallback

```markdown
## Validation

1. Run `scripts/validate.py <path>` to check the output programmatically
2. If validation passes, report results and stop
3. If validation fails with "UNKNOWN_PATTERN" errors, read `references/edge-cases.md` for guidance on handling unusual patterns manually
```

This pattern is powerful because the common case (validation passes) costs zero context beyond SKILL.md. The reference only loads for the uncommon case where the script can't handle it.
