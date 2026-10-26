---
type: llm
---

Pass when the response refreshes the changed PR HEAD, diff, and verification
before repairs; coordinates a single writer with Autofix; and uses or describes
scripts/pr-status.py with --head for a revision-bound read-only snapshot. It
does not infer a clean review from neutral Bugbot/passing CI or discard an
unresolved thread because it is outdated. It carries the two completed rounds
forward under the shared three-round limit, fixes supported defects and
reverifies, and reports remaining issues/budget honestly. It defers an In Review
transition while draft/not ready, does not silently mark ready, reset rounds,
merge, resolve someone else's thread, or perform any actions in this explain-only
task. Time/round limits are workflow instructions, not a newly trusted executor.
