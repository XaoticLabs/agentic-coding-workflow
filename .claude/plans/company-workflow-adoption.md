# Company workflow adoption and learning plan

Status: planned; training, company rollout, and ongoing programs deferred.
Created 2026-10-25 from the workflow discussion against baseline `227f2b3` and
the subsequent review/readiness changes. The audience works in Go, Python,
and TypeScript, with review as its current bottleneck.

## Problem and goals

Turn the personal workflow into something coworkers can reproduce with their
existing tools and review process. Colleagues should be able to scope a change,
verify behavior, interpret agent findings, explain remaining risks, and deliver
a useful PR with less reviewer effort. Expertise should spread through shared
examples, feedback, and evidence.

This plan records later work. It does not announce training, contact coworkers,
install tools, change company policy, or expand autonomy now.

## Dependencies and boundaries

Use [the review policy](../../references/review-policy.md) and
[project readiness](../../references/project-readiness.md) as the small common
contract. Existing CLI/session features remain responsible for runtime and
recovery. Keep reusable company conventions in their owning repositories;
plugin-specific packaging should be an adapter to those conventions.

Coordinate proof and case selection with
[the benchmark/pilot plan](review-benchmark-and-team-pilot.md). Basic teaching
can begin with clearly labeled demonstrations; productivity claims need actual
pilot evidence. Reproducible setup/containment remains in
[its existing plan](reproducible-setup-and-unattended-execution.md).

## Implementation

1. **Prepare three short recipes.** Use the existing commands for a regression
   fix, a substantial feature, and preparing/reviewing a PR. Show how scope and
   verification scale with uncertainty. Each recipe needs the input/outcome,
   relevant context, actual verification, and a handoff a reviewer can assess.
   Start with ordinary native sessions; introduce Ralph or parallel workers
   when a demonstrated need justifies them. Cover mixed-language contracts
   without requiring users to learn every command.

2. **Select reproducible company examples.** Choose representative tasks across
   Go/Python/TypeScript with code-owner help. Show a failing behavior, a focused
   correction, tests/runtime evidence, and the final reviewer decisions. Include
   a clean review, an agent mistake, and a false finding that a developer
   challenges with evidence. Use suitable internal examples and record setup
   prerequisites; do not manufacture successful before/after claims.

3. **Have a coworker drive the workflow.** Run an observed practice session with
   a colleague who did not build the harness. Let them choose context, execute
   checks, assess findings, and explain the result. Record where they need the
   author's help and fix that friction in canonical docs/configuration. Success
   means they can complete and explain the change independently, including what
   remains unverified; prompt memorization is not an acceptance criterion.

4. **Prepare an internal session.** Working title: “Agentic coding that makes
   review easier.” Use a real task and its evidence to demonstrate the three
   recipes, ownership, and failure recovery. Present pilot results only if they
   exist, with limits. Give attendees a short starting guide, repository setup
   links, and an example PR. Adapt length to the audience and offer hands-on
   practice; no presentation or event is created by this planning task.

5. **Run a lightweight feedback cadence.** Offer optional office hours where
   coworkers bring actual PRs. Keep a small list of recurring friction with an
   owner and example. Put mechanical problems in project tooling, behavior
   failures in regression tests, contextual conventions in short owner guidance,
   and stable repeated procedures in narrowly scoped skills. Retest representative
   cases before keeping a change. Remove stale or redundant instructions as
   model capabilities change.

6. **Assign maintenance and expand based on evidence.** Choose maintainers for
   shared workflow defaults, per-repository operating contracts, and reviewer
   evaluation cases. Record supported CLI/plugin versions, a way to revert a
   workflow update, and a small release checklist using existing validation.
   Review adoption friction and delivery/quality outcomes with the pilot owner.
   Extend to more repositories or autonomy only when evidence and existing
   company rules support it. Keep learning metrics at team level.

## Verification and completion

- [ ] Three concise recipes use existing entrypoints and match their actual
  behavior; the advanced command catalog is optional.
- [ ] Examples reproduce on the selected company environments, with explicit
  setup requirements, actual check evidence, and at least one failure lesson.
- [ ] A coworker independently completes and explains a change; observed
  friction is addressed or documented with an owner.
- [ ] Training materials distinguish demonstrations, measured outcomes, and
  open questions; company review rules are preserved.
- [ ] Maintenance owners, feedback routing, regression cases, and a process for
  retiring unnecessary guidance are recorded in their canonical locations.

## Open decisions

Company sponsors/code owners, representative repositories, training audience,
approved tools, maintainers, session date/format, and office-hour cadence remain
to be agreed. No universal speedup, adoption target, or individual ranking is
promised. Use pilot evidence to decide expansion.

## Research inputs

- [Spotify, 2026-06-03](https://engineering.atspotify.com/2026/6/code-with-claude-coding-is-no-longer-the-constraint): discoverable conventions and review capacity as output rises.
- [DORA, 2026-06-02](https://dora.dev/insights/finding-balance-in-the-era-of-tokenmaxxing/): team capability and outcomes in AI adoption.
- [OpenAI, 2026-09-11](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra): concise descriptions, progressive disclosure, and revisiting accumulated guidance.
- [Anthropic, 2026-10-22](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop): evaluate simpler loops and keep delegation where it helps.
