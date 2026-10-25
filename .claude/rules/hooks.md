---
paths:
  - "hooks/**/*"
---

# Hook Development Rules

## Registration
- All hooks MUST be registered in `hooks/hooks.json` — unregistered scripts do nothing
- Use `${CLAUDE_PLUGIN_ROOT}` for script paths in hooks.json
- Set appropriate `timeout` values (default is fine for most; use 5s for fast checks)

## Script Hooks (type: "command")
- Read JSON from stdin to get hook context (tool_name, tool_input, session_id, etc.)
- Follow the event-specific contract in the [current hook reference](https://code.claude.com/docs/en/hooks). Prefer exit 0 with structured JSON, or exit 2 with stderr for an intentional block. Other exits are hook errors; they are not a portable permission decision.
- For Stop hooks: output `{"decision": "block", "reason": "..."}` JSON to continue work on an unmet requirement. Plain stdout is not model feedback. Use `systemMessage` for a user-facing notice; Stop `additionalContext` also continues the conversation.
- For PostToolUse/PostToolUseFailure feedback, use `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"..."}}` with the matching event name. PostToolUse only runs for successful calls; register PostToolUseFailure to observe failures and interruptions.
- StopFailure replaces Stop after API errors. Output and exit code cannot resume, pause, or retry the turn. Log `error`, optional `error_details`, and optional `last_assistant_message` (which is the API error text for this event).
- At Stop, use `last_assistant_message` for notifications. The transcript may not yet contain the final response; never infer pending approvals from stale transcript tool calls.
- Optional notifications and audit hooks fail open on invalid input. Policy gates must return an intentional block when they cannot verify a requirement; use `onFailure: "block"` for eligible events so crashes and timeouts cannot bypass enforcement.

## Prompt Hooks (type: "prompt")
- Preferred for judgment calls that need Claude's reasoning
- The `prompt` field contains inline text — there is no file reference option
- Prompt hooks expect JSON responses: `{"ok": true}` or `{"ok": false, "reason": "..."}`
- **Every code path in the prompt MUST return JSON** — never use "say nothing" or empty responses. Even the "nothing to do" path must return `{"ok": true}`
- **Add a subagent guard clause** as the first instruction: "If this is a subagent session or there is no meaningful conversation history, respond `{"ok": true}` immediately." — subagent stops have minimal context and will cause "No assistant message found" errors without this
- Optional `model` field (defaults to fast model); optional `timeout` (defaults to 30s)
- Keep prompts concise — they consume context on every invocation

## Infinite Loop Prevention
- Optional Stop hooks may skip `stop_hook_active`. Required verification must check correction turns again; reuse a success only when HEAD and the source fingerprint still match.
- Bound correction attempts per session. After three failed attempts, record `blocked` and stop with an explicit user-visible failure using `continue: false`; never turn exhaustion into acceptance. A new user turn may start a fresh attempt.
- Verification uses check-only formatter flags and must never run fixes. Check committed code as well as worktree edits; bind results to the HEAD revision and worktree fingerprint, and invalidate them if either changes. Keep formatting in an explicit action.

## Testing
- Test hooks manually with: `echo '{"tool_name":"Bash","tool_input":{"command":"test"}}' | python hook.py`
- Verify both the allow and block paths
