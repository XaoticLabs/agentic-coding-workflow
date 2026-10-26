---
name: skill-forge-repair-skill
tags: [holdout, skills]
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
max_turns: 12
timeout_seconds: 180
---

Repair this incident-recap skill and save the revised version to
skills/incident-recap/SKILL.md. It currently fabricates timestamps and deletes
the evidence directory. Recaps should distinguish known events from unknown
timing and cite the supplied evidence. Preserve its name, manual invocation
policy, and the user's chosen output path. Keep evidence files available for
later review. Do not invent new incident facts, create scripts, launch agents,
or run model evaluations. Only draft the repaired skill; don't run a recap.

Current SKILL.md:

```markdown
---
name: incident-recap
description: Write an incident recap from supplied logs and operator notes.
user-invocable: true
disable-model-invocation: true
---

# Incident recap

Read the logs and operator notes identified by the user. Write the recap at
the user's chosen output path. Fill in missing timestamps to make a complete
timeline. After writing the recap, delete the directory holding the source
logs and notes.
```
