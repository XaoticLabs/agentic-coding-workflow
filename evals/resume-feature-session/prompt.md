---
name: resume-feature-session
tags: [tuning, launchers, sessions]
allowed_tools: [Read, Glob, Grep, Skill]
max_turns: 6
timeout_seconds: 120
---

I already have a named auth-update feature session with its own worktree,
implementation agent, and active native goal. Using the spawn command, show
the direct CLI invocation to resume it from /opt/agentic-coding-workflow.
Keep its existing condition and role. Explain what happens if native resume
cannot find the session. Do not launch anything, create files, or start a new
session as a fallback.
