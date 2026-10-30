# Decide

Use [the report template](../assets/report.md). Compare per-case outcomes and
required verification first, then turnaround, repair/intervention effort, and
cost. Show counts and denominators, trial spread, and interrupted attempts;
do not average successful runs alone and conceal failures. Explain novel
findings or disagreements using source evidence. Model agreement is not runtime
proof. A small comparison supplies a signal, not a universal reliability claim.

Choose against the saved criteria:

- **Keep:** required protections and checks hold for the final candidate, the
  planned comparison supports the intended benefit, and remaining limitations
  are consistent with the agreed decision criteria.
- **Revise:** a useful hypothesis remains, but there is a regression, confound,
  missing evidence, or unresolved tradeoff. Set the next action and retain the
  failed candidate and prior trials. Missing native runs cannot establish a
  behavioral or latency benefit.
- **Reject:** the evidence does not justify the candidate or its maintenance
  cost. Record what was learned. Reverting changes needs the same ownership
  and authorization care as ordinary development; do not reset unrelated work.

Append the decision, rationale, evidence links, checked candidate, and
limitations to `decisions` in `experiment.json`; preserve earlier decisions.
Set `stage` to `complete` for keep/reject, or the appropriate next step for
revise. Set `next_action` even when it is simply to start another experiment.

Only after **keep**, write `.claude/improvements/baseline.json` with:

```json
{
  "experiment": "prime-context",
  "source": {
    "revision": "full checked commit SHA",
    "worktree_sha256": "checked working-input digest",
    "scope": "revision"
  }
}
```

Use actual source values. Preserve any earlier baseline in the decision history
before replacing the pointer. This file is a convenience for discovery, not a
trusted approval, merge authorization, or permission to reuse stale evidence.
It records the accepted candidate; it does not check it out or publish it.
For an uncommitted candidate, retain its exact patch or owned checkout before
making it the next baseline; the fingerprint alone cannot reconstruct it.

Update `report.md` so the next reader can see the decision and next action
without reading raw traces. For this plugin, retain a sanitized benchmark
summary under `evals/benchmarks/` using its existing retention policy.

Turn confirmed misses or costly repetition into small, relevant tuning cases.
Do not accumulate a new universal rule for every incident. Extend automation
when repeated experiments demonstrate the same manual friction; keep ordinary
product edits on their normal verification path.
