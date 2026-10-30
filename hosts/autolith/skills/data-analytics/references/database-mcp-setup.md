# Database MCP Setup Guide

How to configure database connections for use with `/agentic-coding-workflow:query` and `/agentic-coding-workflow:analyze`.

## Option 1: Pinned DBHub MCP Integration

Use [Bytebase DBHub](https://github.com/bytebase/dbhub) for PostgreSQL, MySQL, and SQLite. This guide pins **`@bytebase/dbhub@1.5.0`** and requires **Node.js >= 22.5.0** and `npx`. The PostgreSQL and SQLite reference servers are [archived and no longer maintained](https://github.com/modelcontextprotocol/servers-archived). Replace their entries rather than installing them. The previous BigQuery and MySQL `@modelcontextprotocol` package examples were not verified integrations and have been removed.

### Configure a read-only connection

Copy the supplied [`dbhub.toml`](dbhub.toml) into your project's `.claude/dbhub.toml`:

```toml
[[sources]]
id = "analytics"
dsn = "${ANALYTICS_DATABASE_URL}"

[[tools]]
name = "execute_sql"
source = "analytics"
readonly = true
max_rows = 100

[[tools]]
name = "search_objects"
source = "analytics"
```

Set the connection string and absolute configuration path **in the shell that starts Claude**. Choose one database:

```bash
# PostgreSQL — use a read-only database role and URL-encode credentials.
export ANALYTICS_DATABASE_URL='postgres://readonly:REPLACE_ME@localhost:5432/myapp?sslmode=require'

# MySQL — alternative to the PostgreSQL DSN above.
export ANALYTICS_DATABASE_URL='mysql://readonly:REPLACE_ME@localhost:3306/myapp?sslmode=require'

# SQLite — alternative; point to an existing file using an absolute path.
export ANALYTICS_DATABASE_URL="sqlite://$(pwd)/data/app.db"

export DBHUB_CONFIG_PATH="$(pwd)/.claude/dbhub.toml"
```

Add this project `.mcp.json` entry. Claude expands the environment references; DBHub expands the DSN reference inside the TOML file:

```json
{
  "mcpServers": {
    "analytics": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "--yes", "@bytebase/dbhub@1.5.0",
        "--transport", "stdio",
        "--config", "${DBHUB_CONFIG_PATH}"
      ],
      "env": {
        "ANALYTICS_DATABASE_URL": "${ANALYTICS_DATABASE_URL}"
      }
    }
  }
}
```

For multiple environments, duplicate the entry under a different server name, set a separate configuration-path variable, and map its `ANALYTICS_DATABASE_URL` to a separate DSN variable such as `${STAGING_DATABASE_URL}`. Credentials stay outside committed files. DBHub's read-only tool setting supplements a least-privilege database account; it does not replace database permissions.

Configuration references: [DBHub CLI and DSNs](https://dbhub.ai/config/command-line), [TOML configuration](https://dbhub.ai/config/toml), [read-only SQL tools](https://dbhub.ai/tools/execute-sql), and [Claude MCP environment expansion](https://code.claude.com/docs/en/mcp#environment-variable-expansion-in-mcp-json).

### Reproduce the smoke test

From this plugin checkout, run:

```bash
python3 skills/data-analytics/scripts/smoke-test-db-mcp.py
```

The first run downloads the pinned package. It uses the supplied TOML configuration, a temporary SQLite file, and MCP stdio to check initialization, tool discovery, `SELECT 1`, and write rejection. It does not need Claude authentication or database credentials. When intentionally upgrading DBHub, update the package pin in both this guide and the smoke script, then rerun it.

Verified on 2026-10-25 with DBHub 1.5.0 and Node.js 26.7.0: SQLite initialization, tool listing, query execution, and read-only enforcement passed. PostgreSQL and MySQL DSN formats match the upstream documentation; live connections require your database and credentials and were not exercised by this SQLite test. Before relying on either connection, open `/mcp`, confirm the server is connected, and request `SELECT 1 AS connection_ok` through its SQL tool.

### BigQuery

Use Google's maintained **`bq` CLI** in Option 2. DBHub does not support BigQuery. This guide does not provide a BigQuery MCP package configuration. See the [official bq reference](https://cloud.google.com/bigquery/docs/reference/bq-cli-reference).

## Option 2: Database CLIs

If you prefer CLI tools over MCP, ensure they're installed and configured:

### psql (Postgres)

```bash
# Install
brew install postgresql

# Configure connection (pick one):

# Via DATABASE_URL env var
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# Via .pgpass file (no password prompts)
echo "host:5432:dbname:user:password" >> ~/.pgpass
chmod 600 ~/.pgpass

# Via pg_service.conf (named connections)
cat >> ~/.pg_service.conf << EOF
[local]
host=localhost
port=5432
dbname=myapp_dev
user=postgres

[staging]
host=staging-db.internal
port=5432
dbname=myapp
user=readonly
EOF

# Usage: psql service=local, psql service=staging
```

### bq (BigQuery)

```bash
# Install Google Cloud SDK
brew install google-cloud-sdk

# Authenticate the gcloud/bq CLI
gcloud auth login

# Set default project
gcloud config set project my-project-id

# Test
bq query --use_legacy_sql=false "SELECT 1"
```

### sqlite3

```bash
# Use an existing database without allowing writes.
sqlite3 -readonly ./data/app.db "SELECT 1 AS connection_ok;"
```

### mysql

```bash
# Install
brew install mysql-client

# Configure via ~/.my.cnf
cat >> ~/.my.cnf << EOF
[client]
host=localhost
user=root
password=password
database=mydb
EOF
```

## Option 3: Docker Compose Databases

For local development databases running in Docker:

```bash
# Find the running database container
docker compose ps | grep postgres

# Connect directly
docker compose exec postgres psql -U postgres -d myapp_dev

# Or expose the port and use psql locally
# In docker-compose.yml:
#   ports:
#     - "5432:5432"
psql -h localhost -U postgres -d myapp_dev
```

## Security Best Practices

1. **Use read-only credentials** for analytics queries — never give Claude write access
2. **Don't commit credentials** — use environment variables or `.env` files (gitignored)
3. **Use `.mcp.json` in `.gitignore`** if it contains credentials, or use env var references
4. **For production databases**, use a read replica or read-only user
5. **Set statement timeouts** to prevent runaway queries:
   ```sql
   -- Postgres: 30 second timeout
   SET statement_timeout = '30s';
   ```

## Verifying Your Setup

After configuring, test with `/agentic-coding-workflow:query`:

```
/agentic-coding-workflow:query "show me the first 5 rows from any table"
```

For MCP, first verify `/mcp` reports the server connected and a `SELECT 1 AS connection_ok` query succeeds. Connection failures may require checking credentials, network access, TLS options, or SQLite file paths; a successful tool listing alone does not prove database access.
