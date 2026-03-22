---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Agent
  - Write
  - AskUserQuestion
---

# Explain — Educational Code Breakdown

Generates a deep educational breakdown of code changes, files, or systems. Explains the "why" behind the code — not just what it does, but why it was designed that way, what trade-offs were made, and what concepts are at play.

## Input

$ARGUMENTS — One of:
- Empty — explains all staged/unstaged changes (like a teaching-oriented code review)
- A file path: `lib/accounts/auth.ex` — explains the module in depth
- A diff reference: `HEAD~3..HEAD` — explains recent commits
- A concept in context: `"how does the message pipeline work?"` — traces through the codebase and explains
- A PR number: `#142` — explains what the PR does and why

## Instructions

### Phase 1: Identify What to Explain

**Determine the scope:**

- **No arguments** — gather current changes:
  ```bash
  git diff --cached --name-only
  git diff --name-only
  git diff origin/main...HEAD --name-only
  ```

- **File path** — read the file and its surrounding context (callers, tests, related modules)

- **Diff reference** — gather the diff:
  ```bash
  git diff <ref>
  git log --oneline <ref>
  ```

- **Concept/question** — search the codebase for relevant modules, trace the data flow, and map the system

- **PR number** — fetch PR details:
  ```bash
  gh pr view <number> --json title,body,files
  gh pr diff <number>
  ```

**If nothing found:**
- Use AskUserQuestion: "What would you like me to explain? A file, a recent change, a concept, or a system?"

### Phase 2: Build Context

**Read all relevant code** — not just the target, but the surrounding ecosystem:

- The file/changes themselves
- Direct callers and consumers (use Grep to find references)
- Related tests (they reveal intent and edge cases)
- Configuration that affects behavior
- Similar patterns elsewhere in the codebase (shows conventions)

**Use subagents for broad exploration** — if the concept spans multiple modules, launch Agent workers to explore different areas in parallel. Combine their findings.

### Phase 3: Generate the Explanation

Structure the explanation in layers, from high-level to detailed:

```markdown
## What This Does
[1-2 sentence plain-English summary. No jargon. A non-engineer should understand this paragraph.]

## Why It Exists
[The problem this solves. What was the situation before? What would happen without this code?]

## How It Works
[Walk through the logic step by step. Use numbered steps for sequential flows, bullet points for parallel concerns.]

### Key Concepts
[Explain any patterns, algorithms, or architectural decisions that aren't immediately obvious:]
- **[Concept name]** — [Explanation in plain terms, then the technical detail]
- **[Pattern name]** — [Why this pattern was chosen over alternatives]

### Data Flow
[Trace the data through the system. Where does input come from? What transformations happen? Where does output go?]

### Trade-offs & Design Decisions
[What alternatives existed? Why was this approach chosen? What are the downsides?]
- **Chose X over Y because:** [reason]
- **The downside is:** [limitation]
- **This matters when:** [context where the trade-off becomes relevant]

## Edge Cases & Gotchas
[Things that aren't obvious from reading the code:]
- [Edge case 1 — what triggers it, how it's handled]
- [Edge case 2]

## Related Code
[Other files/modules that interact with this code, with brief notes on the relationship]
- `path/to/file.ex` — [how it relates]

## If You're Modifying This Code
[Practical advice for someone about to make changes:]
- [What to watch out for]
- [What tests to run]
- [What other code might be affected]
```

**Adapt the depth to the scope:**
- Single function → focus on How It Works + Edge Cases
- Full module → include all sections
- System/concept → emphasize Data Flow + Why It Exists + Trade-offs
- Diff/PR → focus on What Changed + Why + Trade-offs

### Phase 4: Add Visual Aids

**Include diagrams where they help:**

- **Sequence diagrams** for request flows:
  ```
  Client → Router → Controller → Service → Database
                                    ↓
                               Queue (async)
  ```

- **ASCII box diagrams** for architecture:
  ```
  ┌─────────────┐     ┌──────────────┐
  │  API Layer   │────→│  Service      │
  └─────────────┘     │  Layer        │
                      └──────┬───────┘
                             │
                      ┌──────▼───────┐
                      │  Data Layer   │
                      └──────────────┘
  ```

- **State diagrams** for state machines or lifecycle:
  ```
  [created] → [pending] → [active] → [completed]
                  ↓                       ↓
              [failed]              [cancelled]
  ```

### Phase 5: Offer Next Steps

After the explanation, offer:

- "Want me to explain any part in more depth?"
- "Should I generate flashcards from this explanation?" (connects to `/flashcards`)
- "Want me to create a visual diagram?" (connects to `/agentic-coding-workflow:visualize`)

## Error Handling

**If the code is too large (>20 files):**
Focus on the most important/complex files. Note what was skipped and offer to explain specific areas on request.

**If the code is trivial:**
Give a brief explanation and note: "This is straightforward — let me know if you want me to go deeper on any specific aspect."

**If the concept is ambiguous:**
Use AskUserQuestion to clarify: "I found several things related to '[concept]' — which area interests you?"

## Important Constraints

- **Explain, don't judge** — this is educational, not a code review. Save opinions for `/grill-me` or `/agentic-coding-workflow:review-implementation`
- **Use the codebase's own terminology** — match naming conventions and domain language
- **Assume intelligence, not knowledge** — the reader is smart but may be new to this specific codebase/pattern
- **Concrete over abstract** — use actual values, real examples from the code, specific line references
- **Progressive depth** — start simple, layer in complexity. Let the reader stop when they've learned enough
- **No unnecessary jargon** — if you use a technical term, define it briefly on first use

## Example Usage

```
/agentic-coding-workflow:explain
```
Explains all current changes as a teaching-oriented walkthrough.

```
/agentic-coding-workflow:explain lib/accounts/auth.ex
```
Deep dive into the auth module — how it works, why it's designed this way, and what to know before modifying it.

```
/agentic-coding-workflow:explain "how does the message pipeline work?"
```
Traces the message pipeline through the codebase, explaining each stage.

```
/agentic-coding-workflow:explain HEAD~5..HEAD
```
Explains what the last 5 commits did and why, as a cohesive narrative.

```
/agentic-coding-workflow:explain #142
```
Explains PR #142 — what changed, why, and what trade-offs were made.
