---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Agent
  - AskUserQuestion
  - WebFetch
effort: low
---

# Natural Language Database Query

You are a data analyst assistant. Your task is to translate natural language questions into SQL, run them against the configured database, and present results clearly.

## Input

$ARGUMENTS — One of:
- A natural language question: `"how many users signed up last week?"`
- A question with explicit database target: `--db staging "top 10 accounts by revenue"`
- A question with output format: `--csv "all active campaigns with their owner emails"`
- Raw SQL to run directly: `--raw "SELECT count(*) FROM users WHERE created_at > now() - interval '7 days'"`

## Instructions

### Phase 1: Detect Database Configuration

Determine which database to query by checking, in order:

1. **`--db` flag** — explicit target (e.g., `--db staging`, `--db local`, `--db prod`, `--db bigquery`)
2. **MCP database tools** — check if any database MCP servers are configured (Postgres MCP, BigQuery MCP, etc.)
3. **Environment database CLIs** — check what's available:
   ```bash
   which psql && echo "postgres available"
   which bq && echo "bigquery available"
   which mysql && echo "mysql available"
   which sqlite3 && echo "sqlite available"
   ```
4. **Docker Compose databases** — check for local database containers:
   ```bash
   docker compose ps 2>/dev/null | grep -i postgres
   docker compose ps 2>/dev/null | grep -i mysql
   ```
5. **Project config files** — look for database connection strings:
   ```bash
   # Check common config locations
   grep -r "DATABASE_URL\|DB_HOST\|ecto.*Repo" --include="*.ex" --include="*.exs" --include="*.env" --include="*.yaml" --include="*.yml" . 2>/dev/null | head -20
   ```

If no database is found, explain what's needed and suggest the database MCP setup guide:
```
No database connection detected. To use /agentic-coding-workflow:query, you need one of:
- A database MCP server configured in .mcp.json
- A database CLI (psql, bq, mysql) with access configured
- A local database running in Docker Compose

See skills/data-analytics/references/database-mcp-setup.md for setup instructions.
```

**If `--db prod` is specified**, confirm with the user before proceeding: "This will run a query against production. The query will be read-only (SELECT). Proceed?"

Present the detected configuration:
```
Database: [type — Postgres/BigQuery/MySQL/SQLite]
Connection: [via MCP / CLI / Docker]
Target: [local/staging/prod]
```

### Phase 2: Understand the Schema

Before writing SQL, understand what's available:

**Via MCP** — use the database MCP's schema introspection tools if available.

**Via CLI:**
```bash
# Postgres — list tables
psql $DATABASE_URL -c "\dt" 2>/dev/null

# Postgres — describe a table
psql $DATABASE_URL -c "\d <table_name>"

# BigQuery — list tables in dataset
bq ls <dataset>

# BigQuery — show schema
bq show --schema <dataset>.<table>

# MySQL
mysql -e "SHOW TABLES;" <database>
mysql -e "DESCRIBE <table>;" <database>
```

**Use a subagent for schema exploration** if the question touches multiple tables or you're unsure which tables are relevant. Have the subagent:
1. List all tables
2. Find tables related to the question's domain (users, campaigns, revenue, etc.)
3. Check column names and types on relevant tables
4. Look for foreign key relationships
5. Return a mini schema summary

Cache the schema context mentally — don't re-query schema for follow-up questions in the same session.

### Phase 3: Generate SQL

Translate the natural language question into SQL:

1. **Identify the target tables** from the schema
2. **Map natural language concepts to columns** (e.g., "signed up" → `created_at`, "last week" → `>= now() - interval '7 days'`)
3. **Write the SQL** following these rules:
   - Always use `SELECT` — never write `INSERT`, `UPDATE`, `DELETE`, `DROP`, or any DDL
   - Use explicit column names, not `SELECT *` (unless the user specifically asks for all columns)
   - Add `LIMIT 100` by default unless the user asks for all results or an aggregate
   - Use appropriate date functions for the database dialect
   - Use CTEs for complex queries (readability)
   - Add comments explaining non-obvious logic

