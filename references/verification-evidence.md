# Evidence for behavior

Connect each material acceptance claim to the source state, actual check,
observed result, and retained output. Reuse existing PR templates and records;
a separate document is unnecessary for a small change.

**This is not evidence:** a proposed command, imagined debugger execution,
another agent's agreement, an agent-written PASS, or a passing check on older
source. A test proves only the behavior it exercises. A screenshot establishes
appearance, not persistence, permissions, or a successful deployment.

Choose checks that distinguish working behavior from the reported failure:

- Bug fix: reproduce failure on the baseline and success after the fix when
  practical, with existing expectations preserved.
- Product flow: exercise the relevant API/browser interaction and its effects,
  including real service boundaries when part of the criterion.
- Performance: retain commands, identical workloads/environment, repeated
  measurements, correctness checks, variability, and tradeoffs.
- Deployment/flags: inspect the actual target, expected revision/build, rollout
  or flag state, and health. Publishing success alone is narrower evidence.

Report missing prerequisites, failed probes, timeouts, and unrun checks explicitly.
Inspection can support a hypothesis when execution is unavailable; label the
inference and leave runtime claims unverified. Never weaken a check to obtain
a pass. Follow [verification integrity](shared-patterns.md#test-and-verification-integrity).

The experiment, observation, and environment runners retain commands, exits,
durations, source fingerprints, and output. These are reproducible workflow
artifacts, not authenticated approval or tamper-proof acceptance.
