# Database MCP Setup Guide

How to configure database connections for use with `/query` and `/analyze`.

## Option 1: Database MCP Servers (Recommended)

MCP servers give Claude direct, structured access to your database. Add them to your project's `.mcp.json`:

### Postgres MCP

```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/mydb"
      }
    }
  }
}
```

For multiple environments, use separate server entries:

```json
{
  "mcpServers": {
    "postgres-local": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/myapp_dev"
      }
    },
    "postgres-staging": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "DATABASE_URL": "postgresql://readonly:pass@staging-db.internal:5432/myapp"
      }
    }
  }
}
```

### BigQuery MCP

```json
{
  "mcpServers": {
    "bigquery": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-bigquery"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account.json",
        "BQ_PROJECT_ID": "my-project-id"
      }
    }
  }
}
```

### MySQL MCP

```json
{
  "mcpServers": {
    "mysql": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-mysql"],
      "env": {
        "MYSQL_HOST": "localhost",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "password",
        "MYSQL_DATABASE": "mydb"
      }
    }
  }
}
```

### SQLite MCP

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sqlite"],
      "env": {
        "SQLITE_DB_PATH": "./data/app.db"
      }
    }
  }
}
```

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

# Authenticate
gcloud auth application-default login

# Set default project
gcloud config set project my-project-id

# Test
bq query --use_legacy_sql=false "SELECT 1"
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

After configuring, test with `/query`:

```
/query "show me the first 5 rows from any table"
```

If it works, you're good. If not, the error message will tell you what's misconfigured.
