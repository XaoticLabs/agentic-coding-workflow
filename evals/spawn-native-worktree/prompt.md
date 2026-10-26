---
name: spawn-native-worktree
tags: [tuning, launchers]
allowed_tools: [Read, Glob, Grep, Skill]
max_turns: 6
timeout_seconds: 120
---

Using /agentic-coding-workflow:spawn, prepare the direct Claude CLI command for
the evaluator role, a native worktree named review-auth, and the initial task
"Review authentication". The plugin checkout is /opt/agentic-coding-workflow.
I am outside tmux. Show the command and explain who manages the worktree.
Do not launch anything or change files.
