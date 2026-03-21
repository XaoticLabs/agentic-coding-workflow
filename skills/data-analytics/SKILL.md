---
name: data-analytics
description: >
  Database querying and data analysis support. Use when: configuring database connections,
  setting up database MCP servers, troubleshooting database access, understanding how
  /query and /analyze commands work, connecting to Postgres, BigQuery, MySQL, SQLite,
  database CLI setup, MCP server configuration for databases, read-only database access,
  SQL query help, data visualization setup.
  Keywords: database, MCP, postgres, bigquery, mysql, sqlite, psql, bq, query, analyze,
  data, analytics, metrics, SQL, connection, setup, configure.
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
user-invocable: false
---

# Data Analytics Support

This skill provides reference material for database connectivity and the `/query` and `/analyze` commands.

## When to Load

- User asks about setting up database connections for Claude
- User has trouble with `/query` or `/analyze` not finding a database
- User wants to configure a database MCP server

## References

- `references/database-mcp-setup.md` — Full setup guide for Postgres, BigQuery, MySQL, SQLite via MCP servers, CLIs, or Docker Compose

## Related Commands

- `/query` — Natural language to SQL, runs queries, returns results
- `/analyze` — Takes data (CSV, JSON, query results) and produces insights + HTML visualizations
