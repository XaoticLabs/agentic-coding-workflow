---
name: test-audit
description: "Review existing tests for observable protection, meaningful assertions, duplication, and maintenance cost. Return evidence-backed candidates; do not delete tests as an audit side effect."
metadata:
  workflow-source: "skills/test-audit/SKILL.md"
---


# Test audit

Use [review policy](../../references/review-policy.md) and the project's actual
test commands. Audit the requested scope, not every test merely because it is
present. This workflow reports findings; it does not weaken acceptance criteria,
delete tests, change thresholds, or disable checks without that requested scope.

For each proposed change, identify:

- The observable failure the test protects, with its public entrypoint and
  expected outcome. Contract/configuration tests can protect real behavior;
  a source-text assertion is not automatically worthless.
- Evidence that the test runs and can fail for the intended defect. A targeted
  mutation or historical regression is useful when it can run in an isolated
  candidate. Never leave mutations in the working source.
- The concrete maintenance cost: repeated coverage of the same failure, brittle
  coupling to implementation layout, no meaningful assertion, a fake that
  bypasses the real boundary, or expensive setup without additional protection.
- What protection remains after the proposed correction, replacement, or removal.
  Name overlapping tests and verify that they exercise the same failure.

Prefer improving a useful test over deleting it. Tests of timeout, error,
cancellation, stale evidence, and rejected acceptance paths can be valuable even
when the success path is simple. Do not infer low value from test count, file
length, private-function use, or a test that rarely catches a bug.

Return a short ranked list of evidence cards: test, failure protected, evidence,
cost, proposed change, preserved coverage, and uncertainty. A clean audit is a
valid result. Keep fixture/controller evidence distinct from live model quality
or provider compatibility. Any authorized edits must rerun the affected behavior
and project-required gates.
