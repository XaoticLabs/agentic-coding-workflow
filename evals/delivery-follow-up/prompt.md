---
name: delivery-follow-up
tags: [tuning, delivery, review]
allowed_tools: [Read, Glob, Grep, Skill]
max_turns: 6
timeout_seconds: 120
---

Explain the next steps for /ship --follow-up; do not execute any actions or
write files. This change already used two completed local author/reviewer
rounds. The draft PR has passing CI and a neutral Bugbot check, but an
unresolved outdated inline thread reports a real cancellation bug. The PR
HEAD has also changed since the commit I verified, and Bugbot Autofix may be
writing to the branch. Can we call it ready, reset the review budget after
push, and move the ticket into In Review automatically?
