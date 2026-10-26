---
name: ticket-cli-api-routing
tags: [tuning, tickets, connectors]
allowed_tools: [Read, Glob, Grep, Skill]
max_turns: 6
timeout_seconds: 120
---

Explain how this plugin should retrieve and start Jira ticket OPS-42 in my
project using installed CLI tools and direct APIs. Do not execute anything or
write files. My project default is Jira at https://example.atlassian.net;
Linear is also configured. ACLI is installed but its ticket read currently
fails authentication; Jira API credentials work. Should it automatically try
the API or look up OPS-42 in Linear? How would I diagnose and deliberately
choose API access, then preview a transition to our native "Development" status?
I do not use MCP connectors.
