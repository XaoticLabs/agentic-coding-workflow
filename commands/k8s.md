---
allowed-tools:
  - Bash
  - AskUserQuestion
  - Grep
---

# Kubernetes Quick Access

A context-aware kubectl wrapper that knows our namespace layout and provides fast access to common Kubernetes operations.

## Input

$ARGUMENTS — One of:
- `logs <service> [flags]` — Tail logs for a service
- `pods <service> [--status]` — Show pods, optionally with status details
- `events <service> [-n N]` — Show recent events (default 20)
- `exec <service> "<command>"` — Exec into a pod
- `describe <service>` — Describe pods for a service
- `top <service>` — Show resource usage
- `restart <service>` — Delete pods to trigger restart
- `rollback <service>` — Undo last deployment rollout
- `scale <service> <replicas>` — Scale deployment
- `--env staging|prod` — Environment flag (default: staging)

## Environment Reference

**Staging EKS** — `arn:aws:eks:<REGION>:<STAGING_ACCOUNT_ID>:cluster/<STAGING_CLUSTER>` (default)
**Prod EKS** — `arn:aws:eks:<REGION>:<PROD_ACCOUNT_ID>:cluster/<PROD_CLUSTER>`

Known namespaces: Configure your namespace list here (e.g., api, auth, billing, frontend, workers, etc.)

## Instructions

### Phase 1: Parse Input

1. Extract the **operation** (logs, pods, events, exec, describe, top, restart, rollback, scale)
2. Extract the **service name**
3. Extract the **environment** — default to staging unless `--env prod` is specified
4. Extract any additional flags or arguments

### Phase 2: Resolve Namespace

The service name maps to a namespace. Use fuzzy matching:
- Exact match: `api` → namespace `api`
- Common aliases: map common shorthand to full namespace names
- Partial match: `fe` → `frontend`, `wk` → `workers`, `db` → `database`
- If ambiguous, list matching namespaces and ask user to pick

### Phase 3: Set Context

```bash
# Staging (default)
kubectl config use-context arn:aws:eks:<REGION>:<STAGING_ACCOUNT_ID>:cluster/<STAGING_CLUSTER>

# Prod — CONFIRM FIRST
kubectl config use-context arn:aws:eks:<REGION>:<PROD_ACCOUNT_ID>:cluster/<PROD_CLUSTER>
```

**If prod:** Always confirm with the user before running any command: "About to run [command] against **production**. Proceed?"

### Phase 4: Execute

Run the appropriate kubectl command:

**logs:**
```bash
# Find the pod first
POD=$(kubectl -n <ns> get pods -l app=<service> -o jsonpath='{.items[0].metadata.name}')
kubectl -n <ns> logs $POD --tail=100 -f
```
If `--previous` flag is present, add `--previous` for crash logs.

**pods:**
```bash
kubectl -n <ns> get pods
```
If `--status` flag: also run `kubectl -n <ns> describe pods` for detailed status.

**events:**
```bash
kubectl -n <ns> get events --sort-by='.lastTimestamp' | tail -<N>
```

**exec:**
```bash
POD=$(kubectl -n <ns> get pods -l app=<service> -o jsonpath='{.items[0].metadata.name}')
kubectl -n <ns> exec -it $POD -- <command>
```
For Elixir services, `bin/<service> remote` opens an IEx console.

**describe:**
```bash
kubectl -n <ns> describe pods -l app=<service>
```

**top:**
```bash
kubectl -n <ns> top pods -l app=<service>
```

**restart:**
```bash
kubectl -n <ns> rollout restart deployment/<service>
```
**Always confirm before executing**, especially in prod.

**rollback:**
```bash
kubectl -n <ns> rollout undo deployment/<service>
```
**Always confirm before executing.** Show rollout history first.

**scale:**
```bash
kubectl -n <ns> scale deployment/<service> --replicas=<N>
```
**Always confirm before executing.** Show current replica count first.

### Phase 5: Report

Display the command output clearly. For long outputs, summarize key findings:
- For logs: highlight error lines and recent patterns
- For pods: flag any non-Running/non-Ready pods
- For events: highlight warnings and errors

## Safety Rules

- **Default to staging** — never assume prod
- **Prod confirmation required** for every command, even read-only
- **Mutating operations** (restart, rollback, scale) require confirmation in both environments
- **Never run `kubectl delete` on deployments, services, or namespaces** — only pods for restart
- **exec into prod** requires explicit user approval

## Example Usage

```
/k8s logs api
```
Tails the last 100 lines of logs from the api service in staging.

```
/k8s pods workers --status
```
Shows all pods in the workers namespace with detailed status.

```
/k8s --env prod events auth -n 30
```
Shows the last 30 events in the auth namespace in production (with confirmation).

```
/k8s exec api "bin/api remote"
```
Opens a remote console on the api service in staging.
