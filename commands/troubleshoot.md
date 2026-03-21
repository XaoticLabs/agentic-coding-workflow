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
  - TaskCreate
  - TaskUpdate
  - TaskGet
  - WebFetch
---

# Troubleshoot Infrastructure Issue

You are an infrastructure debugger. Your task is to diagnose and resolve issues across local Docker, staging Kubernetes, and production Kubernetes environments using a structured troubleshooting flow.

## Input

$ARGUMENTS — One of:
- A service/namespace + symptom: `integrations "rabbitmq connection refused"`
- With explicit env: `--env staging integrations "pod crashlooping"`
- With explicit env: `--env local postgres "replication lag"`
- With explicit env: `--env prod accounts "500 errors on login"`
- A Slack thread URL or pasted error message
- A Linear ticket ID (e.g., `ENG-1234`)

## Environment Reference

**Local Docker** — your project's compose stack (e.g., Postgres, RabbitMQ, Redis)
**Staging EKS** — `arn:aws:eks:<REGION>:<STAGING_ACCOUNT_ID>:cluster/<STAGING_CLUSTER>`
**Prod EKS** — `arn:aws:eks:<REGION>:<PROD_ACCOUNT_ID>:cluster/<PROD_CLUSTER>` — same topology

Known namespaces: Configure your namespace list here (e.g., api, auth, billing, frontend, workers, etc.)

## Instructions

### Phase 1: Parse Input & Determine Environment

1. **Extract the target service** and **symptom description** from the input
2. **Determine the environment:**
   - If `--env` flag is provided, use that environment
   - If the symptom mentions "docker", "compose", "container", or "local" → local
   - If the symptom mentions "pod", "k8s", "deployment", "namespace" → staging (default k8s)
   - If unclear, **default to staging** — it's the safest place to investigate
   - **Never default to prod** — always require explicit `--env prod`
3. **If input is a Linear ticket or Slack URL**, fetch it first to extract service + symptom
4. Present your understanding to the user:
   ```
   Environment: [local/staging/prod]
   Service: [name]
   Symptom: [description]
   ```
   If this is **prod**, confirm with the user before proceeding: "This will run read-only commands against production. Proceed?"

### Phase 2: Environment Health Check

Run these checks based on the target environment:

#### Local Docker
```bash
docker compose ps                              # Container status
docker compose logs --tail=50 <service>        # Recent logs
docker inspect <container> --format='{{.State}}'  # Detailed state
```

#### Kubernetes (Staging/Prod)
First, ensure the right context:
```bash
# Staging
kubectl config use-context <STAGING_CLUSTER_CONTEXT>

# Prod (only if explicitly requested)
kubectl config use-context <PROD_CLUSTER_CONTEXT>
```

Then gather status:
```bash
kubectl -n <namespace> get pods                          # Pod status
kubectl -n <namespace> get events --sort-by='.lastTimestamp' | tail -20  # Recent events
kubectl -n <namespace> describe pod <pod-name>           # Detailed pod info
kubectl -n <namespace> logs <pod-name> --tail=100        # Recent logs
kubectl -n <namespace> logs <pod-name> --previous        # Previous crash logs (if restarting)
```

### Phase 3: Diagnose

Based on the health check output, follow the appropriate diagnostic path:

**Pod CrashLoopBackOff:**
1. Check previous logs: `kubectl -n <ns> logs <pod> --previous`
2. Check events for OOMKilled, image pull errors, config issues
3. Check resource limits: `kubectl -n <ns> describe pod <pod> | grep -A5 Limits`
4. Check if recent deployments changed anything: `kubectl -n <ns> rollout history deployment/<name>`

**Connection Refused / Timeout:**
1. Check if the target service is running: `kubectl -n <target-ns> get pods`
2. Check service endpoints: `kubectl -n <target-ns> get endpoints <service>`
3. Check network policies: `kubectl -n <ns> get networkpolicies`
4. For RabbitMQ: check queue status via management API or exec
5. For Postgres: check connection count, locks, replication status

**High Latency / Performance:**
1. Check resource usage: `kubectl -n <ns> top pods`
2. Check HPA status: `kubectl -n <ns> get hpa`
3. Check for pending pods: `kubectl -n <ns> get pods --field-selector=status.phase=Pending`

**500 Errors / Application Errors:**
1. Tail application logs with error filtering: `kubectl -n <ns> logs <pod> --tail=500 | grep -i error`
2. Check if all replicas are healthy
3. Check dependent services (database, message queue, cache)
4. Look for recent config changes: `kubectl -n <ns> get configmaps`

**Docker-specific (local):**
1. Check container health: `docker compose ps`
2. Check logs: `docker compose logs --tail=100 <service>`
3. Check network: `docker network ls && docker network inspect <network>`
4. Check volumes: `docker volume ls`
5. Check resource usage: `docker stats --no-stream`

### Phase 4: Check Dependent Services

Most issues are caused by dependencies. For the affected service:
1. Identify what it depends on (database, message queue, cache, other services)
2. Run health checks on each dependency
3. For k8s: check cross-namespace service DNS resolution
4. Report dependency health status

### Phase 5: Root Cause Analysis

Present findings:
```markdown
## Troubleshooting Report

**Environment:** [local/staging/prod]
**Service:** [name]
**Symptom:** [reported issue]

### Findings
- [What was observed in each diagnostic step]

### Root Cause
[Most likely root cause based on evidence]

### Evidence
- [Specific log lines, events, or metrics that support this]

### Recommended Fix
- [Step-by-step remediation]

### Dependencies Checked
- [Service]: [healthy/unhealthy - details]
```

### Phase 6: Remediate (with approval)

If the fix is clear and safe:
1. **For local Docker:** Apply the fix directly (restart container, update config, etc.)
2. **For staging:** Propose the fix and apply after user confirms
3. **For prod:** Present the fix and **always** ask for explicit approval. Never make changes to prod without confirmation.

Common remediations:
- Restart a pod: `kubectl -n <ns> delete pod <pod>` (will be recreated by deployment)
- Rollback a deployment: `kubectl -n <ns> rollout undo deployment/<name>`
- Scale up: `kubectl -n <ns> scale deployment/<name> --replicas=<N>`
- Docker restart: `docker compose restart <service>`

After remediation, re-run the health check from Phase 2 to verify the fix.

## Safety Rules

- **Read-only by default** — all diagnostic commands are read-only
- **Prod requires explicit confirmation** for any command, even read-only
- **Never delete or modify k8s resources in prod** without user saying "yes, apply this to prod"
- **Never exec into prod containers** without user approval
- **If uncertain about the environment**, ask — don't guess

## Example Usage

```
/troubleshoot api "rabbitmq connection refused"
```
Investigates the api service in staging (default) for RabbitMQ connectivity issues.

```
/troubleshoot --env local postgres "connection timeout"
```
Checks the local Docker Compose stack for Postgres connection issues.

```
/troubleshoot --env prod auth "pod crashlooping"
```
Investigates crashlooping pods in the auth namespace in production (with confirmation).
