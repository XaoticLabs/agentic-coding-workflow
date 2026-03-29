---
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - AskUserQuestion
  - Agent
effort: medium
---

# Ship — From Approved Code to Merged PR

Takes the current branch from approved implementation to a clean PR in one step: pushes, creates a PR with a generated description, and reports the URL.

## Input

$ARGUMENTS - Either:
- Empty — operates on current branch, auto-detects spec
- A spec path or slug (e.g., `batch-analysis` or `.claude/specs/batch-analysis-spec.md`) — uses for PR description context
- `--draft` flag — creates a draft PR instead of a ready-for-review PR
- `--no-squash` flag — skip the WIP squash phase (commits are already clean)

## Instructions

### Phase 1: Pre-flight

```bash
# Remove any stale PR description from a previous run
rm -f .claude/pr-description.md

# Get current branch
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null)

# Ensure we're not on main/master
for base in main master; do
  if [ "$BRANCH" = "$base" ]; then
    echo "ON_BASE_BRANCH"
  fi
done

# Find base branch
for candidate in main master; do
  if git show-ref --verify --quiet "refs/heads/$candidate"; then
    BASE="$candidate"
    break
  fi
done

# Count commits ahead
git rev-list --count "${BASE}..HEAD"

# Check for uncommitted changes
git status --porcelain
```

**If on main/master:** Stop with "You're on the base branch. Switch to a feature branch first."

**If there are uncommitted changes:** Use AskUserQuestion: "You have uncommitted changes. Commit them first, or ship without them?"

**If zero commits ahead of base:** Stop with "No commits to ship. Nothing to do."

### Phase 2: Find Context for PR Description

**Auto-detect spec/plan/ralph summary:**
- If spec provided in $ARGUMENTS, use it
- Otherwise, look for specs matching the branch name in `.claude/specs/`
- Also check `.claude/plans/` for a corresponding plan
- Check for Ralph summary: read `.claude/ralph-logs/ralph-summary-<slug>.md` if it exists for run metrics and context

**Gather context:**
```bash
# Clean commit log after squash
git log --oneline "${BASE}..HEAD"

# Diff stats
git diff --stat "${BASE}..HEAD"

# Full diff for understanding changes
git diff "${BASE}..HEAD"
```

### Phase 4: Detect PR Template

Check for a PR template in the repository. Search these locations in order:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)

# Check standard PR template locations (in priority order)
for tmpl in \
  "${REPO_ROOT}/.github/pull_request_template.md" \
  "${REPO_ROOT}/.github/PULL_REQUEST_TEMPLATE.md" \
  "${REPO_ROOT}/.github/PULL_REQUEST_TEMPLATE/pull_request_template.md" \
  "${REPO_ROOT}/docs/pull_request_template.md" \
  "${REPO_ROOT}/pull_request_template.md" \
  "${REPO_ROOT}/PULL_REQUEST_TEMPLATE.md"; do
  if [ -f "$tmpl" ]; then
    echo "TEMPLATE_FOUND: $tmpl"
    break
  fi
done
```

Also check for multiple templates (some repos offer a choice):
```bash
ls "${REPO_ROOT}/.github/PULL_REQUEST_TEMPLATE/" 2>/dev/null
```

If multiple templates exist, use AskUserQuestion to let the user pick one.

### Phase 5: Generate PR Description

**If a PR template was found:**

Read the template file. Preserve its exact structure — headings, sections, checkboxes, and any boilerplate text the team expects. Fill in each section intelligently using the spec, plan, commit log, and diff:

- **Headings/sections** (e.g., `## Description`, `## What Changed`, `## Motivation`) — fill with content derived from the spec summary, plan rationale, or commit messages. Match the section's intent.
- **Checklist items with empty checkboxes** (e.g., `- [ ] Tests added`) — check off items (`- [x]`) that are demonstrably true based on the diff and test results. Leave unchecked items that aren't applicable or can't be verified.
- **Placeholder text** (e.g., `<!-- Describe your changes -->`, `_Replace this with..._`) — replace with actual content. Remove HTML comments that were meant as instructions to the author.
- **Sections you can't fill** (e.g., `## Screenshots`, `## Jira Ticket`) — leave the heading in place with a brief note like `N/A` or `TODO` so the author can fill it in. Never delete template sections.
- **Static boilerplate** (e.g., team conventions, reviewer checklists, legal notices) — preserve exactly as-is.

