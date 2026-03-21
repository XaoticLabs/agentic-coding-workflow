---
globs:
  - "hooks/**/*"
description: Rules for writing and modifying hooks
---

# Hook Development Rules

## Registration
- All hooks MUST be registered in `hooks/hooks.json` — unregistered scripts do nothing
- Use `${CLAUDE_PLUGIN_ROOT}` for script paths in hooks.json
- Set appropriate `timeout` values (default is fine for most; use 5s for fast checks)

## Script Hooks (type: "command")
- Read JSON from stdin to get hook context (tool_name, tool_input, session_id, etc.)
- Exit codes: 0 = allow, 1 = error (logged, doesn't block), 2 = block execution
- For Stop hooks: output `{"decision": "block", "reason": "..."}` JSON to block
- Always handle JSON parse errors gracefully — exit 0 on failure, never block on hook bugs

## Prompt Hooks (type: "prompt")
- Preferred for judgment calls that need Claude's reasoning
- The `prompt` field contains inline text — there is no file reference option
- Prompt hooks expect JSON responses: `{"ok": true}` or `{"ok": false, "reason": "..."}`
- **Every code path in the prompt MUST return JSON** — never use "say nothing" or empty responses. Even the "nothing to do" path must return `{"ok": true}`
- **Add a subagent guard clause** as the first instruction: "If this is a subagent session or there is no meaningful conversation history, respond `{"ok": true}` immediately." — subagent stops have minimal context and will cause "No assistant message found" errors without this
- Optional `model` field (defaults to fast model); optional `timeout` (defaults to 30s)
- Keep prompts concise — they consume context on every invocation

## Infinite Loop Prevention
- Stop hooks MUST check for `stop_hook_active` flag to prevent re-triggering
- If your hook blocks, Claude will try again — make sure the second attempt can succeed

## Testing
- Test hooks manually with: `echo '{"tool_name":"Bash","tool_input":{"command":"test"}}' | python hook.py`
- Verify both the allow and block paths
