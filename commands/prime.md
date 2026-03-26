---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Agent
  - mcp__claude_ai_Linear__get_issue
  - mcp__claude_ai_Linear__list_issues
effort: medium
---

# Prime Project Context

Prime project context before starting work on a ticket or feature. The deterministic context below was gathered automatically — focus on analysis, synthesis, and ticket details.

## Variables

ticket_id: $ARGUMENTS (optional - Linear ticket ID like "AI-3364", can include "--deep" flag)

## Pre-Gathered Context

The following was injected at invocation time — do NOT re-gather this data with tool calls:

!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/prime-context.sh 2>/dev/null || echo "⚠️ Context script failed — gather manually using the instructions below."`

---

## Instructions

Parse the arguments to extract:
- `ticket_id`: Any ticket ID pattern (letters followed by dash and numbers, e.g., "AI-3364")
- `deep_mode`: Whether "--deep" flag is present

### Quick Mode (default)

The pre-gathered context above already contains git state, tech stack, directory structure, README, and CLAUDE.md. Your remaining work:

1. **Analyze the pre-gathered context** — identify the project's purpose, architecture patterns, and current state from the injected data above. Don't re-read files that were already injected.

2. **Ticket Details** (if ticket_id provided)
   - Use the Linear MCP tool to fetch the ticket
   - Extract: title, description, acceptance criteria, status, assignee
   - Note any linked issues or parent tickets

3. **Synthesize** — connect the dots between project structure, recent git activity, and ticket requirements to form an actionable starting point.

### Deep Mode (--deep flag)

Everything from Quick Mode, plus these additional investigations:

4. **Architecture Analysis**
   - Read any ARCHITECTURE.md, ADRs, or design docs found in the key files list above
   - Read contents of docs/ folder if present

5. **Code Patterns** (sample key files to infer conventions)
   - For Elixir/Phoenix:
     - Sample a context module (lib/*/contexts/*.ex or lib/*/*.ex)
     - Sample a schema (lib/*/schemas/*.ex)
     - Sample a controller or live view
     - Sample a test file
   - For Node.js/TypeScript:
     - Sample a route/controller, a model/schema, a test file
   - For Python:
     - Sample a main module, a test file, config patterns
   - Note: module naming, error handling patterns, test organization

6. **Recent Activity**
   - Last 20 commits with files changed (`git log --oneline --stat -20`)
   - List active/recent branches (`git branch -a --sort=-committerdate | head -15`)

7. **Configuration**
   - CI/CD setup (read workflow files found in directory tree)
   - Linting/formatting config

8. **Dependencies**
   - Key dependencies from the detected stack's config with brief purpose annotations
   - Note any internal/private dependencies

### Elixir/Phoenix Specific Highlights

When working with Elixir/Phoenix projects, specifically highlight:
- Phoenix contexts and their boundaries
- Ecto schemas and their relationships
- LiveView vs traditional controller patterns
- Supervision tree structure (if applicable)
- Background job processing (Oban, etc.)
- API patterns (REST, GraphQL, gRPC)

### Output

1. **Write to project directory**:
   - Save structured summary to `.claude/prime-context/context.md`
   - Ensure `.claude/prime-context/` directory exists first

2. **Display concise summary** in conversation:
   ```
   ## Project: {project_name}
   **Tech Stack:** {detected technologies}
   **Branch:** {current_branch}
   **Recent Changes:** {summary of last few commits}

   {If ticket provided:}
   ## Ticket: {ticket_id} - {ticket_title}
   **Status:** {status}
   {Brief description/acceptance criteria}

   {If deep mode:}
   ## Architecture Highlights
   {Key patterns and conventions discovered}

   ## Ready Status
   Ready to work on [{ticket_title or "this project"}] on branch [{branch}]

   ## Suggested First Steps
   1. {step based on ticket/context}
   2. {step based on ticket/context}
   ```

3. **Keep ticket visible**: If ticket_id provided, reference it as an anchor throughout the session

### Performance Guidelines

- The pre-gathered context eliminates most tool calls for Quick Mode — avoid redundant reads
- Use parallel file reads for Deep Mode investigations
- Don't dump raw file contents — summarize and extract key insights
- For large projects, sample representative files rather than reading everything

## Example Invocations

- `/agentic-coding-workflow:prime` — Quick context, no ticket
- `/agentic-coding-workflow:prime AI-3364` — Quick context with Linear ticket
- `/agentic-coding-workflow:prime --deep` — Deep context analysis, no ticket
- `/agentic-coding-workflow:prime AI-3364 --deep` — Deep context with ticket

## Error Handling

- If the pre-gathered context script failed (see warning above), fall back to manual gathering using Read/Bash tools
- If Linear MCP is unavailable or ticket not found, continue without ticket info and note the issue
- If README.md doesn't exist, note that and continue with other context gathering
