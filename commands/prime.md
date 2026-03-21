# Prime Project Context

Prime project context before starting work on a ticket or feature. Gathers essential information about the codebase, current state, and optionally fetches ticket details from Linear.

## Variables

ticket_id: $ARGUMENTS (optional - Linear ticket ID like "AI-3364", can include "--deep" flag)

## Instructions

Parse the arguments to extract:
- `ticket_id`: Any ticket ID pattern (letters followed by dash and numbers, e.g., "AI-3364")
- `deep_mode`: Whether "--deep" flag is present

### Quick Mode (default)

Gather essentials in parallel for speed (~10-15 seconds):

1. **Project Snapshot**
   - Read and summarize README.md (key purpose, setup instructions)
   - Detect tech stack from config files:
     - Elixir/Phoenix: mix.exs, config/config.exs
     - Node.js: package.json
     - Python: pyproject.toml, requirements.txt
     - Other: Makefile, docker-compose.yml

2. **Current Git State**
   - Current branch name
   - Last 5 commits with messages
   - Any uncommitted changes (staged/unstaged)

3. **Ticket Details** (if ticket_id provided)
   - Use the Linear MCP tool to fetch the ticket
   - Extract: title, description, acceptance criteria, status, assignee
   - Note any linked issues or parent tickets

### Deep Mode (--deep flag)

Everything from Quick Mode, plus:

4. **Architecture Analysis**
   - Full directory tree (3 levels deep, excluding node_modules, _build, deps, .git)
   - Contents of docs/ folder if present
   - Look for ARCHITECTURE.md, ADRs, or design docs

5. **Code Patterns** (sample key files to infer conventions)
   - For Elixir/Phoenix:
     - Sample a context module (lib/*/contexts/*.ex or lib/*/*.ex)
     - Sample a schema (lib/*/schemas/*.ex)
     - Sample a controller or live view
     - Sample a test file
   - Note: module naming, error handling patterns, test organization

6. **Recent Activity**
   - Last 20 commits with files changed
   - List of active/recent branches (last 2 weeks)

7. **Configuration**
   - CI/CD setup (.github/workflows/, .gitlab-ci.yml)
   - Linting rules (credo config, .eslintrc)
   - Formatting config (.formatter.exs, prettier)

8. **Dependencies**
   - Key dependencies from mix.exs with brief purpose annotations
   - Note any internal/private dependencies

### Output

1. **Write to project directory**:
   - Save structured summary to `.claude/prime-context/context.md`
   - This keeps context with the project alongside other `.claude/` artifacts (plans, specs, checkpoints)

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

### Elixir/Phoenix Specific Highlights

When working with Elixir/Phoenix projects, specifically highlight:
- Phoenix contexts and their boundaries
- Ecto schemas and their relationships
- LiveView vs traditional controller patterns
- Supervision tree structure (if applicable)
- Background job processing (Oban, etc.)
- API patterns (REST, GraphQL, gRPC)

### Performance Guidelines

- Use parallel file reads wherever possible
- Don't dump raw file contents - summarize and extract key insights
- For large projects, sample representative files rather than reading everything
- Skip binary files, compiled outputs, and dependency directories

## Example Invocations

- `/prime` - Quick context, no ticket
- `/prime AI-3364` - Quick context with Linear ticket AI-3364
- `/prime --deep` - Deep context analysis, no ticket
- `/prime AI-3364 --deep` - Deep context with ticket AI-3364
- `/prime --deep AI-3364` - Same as above (order doesn't matter)

## Error Handling

- If Linear MCP is unavailable or ticket not found, continue without ticket info and note the issue
- If README.md doesn't exist, note that and continue with other context gathering
- If config files don't exist for detected patterns, skip that section gracefully