The goal is that a reviewer opening the PR sees their familiar template fully filled out, not a generic description pasted over it.

Write the filled template to `.claude/pr-description.md`.

**If no PR template was found:**

Fall back to the default format:

```markdown
## Summary
- (2-3 bullet points covering what this PR does and why)

## Changes
- (one bullet per logical commit, with file counts)

## Test plan
- [ ] (specific things to verify — derived from spec acceptance criteria or from reading the diff)

## Notes
- (anything reviewers should pay attention to)
```

Write to `.claude/pr-description.md`.

In both cases, keep content concise. The diff speaks for itself — focus on the "why" and testing strategy, not re-describing every line changed.

### Phase 5.5: User Review of PR Description (ENFORCED BY HOOK)

A PreToolUse hook (`ship-gate.sh`) will **block** `gh pr create` unless `.claude/pr-description.md` contains the marker `<!-- user-approved -->` at the top. You cannot skip this step — the hook runs in the harness and will reject the command.

1. Read back the full contents of `.claude/pr-description.md` and display it to the user.
2. Use AskUserQuestion to ask: "Here's the PR description I generated. Approve it as-is, or tell me what to change."
3. Wait for the user's response. Do not continue until they reply.
4. If the user requests changes: apply them to `.claude/pr-description.md`, show the updated version, and ask again.
5. After the user explicitly approves (e.g., "looks good", "yes", "ship it"), add the approval marker:

```bash
# Add approval marker — ship-gate.sh hook checks for this before allowing gh pr create
sed -i '' '1s/^/<!-- user-approved -->\n/' .claude/pr-description.md
```

Only then proceed to Phase 6.

### Phase 6: Push and Create PR

Run the following script block **exactly as written** — do not modify, summarize, or reinterpret any part of it. Copy-paste the entire block into a single Bash tool call:

```bash
# Determine base and branch
BRANCH=$(git symbolic-ref --short HEAD)
for candidate in main master; do
  if git show-ref --verify --quiet "refs/heads/$candidate"; then BASE="$candidate"; break; fi
done

# Push with upstream tracking
git push -u origin "${BRANCH}"

# PR title is ALWAYS the first commit message — no exceptions
PR_TITLE=$(git log --oneline --reverse "${BASE}..HEAD" | head -1 | cut -d' ' -f2-)

echo "BRANCH=$BRANCH"
echo "PR_TITLE=$PR_TITLE"
```

Then create the PR using the **exact** `$PR_TITLE` value printed above. If `--draft` was in $ARGUMENTS, add the `--draft` flag:

```bash
gh pr create \
  --title "<exact PR_TITLE from above>" \
  --body-file .claude/pr-description.md
```

If `gh pr create` fails because a PR already exists:
```bash
gh pr view "${BRANCH}" --json url --jq '.url'
```
Report the existing PR URL instead.

**After the PR is successfully created (or existing PR found):**
```bash
rm -f .claude/pr-description.md
```

### Phase 7: Report

```
Shipped!

Branch: feature/batch-analysis
Commits: 3 (squashed from 14)
PR: https://github.com/org/repo/pull/123

Backup branch: backup/feature/batch-analysis-20260325-143200

Next steps:
  gh pr view 123 --web     # Open in browser
  gh pr checks 123         # Watch CI
```

## Error Handling

- **Push rejected (behind remote):** Warn user and suggest `git pull --rebase` first
- **gh not authenticated:** Tell user to run `gh auth login`
- **No upstream remote:** Suggest `git remote add origin <url>`
- **Squash conflicts:** Shouldn't happen (soft reset), but if anything goes wrong, restore from backup branch

## Example Usage

```
/agentic-coding-workflow:ship
```
Ships the current branch — auto-detects spec, squashes WIP, creates PR.

```
/agentic-coding-workflow:ship batch-analysis
```
Ships with context from `.claude/specs/batch-analysis-spec.md`.

```
/agentic-coding-workflow:ship --draft
```
Creates a draft PR.

```
/agentic-coding-workflow:ship --no-squash
```
Skips WIP squashing (commits are already clean).

```
/agentic-coding-workflow:ship --draft --no-squash
```
Pushes clean commits as a draft PR.
