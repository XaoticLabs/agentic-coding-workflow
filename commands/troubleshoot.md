---
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Agent
  - AskUserQuestion
  - EnterPlanMode
  - ExitPlanMode
  - WebFetch
effort: high
---

# Troubleshoot Infrastructure Issue

Diagnose and resolve issues across local Docker, staging Kubernetes, and production Kubernetes environments. Includes quick kubectl access for common k8s operations.

## Input

$ARGUMENTS — One of:
- A service/namespace + symptom: `integrations "rabbitmq connection refused"`
- With explicit env: `--env staging integrations "pod crashlooping"`
- With explicit env: `--env local postgres "replication lag"`
- With explicit env: `--env prod accounts "500 errors on login"`
- A kubectl shortcut: `logs integrations`, `pods campaigns --status`, `exec messaging "bin/messaging remote"`
- A Slack thread URL or pasted error message
- A Linear ticket ID (e.g., `ENG-1234`)

## Quick K8s Operations

If the input matches a kubectl shortcut pattern, skip the full troubleshooting flow and execute directly:

| Pattern | Action |
|---------|--------|
| `logs <service> [flags]` | Tail last 100 log lines |
| `pods <service> [--status]` | Show pods, optionally with details |
| `events <service> [-n N]` | Show recent events (default 20) |
| `exec <service> "<cmd>"` | Exec into a pod |
| `describe <service>` | Describe pods for a service |
| `top <service>` | Show resource usage |
| `restart <service>` | Rollout restart (with confirmation) |
| `rollback <service>` | Undo last rollout (with confirmation) |
| `scale <service> <N>` | Scale deployment (with confirmation) |

All shortcuts default to staging. Use `--env prod` to target production (always requires confirmation).

### Namespace Resolution

Fuzzy match service names to namespaces:
- Exact: `integrations` → `integrations`
- Aliases: `rabbit`/`rmq` → check within `integrations`
- Partial: `msg` → `messaging`, `acct` → `accounts`, `notif` → `notifications`
- Ambiguous → list matches and ask user

### K8s Execution

```bash
# Set context
kubectl config use-context arn:aws:eks:us-east-2:604412908292:cluster/staging-eks  # staging
kubectl config use-context arn:aws:eks:us-east-2:940766330009:cluster/prod-eks     # prod (confirm first!)

# Find pod
POD=$(kubectl -n <ns> get pods -l app=<service> -o jsonpath='{.items[0].metadata.name}')

# Operations
kubectl -n <ns> logs $POD --tail=100
kubectl -n <ns> get pods
kubectl -n <ns> get events --sort-by='.lastTimestamp' | tail -20
kubectl -n <ns> exec -it $POD -- <command>
kubectl -n <ns> describe pods -l app=<service>
kubectl -n <ns> top pods -l app=<service>
kubectl -n <ns> rollout restart deployment/<service>
kubectl -n <ns> rollout undo deployment/<service>
kubectl -n <ns> scale deployment/<service> --replicas=<N>
```

For Elixir services, `bin/<service> remote` opens an IEx console.

Highlight errors in logs, flag non-Running pods, summarize event warnings.

---

## Full Troubleshooting Flow

For symptom-based inputs (not kubectl shortcuts), run the structured diagnostic flow:

## Environment Reference

**Local Docker** — compose stack (Postgres, RabbitMQ, etc.)
**Staging** — your staging cluster
**Prod** — your production cluster

Discover namespaces and services from the project's own configuration.

### Phase 1: Parse Input & Determine Environment

1. Extract **target service** and **symptom** from input
2. Determine environment:
   - `--env` flag → use that
   - Mentions "docker", "compose", "local" → local
   - Mentions "pod", "k8s", "deployment" → staging (default)
   - **Never default to prod** — require explicit `--env prod`
3. If Linear ticket or Slack URL, fetch to extract service + symptom
4. If **prod**, confirm before proceeding

### Phase 2: Environment Health Check

**Local Docker:**
```bash
docker compose ps
docker compose logs --tail=50 <service>
docker inspect <container> --format='{{.State}}'
```

**Kubernetes:**
```bash
kubectl -n <namespace> get pods
kubectl -n <namespace> get events --sort-by='.lastTimestamp' | tail -20
kubectl -n <namespace> describe pod <pod-name>
kubectl -n <namespace> logs <pod-name> --tail=100
kubectl -n <namespace> logs <pod-name> --previous  # crash logs
```

### Phase 3: Diagnose

Follow the diagnostic path matching the symptom:

**CrashLoopBackOff:** Check previous logs, events (OOMKilled, image pull), resource limits, recent rollout history.

**Connection Refused/Timeout:** Check target service running, service endpoints, network policies. For RabbitMQ: queue status. For Postgres: connections, locks, replication.

**High Latency:** Check resource usage (`top pods`), HPA status, pending pods.

**500 Errors:** Tail logs with error filter, check replica health, dependent services, recent config changes.

**Docker-specific:** Container health, logs, network inspect, volumes, `docker stats`.

### Phase 4: Check Dependent Services

Most issues are caused by dependencies. Identify what the service depends on (database, queue, cache, other services), health check each, and check cross-namespace DNS resolution.

### Phase 5: Root Cause Analysis

```markdown
## Troubleshooting Report

**Environment:** [local/staging/prod]
**Service:** [name]
**Symptom:** [reported issue]

### Findings
- [observations from each diagnostic step]

### Root Cause
[most likely cause based on evidence]

### Evidence
- [specific log lines, events, or metrics]

### Recommended Fix
- [step-by-step remediation]
```

### Phase 6: Remediate (with approval)

- **Local Docker:** Apply directly
- **Staging:** Propose fix, apply after confirmation
- **Prod:** Always require explicit approval, never auto-apply

Common fixes: pod restart, rollback, scale up, docker compose restart. Re-run health check after remediation.

## Safety Rules

- **Read-only by default** — all diagnostics are non-destructive
- **Prod requires explicit confirmation** for every command
- **Never delete or modify k8s resources in prod** without user saying "yes"
- **Never exec into prod containers** without approval
- **Mutating operations** (restart, rollback, scale) require confirmation in both environments

## Example Usage

```
/agentic-coding-workflow:troubleshoot integrations "rabbitmq connection refused"
/agentic-coding-workflow:troubleshoot --env local postgres "connection timeout"
/agentic-coding-workflow:troubleshoot --env prod accounts "pod crashlooping"
/agentic-coding-workflow:troubleshoot logs integrations
/agentic-coding-workflow:troubleshoot pods campaigns --status
/agentic-coding-workflow:troubleshoot --env prod events accounts -n 30
/agentic-coding-workflow:troubleshoot exec messaging "bin/messaging remote"
/agentic-coding-workflow:troubleshoot restart integrations
```
