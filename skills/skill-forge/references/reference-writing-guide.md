# Reference Writing Guide

## Table of Contents

1. [What Makes a Good Reference](#what-makes-a-good-reference)
2. [Structure and Organization](#structure-and-organization)
3. [Optimal Length](#optimal-length)
4. [Self-Contained Knowledge Units](#self-contained-knowledge-units)
5. [How to Reference from SKILL.md](#how-to-reference-from-skillmd)
6. [When to Split vs Combine](#when-to-split-vs-combine)
7. [Writing Style for References](#writing-style-for-references)
8. [Examples of Effective References](#examples-of-effective-references)

---

## What Makes a Good Reference

A reference file is a self-contained knowledge document that provides depth on a specific topic. Unlike SKILL.md (which orchestrates), references inform. They're loaded into context on-demand, so each one should earn its context cost by providing knowledge the AI can't reliably produce on its own.

**A good reference is:**
- **Focused** — covers one topic thoroughly, not many topics shallowly
- **Self-contained** — makes sense without reading other files first
- **Actionable** — provides patterns, rules, or checklists the AI can apply directly
- **Calibrated** — long enough to be thorough, short enough to justify loading

**A good reference is NOT:**
- A dump of raw documentation (too verbose, not actionable)
- A copy of SKILL.md content (redundant, wastes context)
- A collection of unrelated tips (unfocused, hard to use)
- A file that needs other references to make sense (not self-contained)

---

## Structure and Organization

Every reference should follow this structure:

### 1. Title and Purpose (2-3 lines)

Start with a clear heading and a brief statement of what this reference covers and when the AI should use it.

```markdown
# Security Review Checklist

Use this reference when reviewing code for security issues. Covers OWASP Top 10,
authentication patterns, and input validation.
```

### 2. Table of Contents (for files > 100 lines)

For longer references, include a navigable table of contents:

```markdown
## Contents
1. [Input Validation](#input-validation)
2. [Authentication](#authentication)
3. [SQL Injection Prevention](#sql-injection)
```

### 3. Core Content (organized by topic)

Use clear headings (##, ###) to separate topics. Each section should be independently useful — the AI might be looking for just one section, not reading front-to-back.

### 4. Quick Reference (optional, at the end)

For references with many rules or patterns, end with a condensed summary table or checklist.

```markdown
## Quick Reference

| Issue | Check | Fix |
|-------|-------|-----|
| SQL injection | Raw string in query | Use parameterized queries |
| XSS | Unescaped user input in HTML | Use template engine auto-escaping |
```

---

## Optimal Length

### The Sweet Spot: 2,000-5,000 Words

This range provides enough depth to be genuinely useful while keeping context cost manageable (~2,700-6,700 tokens).

| Length | Tokens | Good For |
|--------|--------|----------|
| < 500 words | < 700 | Too thin — probably should be in SKILL.md |
| 500-2,000 | 700-2,700 | Quick references, checklists, lookup tables |
| 2,000-5,000 | 2,700-6,700 | Ideal for most domain knowledge |
| 5,000-8,000 | 6,700-10,800 | Comprehensive guides — use sparingly |
| > 8,000 | > 10,800 | Too large — split into sub-documents |

### Signs a Reference is Too Short

- It repeats what SKILL.md already says
- It only has one section with a few bullet points
- The AI could have generated this content from general knowledge
- Loading it doesn't change the AI's behavior

**Fix:** Either expand with genuinely useful domain knowledge, or fold the content into SKILL.md.

### Signs a Reference is Too Long

- It covers multiple distinct topics that are used independently
- Sections are largely independent of each other
- The AI only needs 20% of it for any given invocation
- It exceeds 8,000 words

**Fix:** Split into focused sub-documents by topic.

---

## Self-Contained Knowledge Units

Each reference should be a **self-contained knowledge unit** — meaning it provides everything the AI needs to handle the topic it covers, without requiring other references to be loaded simultaneously.

### What Self-Contained Means

- **No forward references** — Don't say "see security-patterns.md for details" for something critical to this reference's topic. If it's needed, include it.
- **Defines its own terms** — Don't assume the AI read another reference that defines a concept. Define it here (briefly) if you use it.
- **Complete patterns** — If you show a pattern, include enough context to apply it. Don't show half a solution.

### What Self-Contained Does NOT Mean

- **No duplication required** — If two references share a concept, a brief one-line mention is fine. You don't need to reproduce 500 words of context in each file.
- **No cross-references allowed** — You can mention other references exist for related topics. Just don't depend on them for this reference's core content.

### Example: Good Self-Containment

```markdown
# AWS Deployment Reference

## IAM Role Configuration

When deploying to AWS, the Lambda function needs an execution role.
The role must have these permissions:
- logs:CreateLogGroup
- logs:CreateLogStream
- logs:PutLogEvents
- s3:GetObject (for the deployment bucket)

Create the role with this trust policy:
[full JSON trust policy here]

Then attach the permissions:
[full JSON permissions policy here]
```

This section is complete — someone reading just this reference can create the IAM role without looking anywhere else.

### Example: Poor Self-Containment

```markdown
# AWS Deployment Reference

## IAM Role Configuration

Create an IAM role as described in the IAM reference (see references/iam-setup.md).
Make sure it has the permissions listed in references/permissions-matrix.md.
```

This forces loading two additional references just to complete one task.

---

## How to Reference from SKILL.md

The way SKILL.md points to references determines when they load. This is the most important interface in progressive disclosure.

### Pattern 1: Condition-Based Loading

```markdown
## Reference materials

- If reviewing **security** concerns → Read `references/security-checklist.md`
- If reviewing **performance** concerns → Read `references/performance-patterns.md`
- If the project uses **React** → Read `references/react-patterns.md`
```

Clear conditions, one reference per condition. The AI loads only what's relevant.

### Pattern 2: Phase-Based Loading

```markdown
## Phase 3: Deep Analysis

Based on findings from Phase 2:
1. For each category of issues found, read the corresponding reference in `references/`
2. Apply the patterns from the reference to generate detailed feedback
```

References load only during a specific workflow phase.

### Pattern 3: Script-Gated Loading

```markdown
## Detection

Run `scripts/detect-stack.sh <project-dir>` to identify the technology stack.
Based on the output:
- `type: "python"` → Read `references/python-patterns.md`
- `type: "typescript"` → Read `references/typescript-patterns.md`
- `type: "go"` → Read `references/go-patterns.md`
```

A script determines which reference is needed. Highly efficient — the detection script costs zero context.

### Anti-Pattern: Unconditional Loading

```markdown
## Setup

First, read all reference files in references/ to understand the domain.
```

This loads everything every time. Never do this.

### Anti-Pattern: Vague Loading

```markdown
## References

See the references/ directory for additional information.
```

Too vague — the AI doesn't know when to look or what to look for. Be specific about conditions and content.

---

## When to Split vs Combine

### Split When

- **Topics are used independently** — If you review security without needing style patterns, they should be separate files.
- **Users have different needs** — If AWS users never need GCP content, split by provider.
- **A section exceeds 3,000 words** — It's probably a topic worth its own file.
- **Loading frequency differs** — If section A is needed 80% of the time and section B only 10%, keeping them together wastes context 90% of the time for B's content.

### Combine When

- **Topics are always used together** — If you never check authentication without also checking authorization, they can share a file.
- **Individual pieces are too small** — Three 400-word sections are better as one 1,200-word reference than three separate files.
- **There's a natural narrative** — Sometimes a topic flows from setup → configuration → troubleshooting, and splitting it would lose coherence.
- **Cross-references would be constant** — If splitting would require every section to say "see the other file for X", they belong together.

### The Decision Rule

Ask: "When the AI loads this file, what percentage of it will typically be relevant?"

- **> 70% relevant** → Keep combined
- **30-70% relevant** → Consider splitting, but weigh the overhead of more files
- **< 30% relevant** → Definitely split

---

## Writing Style for References

### Use Imperative and Declarative Forms

References are instructions and facts, not conversations.

```markdown
# Good
Check all SQL queries for parameterized arguments. Raw string concatenation
in queries is a critical security issue.

# Poor
You should check all SQL queries for parameterized arguments. I'd recommend
looking for raw string concatenation, which could be a security issue.
```

### Lead with the Rule, Follow with Context

```markdown
# Good
Never store secrets in environment variables accessible to child processes.
Environment variables are inherited by all child processes, making them visible
to any library or subprocess — even malicious ones.

# Poor
Environment variables have a property where they're inherited by child processes.
This means that any subprocess can read them. Libraries you import could also
access them. Because of all this, you shouldn't store secrets in them.
```

### Include Concrete Examples

Abstract rules are hard to apply. Concrete examples make patterns immediately usable.

```markdown
## Input Validation

Validate all user input at the boundary where it enters the system.

**Bad — validation deep inside business logic:**
```python
def process_order(data):
    # 50 lines later...
    if not data.get("amount"):  # Too late!
        raise ValueError("missing amount")
```

**Good — validation at the boundary:**
```python
@validate_input(OrderSchema)
def process_order(data: ValidatedOrder):
    # data is already validated, just use it
    charge(data.amount)
```
```

### Use Tables for Lookup-Style Content

When the AI needs to match a condition to an action, tables are more efficient than paragraphs:

```markdown
| HTTP Status | Meaning | Action |
|------------|---------|--------|
| 401 | Unauthorized | Check API key, refresh token |
| 403 | Forbidden | Check IAM permissions |
| 429 | Rate limited | Implement exponential backoff |
| 500 | Server error | Retry with backoff, then escalate |
```

---

## Examples of Effective References

### Example 1: Technology-Specific Patterns

**File:** `references/react-patterns.md` (~3,000 words)

Structure:
1. Component patterns (functional, hooks, composition)
2. State management (local, context, external)
3. Performance (memo, useMemo, useCallback, virtualization)
4. Testing (RTL patterns, mock strategies)
5. Common anti-patterns with fixes
6. Quick reference table

Why it works: Focused on one technology, organized by concern, includes concrete code examples, ends with a scannable reference table.

### Example 2: Review Checklist

**File:** `references/security-checklist.md` (~2,500 words)

Structure:
1. Input validation rules (by input type)
2. Authentication checks (session, token, OAuth)
3. Authorization patterns (RBAC, ABAC)
4. Data handling (encryption, PII, logging)
5. Dependency security (known vulns, pinning)
6. Severity classification guide
7. Quick-scan checklist (30-second version)

Why it works: Organized as a checklist the AI can work through systematically, with a quick-scan version at the end for simple reviews.

### Example 3: Domain Knowledge

**File:** `references/ecto-phoenix-patterns.md` (~4,000 words)

Structure:
1. Schema and changeset patterns
2. Query composition
3. Migration best practices
4. Context module organization
5. Testing with Ecto sandbox
6. Performance considerations (preloading, N+1)
7. Common mistakes with corrections

Why it works: Covers one framework deeply, provides both patterns and anti-patterns, includes practical advice specific to this ecosystem that the AI might not reliably know from training data.