4. **Present the SQL to the user before running:**
   ```sql
   -- Natural language: "how many users signed up last week?"
   SELECT
     date_trunc('day', created_at) AS signup_date,
     count(*) AS signups
   FROM users
   WHERE created_at >= now() - interval '7 days'
   GROUP BY 1
   ORDER BY 1;
   ```
   Ask: "Run this query?" (skip confirmation for simple, obviously safe queries)

**If `--raw` flag is used**, validate the SQL is read-only (SELECT only) and run directly.

### Phase 4: Execute the Query

Run via the appropriate method:

**Via MCP:**
Use the configured database MCP tool to execute the query.

**Via CLI:**
```bash
# Postgres
psql $DATABASE_URL -c "<query>" --pset=format=aligned

# Postgres with CSV output
psql $DATABASE_URL -c "<query>" --csv

# BigQuery
bq query --use_legacy_sql=false "<query>"

# BigQuery with CSV
bq query --use_legacy_sql=false --format=csv "<query>"

# MySQL
mysql -e "<query>" <database>

# SQLite
sqlite3 <db_file> "<query>" -header -column
```

**Handle errors:**
- Syntax errors → fix the SQL and retry (once)
- Permission errors → report and suggest checking access
- Timeout → suggest adding more filters or LIMIT
- No results → confirm the filters are correct, suggest broadening

### Phase 5: Present Results

Format results based on the data shape:

**Small result sets (< 20 rows):**
Display as a formatted markdown table.

**Large result sets (20-100 rows):**
Display the first 10 rows as a table, note the total count, and offer to save as CSV.

**Single value / aggregates:**
Highlight the answer prominently:
```
→ 1,247 users signed up last week
```

**Time series data:**
Present as a table and note the trend:
```
Signups are up 23% week-over-week (892 → 1,098).
```

**If `--csv` flag was used:**
Save results to a file:
```bash
psql $DATABASE_URL -c "<query>" --csv > /tmp/query_results.csv
```
Report the file path and row count.

### Phase 6: Follow-Up

After presenting results, be ready for:
- "Break that down by [dimension]" → add GROUP BY
- "Filter to only [condition]" → add WHERE clause
- "Show me the raw data" → remove aggregation
- "Save this as CSV" → re-run with CSV output
- "Analyze this" → suggest `/agentic-coding-workflow:analyze` with the results

## Safety Rules

- **Read-only queries only** — never execute INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or any DDL
- **Production requires confirmation** — always confirm before running against prod
- **Limit by default** — add LIMIT 100 unless aggregating or user explicitly asks for all
- **No credential exposure** — never echo connection strings or passwords in output
- **Sanitize inputs** — if the user's question contains anything that looks like SQL injection, flag it (shouldn't happen in practice, but be safe)

## Error Handling

**No database found:**
Explain what's needed and point to setup guide.

**Query returns an error:**
Show the error, explain what went wrong in plain language, fix and retry once.

**Results are unexpected:**
Ask: "These results look [unusual pattern]. Want me to check the query logic?"

**Connection timeout:**
Suggest checking network/VPN, or trying a different connection method.

## Example Usage

```
/agentic-coding-workflow:query "how many users signed up last week?"
```
Detects database, generates SQL with date filter, runs it, returns the count.

```
/agentic-coding-workflow:query --db staging "top 10 accounts by total revenue"
```
Connects to staging, joins accounts with revenue data, returns ranked list.

```
/agentic-coding-workflow:query --csv "all active campaigns with owner email and creation date"
```
Runs the query and saves results to a CSV file.

```
/agentic-coding-workflow:query --raw "SELECT status, count(*) FROM orders WHERE created_at > '2024-01-01' GROUP BY 1"
```
Validates the SQL is read-only, runs it directly, presents results.

```
/agentic-coding-workflow:query --db bigquery "what's our daily active user count for the past 30 days?"
```
Uses bq CLI to query BigQuery, returns time series data with trend summary.
