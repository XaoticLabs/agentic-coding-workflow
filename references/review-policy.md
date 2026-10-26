# Review and delivery policy

Use this policy when planning reviewable changes, preparing a PR, reviewing a
diff, or coordinating an author/reviewer repair cycle. Keep the consuming
project's required checks, owners, and human approval rules.

## Reviewable changes

Give each change one understandable behavior or interface outcome and enough
verification to assess it independently. For substantial work, identify useful
review and integration boundaries before implementation. Keep necessary code,
tests, and migration support together; separate unrelated refactoring. Do not
impose a universal line-count limit or split work into changes that cannot be
understood or tested on their own.

Increase concurrent implementation only when review capacity supports it. When
reviews accumulate, finish evidence, respond to existing feedback, or help
review before starting additional changes. Do not create an automatic queue
limit without a team decision.

## PR evidence

Fit these facts into the repository's existing PR template. Use short prose or
a small table, omit inapplicable detail, and link to large artifacts:

- **Intent and behavior:** the problem, observable before/after behavior, and
  the important implementation decision. Reference the issue or criteria.
- **Verification:** the actual commands, outcomes, scope, and checked commit
  or working-input fingerprint. Separate observed results from a test plan.
  Include relevant API, integration, browser, or log evidence when the behavior
  calls for it. Unit tests alone may leave important integration paths untested.
- **Limits and reviewer decisions:** unavailable checks, remaining assumptions,
  compatibility concerns, and the specific decisions requiring human judgment.
  State that none remain when supported; do not invent concerns.
- **Recovery:** how to undo or disable a consequential change, including data
  or migration limitations. A simple revert description is enough when valid.

Use passing evidence only for the source state it checked. Agent-authored tests
and another agent's agreement do not establish acceptance by themselves. Follow
**Test and Verification Integrity** in `shared-patterns.md`. Existing human
review and branch protection remain authoritative; a review verdict is not
authorization to publish or merge.

## Findings that help reviewers

Default to actionable defects in behavior, compatibility, reliability,
security, and materially important maintainability. Investigate callers,
contracts, guards, and existing conventions before reporting a concern.
Include severity, confidence, file/line evidence, reachable trigger, causal
path, consequence, and remaining uncertainty. A concise causal explanation can
cover several of these facts; do not repeat it under many headings.

Keep important design questions separate from established defects. Uncertain
candidates belong under open questions when a human decision or unavailable
evidence matters. Do not turn uncertainty into a blocker. Group tool diagnostics
by root cause and link to their output instead of duplicating every warning.
Do not report pre-existing defects as introduced by this change.

A clean result is valid. There is no finding quota. Omit praise sections, phase
scorecards, and mechanical style comments from the default report. Include
nonblocking design/taste suggestions only when explicitly requested (for
example, `/review --suggestions`); label them optional and keep them out of
blocking counts. Learn mode may retain its teaching and scoring structure.

## Review convergence

An ordinary invocation performs one review pass. Do not start an author/fix
loop unless the task authorizes it. For an authorized continuing review:

1. Carry the criteria, base/head revisions, round count, and prior findings with
   their dispositions: open, fixed, rejected with evidence, or accepted by the
   responsible human. Give a delegated reviewer this history along with the
   current diff; keep its assessment independent of the author's conclusions.
2. The initial pass reviews the full change and relevant surrounding code.
   Subsequent passes inspect new edits, their callers/invariants, and previous
   fixes. Expand scope for an actual dependency or newly supported risk.
3. Do not repost an unchanged finding or reopen a rejected one without new
   evidence. Identify a repeated bug class and affected instances together.
   A fix in one location does not resolve uncorrected instances elsewhere.
4. Use a default budget of **three completed review rounds per logical change**.
   Round three may finish successfully. If material findings remain, preserve
   the report and hand off for human reassessment; never convert exhaustion
   into PASS. A commit, model change, or new reviewer does not reset the count.
   A human may explicitly authorize an extension or a revised approach.
5. Record the reviewed revision, round, remaining findings, and next action in
   the report or continuing conversation. If history is unavailable, say so
   and perform one pass without claiming a known round count or starting a
   fresh automatic budget. These are workflow instructions, not a trusted
   executor enforcing an external approval boundary.

Convert recurring confirmed defects into regression tests or appropriate
project checks. Capture contextual review guidance with code owners. Proposed
rules and reviewer changes need evidence that they reduce misses or noise;
historical bugs and known-clean PRs are useful evaluation inputs.
