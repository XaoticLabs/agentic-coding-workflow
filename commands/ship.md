---
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
  - AskUserQuestion
effort: medium
---

# Ship — Push a Branch and Create a PR

Prepares a concrete publishing action, applies the project’s approval policy and existing authorization, pushes the branch, creates a PR, and reports the URL. Creating a PR does not merge it.

## Input

$ARGUMENTS - Either:
- Empty — operates on current branch, auto-detects spec
- A spec path or slug (e.g., `batch-analysis` or `.claude/specs/batch-analysis-spec.md`) — uses for PR description context
- `--draft` flag — creates a draft PR instead of a ready-for-review PR
- `--no-squash` — accepted for compatibility; this command preserves commits. History rewriting requires a separate request.

## Instructions

### Phase 1: Pre-flight

```bash
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

**If there are uncommitted changes:** Follow any existing instruction to commit or exclude them. Otherwise, use AskUserQuestion to resolve which changes to ship before preparing the publishing proposal.

**If zero commits ahead of base:** Stop with "No commits to ship. Nothing to do."

Read the project's verification requirements and configured commands using **Project Context: Test and Lint Command Detection** in `${CLAUDE_PLUGIN_ROOT}/references/shared-patterns.md`. Reuse verification evidence only for the current commit and relevant working inputs; otherwise run the required configured checks. Resolve failing required checks before publishing. Report unavailable or unconfigured required checks explicitly and follow project policy for proceeding; do not replace them with a preferred toolchain or claim they passed.

### Phase 2: Find Context for PR Description

**Auto-detect spec/plan/ralph summary:**
- If spec provided in $ARGUMENTS, use it
- Otherwise, look for specs matching the branch name in `.claude/specs/`
- Also check `.claude/plans/` for a corresponding plan
- Check for Ralph summary: read `.claude/ralph-logs/ralph-summary-<slug>.md` if it exists for run metrics and context

**Gather context:**
```bash
# Commit history for context
git log --oneline "${BASE}..HEAD"

# Diff stats
git diff --stat "${BASE}..HEAD"

# Full diff for understanding changes
git diff "${BASE}..HEAD"
```

### Phase 3: Detect PR Template

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

### Phase 4: Generate PR Description and Title

**If a PR template was found:**

Read the template file. Preserve its exact structure — headings, sections, checkboxes, and any boilerplate text the team expects. Fill in each section intelligently using the spec, plan, commit log, and diff:

- **Headings/sections** (e.g., `## Description`, `## What Changed`, `## Motivation`) — fill with content derived from the spec summary, plan rationale, or commit messages. Match the section's intent.
- **Checklist items with empty checkboxes** (e.g., `- [ ] Tests added`) — check off items (`- [x]`) that are demonstrably true based on the diff and test results. Leave unchecked items that aren't applicable or can't be verified.
- **Placeholder text** (e.g., `<!-- Describe your changes -->`, `_Replace this with..._`) — replace with actual content. Remove HTML comments that were meant as instructions to the author.
- **Sections you can't fill** (e.g., `## Screenshots`, `## Jira Ticket`) — leave the heading in place with a brief note like `N/A` or `TODO` so the author can fill it in. Never delete template sections.
- **Static boilerplate** (e.g., team conventions, reviewer checklists, legal notices) — preserve exactly as-is.

The goal is that a reviewer opening the PR sees their familiar template fully filled out, not a generic description pasted over it.

Fit the **PR evidence** facts from
`${CLAUDE_PLUGIN_ROOT}/references/review-policy.md` into existing sections.
Distinguish tests actually run from planned checks, name the checked source
state, and surface remaining reviewer decisions and recovery details when
relevant. Link to artifacts instead of pasting large logs. Preserve the template;
do not add a second checklist that repeats it.

Write the filled template to `.claude/pr-description.md`.

**If no PR template was found:**

Fall back to the default format:

```markdown
## Summary
- (problem, observable before/after behavior, and important implementation decision)

## Verification
- Checked source: (commit SHA, or identified worktree state)
- (actual command, result, and scope; link to relevant runtime/CI evidence)
- Not run / limitations: (required checks still unavailable, or none)

## Reviewer decisions
- (specific remaining behavior, compatibility, or architecture decisions, or none)

## Recovery
- (revert/disable approach and data limitations when consequential; omit if inapplicable)
```

Write to `.claude/pr-description.md`.

In both cases, keep content concise. The diff speaks for itself — focus on the "why" and testing strategy, not re-describing every line changed.

Choose a concise PR title that describes the final change, following repository conventions. Use the full diff and resulting behavior; the first commit subject is context, not a required title. Save the exact title to `.claude/pr-title.txt`.

### Phase 5: Review the Proposed External Action

Before any push or PR creation, prepare and show the concrete proposal:

- Repository identity and remote push destination (redact credentials if present)
- Local branch and exact HEAD commit; destination branch and push refspec
- PR repository, base and head branches, exact title, complete description, and draft status
- Verification results and any unresolved limitations

Apply **External Actions and Approval** in `${CLAUDE_PLUGIN_ROOT}/references/shared-patterns.md`. Honor any project requirement to review this proposal. Ask for approval only when the action is outside existing authorization or the workflow explicitly requires review of the final content. An instruction to implement code alone does not authorize publishing. An instruction to ship can authorize ordinary pushes and PR creation within that scope; do not repeatedly ask for the same approval.

If approval is needed, finish the proposal first, ask using AskUserQuestion, and wait. Apply requested changes and present the revised proposal before proceeding. Preserve the approved content for execution. A Markdown comment, local description file, or agent-authored log is never proof of human approval.

This plugin supplies an instruction-level review policy, not an enforceable approval boundary. There is no ship gate or approval marker. If an organization requires enforcement, the external permission service or publishing executor must hold approvals outside agent-writable storage and validate the bound action and content. See the shared policy for the binding requirements. Do not claim that shell-string matching or `allowed-tools` proves approval.

### Phase 6: Push and Create PR

Immediately before each external action, compare the current repository, remote destination, branch, HEAD, base/head selection, title, body, and draft status with the proposal. If a material value changed, update the proposal and obtain any newly required authorization. Do not reuse approval for changed content.

Use explicit repository and branch arguments. The following is a command shape: substitute the reviewed values and preserve their exact contents. Read the title from `.claude/pr-title.txt` and pass the body as a file; do not interpolate body text into shell source.

```bash
# REVIEWED_* values come from the proposal, revalidated immediately above.
PR_TITLE=$(cat .claude/pr-title.txt)
git push "$REVIEWED_REMOTE" "${REVIEWED_COMMIT}:refs/heads/${REVIEWED_HEAD_BRANCH}"
gh pr create \
  --repo "$REVIEWED_PR_REPOSITORY" \
  --base "$REVIEWED_BASE_BRANCH" \
  --head "$REVIEWED_PR_HEAD" \
  --title "$PR_TITLE" \
  --body-file .claude/pr-description.md
```

Add `--draft` only when included in the proposal. Run the push and PR creation sequentially and stop on failure. Never force-push as a recovery step without authorization. If the push succeeds and PR creation fails, report the published branch and retain the description for a retry; do not ask to approve the unchanged push again.

If a PR already exists, retrieve its URL with `gh pr view` using the reviewed repository and branch. Report the existing PR without editing its title or description unless that edit is authorized. Keep the local proposal until the outcome is confirmed.

### Phase 7: Report

```
Shipped!

Branch: feature/batch-analysis
Published commit: <SHA>
Commits: 3
PR: https://github.com/org/repo/pull/123

Next steps:
  gh pr view 123 --web     # Open in browser
  gh pr checks 123         # Watch CI
```

## Error Handling

- **Push rejected (behind remote):** Warn user and suggest `git pull --rebase` first
- **gh not authenticated:** Tell user to run `gh auth login`
- **No upstream remote:** Suggest `git remote add origin <url>`
- **Proposal changed:** Revalidate the action and content against existing authorization before publishing
- **Partial publishing failure:** Report which action succeeded and retain the proposal for retry

## Example Usage

```
/agentic-coding-workflow:ship
```
Ships the current branch — auto-detects context, prepares the publishing proposal, and creates a PR within the applicable authorization.

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
Preserves commits (also the default).

```
/agentic-coding-workflow:ship --draft --no-squash
```
Pushes clean commits as a draft PR.
