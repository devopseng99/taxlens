# TaxLens Platform Substrate — Extracting the System from the Instance

Updated: 2026-04-25 | Based on TaxLens v3.62.0 (83 waves) | Cluster: RKE2 2-node (mgplcb03/mgplcb05)

---

# SECTION 1 — PLATFORM SUBSTRATE INVENTORY

## A. Storage Layer

### StorageClass

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: my-local-storage
provisioner: kubernetes.io/no-provisioner
reclaimPolicy: Delete          # but PVs override with Retain
volumeBindingMode: WaitForFirstConsumer
```

- **Provisioner**: `no-provisioner` — volumes are manually pre-created on the node.
- **Binding**: `WaitForFirstConsumer` prevents scheduling conflicts with nodeAffinity.
- Created 2026-01-26, shared by every app on the cluster.

### PV Layout at `/opt/k8s-pers/vol1/`

**Convention**: `{component}-{app-name}` subdirectories.

| App | Subpath | Size | Owner | Node | Purpose |
|-----|---------|------|-------|------|---------|
| TaxLens | `psql-taxlens` | 5Gi | 999:999 | mgplcb05 | PostgreSQL data |
| TaxLens | `taxlens-docs` | 10Gi | root | mgplcb05 | Uploaded documents + PDFs |
| TaxLens | `taxlens-agent-repos` | 2Gi | root | mgplcb03 | Agent git conversation store |
| TaxLens | `backups/taxlens` | host | root | mgplcb05 | Daily pg_dump (hostPath, not PV) |
| OpenFile | `psql-openfile` | 15Gi | 999:999 | mgplcb05 | PostgreSQL |
| OpenFile | `redis-openfile` | 5Gi | 0:0 | mgplcb05 | Redis AOF |
| Harness | `psql-harness-prd` | 8Gi | 999:999 | mgplcb05 | PostgreSQL |
| Harness | `mongo-harness-prd` | 10Gi | 1001:1001 | mgplcb05 | MongoDB |
| Harness | `redis-harness-prd` | 10Gi | 1000:1000 | mgplcb05 | Redis Sentinel |
| Harness | `minio-harness-prd` | 10Gi | 1001:1001 | mgplcb05 | MinIO |
| Gastown | `gastown-data` | 10Gi | 1000:1000 | mgplcb05 | Workspace data |
| Gastown | `gastown-home` | 5Gi | 1000:1000 | mgplcb05 | Home directory |

**Provisioning flow**:
1. `scripts/provision-node-dirs.sh` SSHes to the target node
2. Creates directory with `mkdir -p` and `chown` to correct UID:GID
3. PV YAML references the path with `local.path` + `nodeAffinity`
4. `claimRef` pre-binds to the expected PVC (prevents orphan binding)
5. Reclaim policy: `Retain` on every PV (manual cleanup on uninstall)

**PV Template Pattern** (from TaxLens):
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: {app}-{component}-pv
spec:
  capacity:
    storage: {size}
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: my-local-storage
  local:
    path: /opt/k8s-pers/vol1/{component}-{app}
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values: [mgplcb05]
  claimRef:
    namespace: {namespace}
    name: {pvc-name}
```

### Backup Pattern

- **Daily CronJob** in `taxlens-db` namespace: `pg_dump | gzip > /backups/taxlens-${TIMESTAMP}.sql.gz`
- **Retention**: 7 days via `find -mtime +7 -delete`
- **Storage**: hostPath `/opt/k8s-pers/vol1/backups/taxlens` (DirectoryOrCreate)
- **No snapshot support**: `my-local-storage` has no VolumeSnapshot capability
- **Gap**: No off-node backup copy. If mgplcb05 disk fails, backups are lost too.
- **Gap**: No automated restore testing.

---

## B. Image Pipeline

### Why scp Is Broken

Remote `.bashrc` prints `Welcome USER=hr1` on non-interactive SSH. `scp` interprets the banner text as protocol data → "Received message too long" error. **Workaround**: pipe via `cat`.

### Build → Transfer → Import → Rollout

```bash
# 1. Build (always --no-cache after source changes — podman caches COPY layers by content hash)
cd /var/lib/rancher/ansible/db/{app}
podman build --no-cache --network=host -t localhost/{app}-{component}:latest -f Dockerfile .

# 2. Save to tar
rm -f /tmp/{app}.tar
podman save localhost/{app}-{component}:latest -o /tmp/{app}.tar

# 3. Transfer and import (cat-pipe workaround for scp banner)
cat /tmp/{app}.tar | ssh -i ~/.ssh/id_rsa_devops_ssh 192.168.29.147 \
  "cat > /tmp/{app}.tar && \
   sudo /var/lib/rancher/rke2/bin/ctr --address /run/k3s/containerd/containerd.sock \
     -n k8s.io images import /tmp/{app}.tar && \
   rm /tmp/{app}.tar"

# 4. Rollout restart
kubectl rollout restart deployment/{app}-{component} -n {namespace}
kubectl rollout status deployment/{app}-{component} -n {namespace} --timeout=120s
```

### Image Naming Convention

- Registry: `localhost/` (never pushed to remote registry)
- Format: `localhost/{app}-{component}:latest` (e.g., `localhost/taxlens-api:latest`)
- Tag: Always `:latest` — we don't use semver tags in containerd. Version tracked in app code + git tags.
- `pullPolicy: Never` in all Helm values (images are local only)

### ctr Namespace

- Always `-n k8s.io` — RKE2's containerd uses `k8s.io` namespace (not `default`)

### Multi-Node Distribution

- **We don't distribute to all nodes.** Images imported only to mgplcb05.
- **nodeSelector** on deployments pins pods to the node with the image.
- Exception: TaxLens Agent runs on mgplcb03 — its image is imported there instead.
- **Gap**: If scheduler lands a pod on the wrong node → `ImagePullBackOff` or stale cached image.

### Failure Modes

| Failure | Symptom | Recovery |
|---------|---------|----------|
| Partial tar transfer | `ctr import` fails with corrupt archive | Re-run the full cat-pipe command |
| Stale tag after rebuild | Pod runs old image despite new build | `crictl rmi <old-sha>` on node, re-import, delete pod |
| Mid-rollout OOM | New pod evicted before old pod terminates | Wait for DiskPressure/MemoryPressure taint to clear (~5min), then re-rollout |
| --network=host omitted | npm `EIDLETIMEOUT` during build | Re-run with `--network=host` |

---

## C. Cloudflared Tunnel Layer

### Architecture

- **Chart**: `/var/lib/rancher/ansible/cf/cloudflare-tunnel/` (v0.3.2)
- **Tunnel**: `hto-rnch-v2-3-1` (ID: `e4955a83-0216-4f37-b43f-6c866245e853`)
- **Replicas**: 2 (HA, anti-affinity preferred spread)
- **Config model**: **Remote API** — Cloudflare dashboard controls ingress rules, NOT the ConfigMap
- **Account**: `9709bd1f498109e65ff5d1898fec15ee`

### Wildcard Behavior

- `*.istayintek.com` is a CNAME → the tunnel
- Specific entries (e.g., `dropit.istayintek.com`) are placed BEFORE the wildcard in the Cloudflare dashboard
- The wildcard catches everything else and routes to an nginx deployment for static pipeline apps

### Adding a New App Hostname — Exact Sequence

1. **Create DNS record**: CNAME `{app}.istayintek.com` → `e4955a83-0216-4f37-b43f-6c866245e853.cfargotunnel.com` (proxied)
2. **Add tunnel ingress rule** via Cloudflare dashboard API or UI:
   - Hostname: `{app}.istayintek.com`
   - Service: `http://{service-name}.{namespace}.svc.cluster.local:{port}`
   - Place BEFORE the `*.istayintek.com` wildcard catch-all
3. **Verify**: `curl -s https://{app}.istayintek.com/health`
4. DNS propagation: Instant (Cloudflare proxy, no TTL wait)

### Current Tunnel Routes

| Hostname | Backend Service | Port |
|----------|----------------|------|
| dropit.istayintek.com | taxlens-api.taxlens.svc | 8000 |
| taxlens-portal.istayintek.com | taxlens-portal.taxlens-portal.svc | 8080 |
| taxlens-agent.istayintek.com | taxlens-agent.taxlens-agent.svc | 8001 |
| openfile.istayintek.com | openfile-df-client.openfile.svc | 3000 |
| openfile-api.istayintek.com | openfile-api.openfile.svc | 8080 |
| hng.istayintek.com | harness-nginx.harness-prd.svc | 80 |
| gastown.istayintek.com | gastown.gastown.svc | 8080 |
| *.istayintek.com | nginx wildcard (pipeline apps) | 80 |

---

## D. Kubernetes App Skeleton

### Namespace Policy

**One namespace per app** (sometimes split for DB isolation):
- `taxlens` (API + UI), `taxlens-db` (PG + PostgREST + Redis), `taxlens-portal`, `taxlens-agent`
- `openfile` (all-in-one), `direct-file` (all-in-one)
- `harness-prd` (all-in-one), `gastown` (all-in-one)

DB isolation is the TaxLens pattern. Most apps use single namespace.

### Deployment Template Defaults

```yaml
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {app}
      app.kubernetes.io/component: {component}
  template:
    spec:
      nodeSelector:
        kubernetes.io/hostname: mgplcb05    # pin to image node
      containers:
        - name: {component}
          image: localhost/{app}-{component}:latest
          imagePullPolicy: Never
          ports:
            - containerPort: {port}
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              memory: 256Mi
```

### Resource Sizing Tiers

| Tier | CPU Request | Memory Request | Memory Limit | Use Case |
|------|------------|----------------|--------------|----------|
| Micro | 10m | 32Mi | 64Mi | Nginx frontends, sidecar containers |
| Small | 25-50m | 48-64Mi | 96-128Mi | PostgREST, Redis, CronJobs |
| Medium | 50-100m | 128-192Mi | 256-384Mi | Python APIs, Portal |
| Large | 100-250m | 256-512Mi | 512Mi-1Gi | Spring Boot APIs, PostgreSQL |
| XL | 250-500m | 512Mi-1Gi | 1-2Gi | Heavy JVM apps |

### Probe Defaults

```yaml
startupProbe:
  httpGet:
    path: /health
    port: {port}
  failureThreshold: 10
  periodSeconds: 5        # 50s max startup

livenessProbe:
  httpGet:
    path: /health
    port: {port}
  periodSeconds: 30
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health
    port: {port}
  periodSeconds: 10
  failureThreshold: 3
```

PostgreSQL uses `exec: pg_isready` instead of httpGet. Redis uses `exec: redis-cli ping`.

### Secrets Pattern

- Secrets created externally via `scripts/setup-secrets.sh` (openssl rand + kubectl create secret --dry-run=client -o yaml | kubectl apply -f -)
- Referenced in deployments via `env.valueFrom.secretKeyRef`
- Never mounted as files (except CF tunnel credentials)
- No Vault integration. No sealed-secrets. Plain K8s secrets.
- `--rotate` flag on setup-secrets.sh regenerates all passwords

### NetworkPolicy Pattern

Default: allow Cloudflare tunnel ingress + DB internal:
```yaml
# netpol-allow-cfd.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-cfd-to-{app}
  namespace: {namespace}
spec:
  podSelector: {}
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: cfd
      ports:
        - port: {app-port}
```

---

## E. Database Layer

### PostgreSQL 16 Pattern

**StatefulSet** (not Deployment) with single replica:
- Image: `postgres:16-alpine`
- Init args: `-c log_min_messages=warning -c log_checkpoints=off -c log_connections=off -c log_disconnections=off`
- PVC via VolumeClaimTemplate binding to pre-created PV
- PGDATA: `/var/lib/postgresql/data/pgdata`
- Password from K8s secret

### PostgREST Exposure

- Image: `postgrest/postgrest:v12.2.3`
- Fronts PostgreSQL with automatic REST API from schema
- JWT auth: `PGRST_JWT_SECRET` from K8s secret
- Anonymous role: `app_anon` (read-only public endpoints)
- Authenticated role: `app_tenant` (RLS-enforced per-tenant access)
- Admin role: `app_admin` (full access)
- Schema: `PGRST_DB_SCHEMAS=public`
- Max rows: 1000, DB pool: 10
- Log level: warn

### Decision Tree: Per-App Schema vs Database vs Cluster

| Scenario | Choice | Rationale |
|----------|--------|-----------|
| Single app, <20 tables | Per-app database, shared PG cluster | TaxLens pattern — simple, isolated |
| Multiple apps needing cross-queries | Per-app schema in shared database | Not used yet |
| App with heavy write load | Dedicated PG StatefulSet | OpenFile pattern |
| No relational data needed | Skip PostgreSQL entirely | Gastown uses embedded Dolt |

### Migration Tooling

**Custom Python Flyway** (`/app/db/flyway/`):
- Pure Python, no JVM dependency
- Sequential migrations: `V001__create_schema.sql`, `V002__roles_and_rls.sql`, etc.
- Checksum validation prevents tampered migrations
- Runs as Helm post-install/post-upgrade hook Job
- CLI: `python -m app.db.flyway migrate --db-url postgres://...`

### Connection Pooling

**No PgBouncer.** PostgREST has built-in pool (`PGRST_DB_POOL=10`). Single-replica API means ~10 concurrent DB connections max. At current scale, PgBouncer would add complexity without benefit.

---

## F. Schema Management

- Schemas live in-app: `/app/db/flyway/migrations/` inside each app's repo
- Versioning: Sequential (`V001`, `V002`, ..., `V007`)
- Forward-only: No down migrations. Rollback = fix forward.
- PostgREST schema reload: `NOTIFY pgrst, 'reload schema'` after migration (automatic via Flyway hook)
- Multi-app dependency: None. Each app has its own database. Cross-app access via REST API (e.g., TaxLens API reads OpenFile's PostgreSQL for document import).

---

## G. CI/CD and Version Control

### Repo Layout

**Polyrepo** — each component is a separate GitHub repo:

| Repo | Purpose | Deploy Chart Location |
|------|---------|----------------------|
| `devopseng99/taxlens` | API + Engine + DB migrations | `charts/taxlens/` + `charts/taxlens-db/` |
| `devopseng99/taxlens-portal` | Portal UI | `charts/taxlens-portal/` |
| `devopseng99/taxlens-agent` | Claude Agent | `charts/taxlens-agent/` |
| `devopseng99/taxlens-landing` | Landing (CF Workers) | `wrangler.toml` |

Rationale: Each component has different build toolchain (Python, Astro/CF Workers) and deploy cadence.

### Branching Strategy

- `main` branch only. No feature branches for TaxLens (single developer, wave-by-wave delivery).
- Git tags per wave: `v3.58.0` through `v3.62.0`
- GitHub releases created per wave with changelog

### Version Bump

Version string lives in **4 places** in `main.py`:
1. FastAPI constructor: `version="3.62.0"`
2. Health endpoint dict: `"version": "3.62.0"`
3. OpenAPI metadata
4. Startup log message

Plus `test_wave34_infrastructure.py` asserts the version string.

### Component Coupling

| API Version | Minimum Portal | Minimum Agent | Notes |
|-------------|---------------|---------------|-------|
| v3.33.0+ | v2.0.0+ | v1.0.0+ | OAuth endpoint required |
| v3.52.0+ | v2.6.0+ | v1.0.1+ | Grafana metrics, billing routes |

No formal dependency declaration. Portal calls API internally; version mismatch surfaces as runtime 404/422 errors.

---

## H. Smoke Tests and Validation

### Post-Deploy Smoke

**In-cluster CronJob** (`k8s/cronjob-smoke-test.yaml`):
- Runs every 30 minutes
- Tests: `/health`, `/ready`, `/docs`, `/metrics`
- Image: `curlimages/curl:8.7.1`
- Timeout: 60s, no retries

**External Smoke** (`tests/smoke_test_tax_drafts.sh`):
- 31 scenarios covering all 4 filing statuses, multi-state, business income, investments, crypto, retirement
- Requires `TAXLENS_API_KEY` env var
- Validates: response structure, form generation, draft retrieval, PDF listing
- Run manually: `TAXLENS_API_KEY=... bash tests/smoke_test_tax_drafts.sh`

### Unit Tests

- 1,499 tests across 61 wave test files
- Run: `python -m pytest tests/ --tb=short -q` (~23 seconds)
- Each wave has dedicated file: `test_wave{N}_{feature}.py`

### Gaps

- No automated E2E (Playwright) post-deploy — manual via `/pc-v7-smoke` skill
- No database migration verification in CI
- No contract tests between API and Portal
- No canary deployment — all-or-nothing rollout

---

## I. Observability

### Logs

- All services: `WARNING` level (Python, PostgreSQL, Redis, PostgREST)
- No Splunk integration. Logs via `kubectl logs`.
- No log aggregation across namespaces.

### Metrics

- Prometheus scrape at `/metrics` (FastAPI instrumentation)
- 7 custom metrics: `taxlens_drafts_total`, `taxlens_ocr_pages_total`, `taxlens_active_tenants`, `taxlens_computation_duration_seconds`, `taxlens_api_requests_total`, `taxlens_webhook_deliveries_total`, `taxlens_stripe_mrr`
- Grafana dashboards provisioned via `grafana_dashboards.py` (4 dashboards: API perf, business, tenant, infra)

### Alerts

4 rules defined in `grafana_dashboards.py`:
1. `TaxLensHighErrorRate` — 5xx > 5% over 5min (critical)
2. `TaxLensHighLatency` — P95 > 2s over 5min (warning)
3. `TaxLensDiskUsageHigh` — disk > 80% over 10min (warning)
4. `TaxLensWebhookFailures` — failed rate > 0 over 15min (warning)

### Traces

- None. No OpenTelemetry, no Linkerd tap.
- Linkerd2 is installed (`/var/lib/rancher/ansible/db/linkerd2/`) but not actively used for tracing.

---

## J. Security Posture

- **No StackRox/ACS** — cluster is not enterprise-managed
- **No OPA Gatekeeper** — no admission controllers beyond RKE2 defaults
- **No image scanning** — images built locally, no Snyk/Trivy in pipeline
- **Secrets**: Plain K8s secrets (base64 encoded, not encrypted at rest unless etcd encryption enabled)
- **PII**: Fernet encryption for SSNs (when `PII_FERNET_KEY` set), masking fallback
- **Network**: NetworkPolicies restrict DB access to known namespaces
- **RBAC**: Default ServiceAccount per namespace, no custom roles
- **TLS**: Terminated at Cloudflare edge, plaintext inside cluster

---

## K. Wave/Build Cadence

### What a Wave Contains

| Metric | Typical | Range |
|--------|---------|-------|
| New tests | 15-20 | 8-48 |
| Files modified | 3-8 | 2-15 |
| New decisions | 2-4 | 1-6 |
| Duration (dev time) | 30-90 min | 15 min - 4 hrs |

### 9-Step Delivery Pattern

1. Implement code changes
2. Write tests
3. Run full test suite (zero regressions)
4. Version bump (4 places in main.py + test file)
5. `podman build --no-cache` → save → `cat|ssh` import to node
6. `kubectl rollout restart` → verify health
7. Update DECISIONS.md + NEXT-STEPS.md
8. Git commit → tag → push → `gh release create`
9. Update project memory + MEMORY.md

### Dependency Graph (Waves 54-83)

```
Waves 54+55+58 — parallel (OAuth, Redis, Landing)
  └─→ Wave 57 (PostgREST cache depends on Redis)
  └─→ Wave 70 (Scaling depends on Redis)
  └─→ Wave 72 (Stripe depends on Redis + Scaling)
  └─→ Wave 73 (Grafana depends on Redis + Stripe)

Waves 59-63 — all parallel (Forms/OCR)
Waves 64-68 — all parallel (Intelligence)
Wave 71 — independent (States)
Waves 74-83 — mostly independent (tax features)
```

### Rollback Pattern

No formal rollback. Recovery options:
1. `git revert` + rebuild + redeploy
2. `kubectl rollout undo deployment/{app}` (reverts to previous ReplicaSet)
3. Import previous image tar if available in `/tmp/`

---

# SECTION 2 — TEMPLATIZATION SPECIFICATION

## Choice: Helm Chart Library + Per-App Values

**Why Helm over Kustomize**: Every app on this cluster already uses Helm. The team knows Helm. Kustomize's overlay model adds cognitive overhead for single-developer operation. Helm's `values.yaml` + template conditionals map directly to the variation points.

**Approach**: A shared **library chart** (`istayintek-app`) that each app chart depends on, plus a per-app `values.yaml`.

## Minimum Variables for a New App

```yaml
# values.yaml — minimum viable app
app:
  name: myapp                    # Used in labels, service names, PV paths
  namespace: myapp               # K8s namespace
  domain: myapp.istayintek.com   # Cloudflare tunnel hostname

api:
  enabled: true
  image: localhost/myapp-api:latest
  port: 8000
  healthPath: /health
  resources:
    tier: medium                 # micro/small/medium/large/xl

db:
  enabled: true
  size: 5Gi
  node: mgplcb05

postgrest:
  enabled: true                  # false if app doesn't need REST-over-SQL

portal:
  enabled: false                 # opt-in

agent:
  enabled: false                 # opt-in

landing:
  enabled: false                 # opt-in (CF Workers, not K8s)

redis:
  enabled: false                 # opt-in
```

## Defaults (4-Component App Bootstrap)

A `values.yaml` with just `app.name`, `app.domain`, and `api.port` gets you:
- Namespace creation
- PostgreSQL 16 StatefulSet (5Gi, mgplcb05)
- PostgREST v12 Deployment
- Flyway migration Job (if `/app/db/flyway/migrations/` exists in image)
- API Deployment (1 replica, medium tier, startup/liveness/readiness probes)
- ClusterIP Services for API + PostgREST + PostgreSQL
- PV + PVC for PostgreSQL + documents
- NetworkPolicy allowing CF tunnel ingress
- Secrets template (`scripts/setup-secrets.sh` generated)

## Directory Layout

```
istayintek-platform/
├── charts/
│   └── istayintek-app/           # Library chart
│       ├── Chart.yaml
│       ├── values.yaml           # Defaults
│       └── templates/
│           ├── _helpers.tpl      # Shared labels, naming
│           ├── namespace.yaml
│           ├── api-deployment.yaml
│           ├── api-service.yaml
│           ├── portal-deployment.yaml    # {{- if .Values.portal.enabled }}
│           ├── portal-service.yaml
│           ├── agent-deployment.yaml     # {{- if .Values.agent.enabled }}
│           ├── agent-service.yaml
│           ├── frontend-deployment.yaml  # {{- if .Values.frontend.enabled }}
│           ├── frontend-service.yaml
│           ├── postgres-statefulset.yaml # {{- if .Values.db.enabled }}
│           ├── postgres-service.yaml
│           ├── postgrest-deployment.yaml # {{- if .Values.postgrest.enabled }}
│           ├── postgrest-service.yaml
│           ├── redis-statefulset.yaml    # {{- if .Values.redis.enabled }}
│           ├── redis-service.yaml
│           ├── flyway-job.yaml           # Helm hook
│           ├── pvs/
│           │   ├── db-pv.yaml
│           │   ├── docs-pv.yaml
│           │   └── agent-pv.yaml
│           ├── cronjobs/
│           │   ├── pg-backup.yaml
│           │   └── smoke-test.yaml
│           └── netpol/
│               ├── allow-cfd.yaml
│               └── db-internal.yaml
├── apps/
│   ├── taxlens/
│   │   ├── values.yaml           # TaxLens-specific overrides
│   │   └── Chart.yaml            # depends on istayintek-app
│   ├── {new-app}/
│   │   ├── values.yaml
│   │   └── Chart.yaml
│   └── ...
├── scripts/
│   ├── new-app.sh                # "New app in 30 minutes" runbook
│   ├── setup-secrets.sh          # Templated for any app
│   ├── provision-node-dirs.sh    # SSH to node, create PV dirs
│   ├── build-and-deploy.sh       # Generic build → transfer → rollout
│   └── add-tunnel-route.sh       # Cloudflare API for new hostname
└── docs/
    ├── SUBSTRATE.md              # This document
    └── RUNBOOK.md                # Operations runbook
```

## "New App in 30 Minutes" Runbook

```bash
# 1. Create app directory (2 min)
mkdir -p istayintek-platform/apps/myapp
cat > apps/myapp/values.yaml << 'EOF'
app:
  name: myapp
  namespace: myapp
  domain: myapp.istayintek.com
api:
  image: localhost/myapp-api:latest
  port: 8000
db:
  enabled: true
  size: 5Gi
EOF

# 2. Provision node directories (2 min)
bash scripts/provision-node-dirs.sh myapp mgplcb05

# 3. Create secrets (2 min)
bash scripts/setup-secrets.sh myapp

# 4. Build app image (5-10 min)
cd /var/lib/rancher/ansible/db/myapp
podman build --no-cache --network=host -t localhost/myapp-api:latest .
bash scripts/build-and-deploy.sh myapp-api mgplcb05

# 5. Deploy with Helm (2 min)
helm upgrade --install myapp charts/istayintek-app \
  --namespace=myapp --create-namespace \
  -f apps/myapp/values.yaml

# 6. Add Cloudflare tunnel route (2 min)
bash scripts/add-tunnel-route.sh myapp.istayintek.com \
  myapp-api.myapp.svc.cluster.local:8000

# 7. Verify (2 min)
kubectl get pods -n myapp
curl -s https://myapp.istayintek.com/health
```

## Anti-Patterns to Forbid

1. **Manual CF tunnel edits** — Always use `add-tunnel-route.sh` or API, never click in dashboard
2. **Hardcoded service URLs** — Use `{app}-{component}.{namespace}.svc.cluster.local`, not IPs
3. **Secrets in values.yaml** — Always via `setup-secrets.sh` → K8s secret → `secretKeyRef`
4. **Images without nodeSelector** — Every deployment MUST pin to the node where image was imported
5. **PVs without claimRef** — Pre-bind to avoid orphan volume claims
6. **Skipping --no-cache** — After source changes, always `--no-cache` (podman layer cache gotcha)

## TaxLens Migration Plan

**Phase 1** (non-disruptive): Extract the library chart from existing TaxLens manifests. TaxLens continues using its current charts.

**Phase 2**: Create `apps/taxlens/values.yaml` that generates identical manifests to the current charts. Diff-test with `helm template`.

**Phase 3**: Switch TaxLens to the library chart during a maintenance window. Verify all services, run smoke tests.

**Risk**: Low. The template generates the same YAML. Only risk is a missed template conditional.

---

# SECTION 3 — THREE ADDITIONAL APPLICATIONS

## Priority 1: EstateMap — Estate Planning Intelligence Engine

**One-line**: Compute estate tax liability, trust structures, and generational wealth transfer strategies for high-net-worth individuals.

**Target user**: Estate planning attorneys, wealth advisors, CPAs with HNW clients.

**Why this and not something else**: Natural extension of TaxLens. HNW clients who use TaxLens for income tax need estate planning. The computation engine pattern (stateless, input/output, PDF generation) is identical. Estate tax has its own IRC sections (§2001-§2801) with completely different brackets, exemptions, and trust structures — exercising the template with a different domain model, not just another CRUD app.

**Synergy with TaxLens**: Cross-references TaxLens income data for gifting strategy optimization (e.g., "gift appreciated assets to beneficiaries in lower income brackets"). MCP tool integration lets Claude agents use both engines in a single conversation.

### Component Breakdown

| Component | Applies? | Notes |
|-----------|----------|-------|
| API | Yes | FastAPI, same pattern as TaxLens |
| Portal | Yes | Client management for estate attorneys |
| Landing | Yes | CF Workers marketing page |
| Agent | No (reuse TaxLens agent) | Same Claude agent, additional MCP tools |
| PostgreSQL | Yes (own database) | Trust structures, beneficiary records |
| PostgREST | Yes | Same pattern |
| Redis | No | Not needed at initial scale |

### URLs

- `estatemap.istayintek.com` (landing)
- `estatemap-api.istayintek.com` (API)
- `estatemap-portal.istayintek.com` (portal)

### Database

Own database `estatemap` in shared or new PG StatefulSet. Tables: trusts, beneficiaries, assets, gift_history, estate_computations.

### MCP Tools Provided

- `compute_estate_tax` — Federal estate tax on gross estate
- `compare_trust_structures` — Revocable vs irrevocable vs GRAT vs ILIT
- `optimize_gifting_strategy` — Annual exclusion ($18K/2025) + lifetime exemption ($13.61M)
- `project_estate_growth` — Multi-decade estate projection with mortality tables

### Estimates

- First deploy: 8-10 waves
- v1.0: 20 waves
- Key risk: Estate tax code is smaller but trust modeling is complex (GRAT annuity calculations, generation-skipping tax)

---

## Priority 2: ComplianceRadar — Regulatory Filing Deadline Tracker + Document Vault

**One-line**: Track every federal, state, and local filing deadline for a business entity portfolio, with document storage and automated reminders.

**Target user**: CPA firms managing 50-500 business clients across multiple states.

**Why this and not something else**: The #1 malpractice claim against CPAs is missed filing deadlines. TaxLens computes taxes but doesn't track the operational calendar. This is a different shape — it's a CRUD + calendar + notification app, not a computation engine. Stress-tests the template's webhook/email integration and scheduled job capabilities rather than the compute pattern.

**Synergy with TaxLens**: Ingests TaxLens draft data to auto-populate filing calendar. When TaxLens computes a multi-state return, ComplianceRadar auto-creates deadline entries for each state.

### Component Breakdown

| Component | Applies? | Notes |
|-----------|----------|-------|
| API | Yes | FastAPI, calendar + entity CRUD |
| Portal | Yes | Calendar dashboard, document upload |
| Landing | No | Sell through TaxLens landing |
| Agent | No | Not needed initially |
| PostgreSQL | Yes (own database) | Entities, deadlines, documents, notifications |
| PostgREST | Yes | |
| Redis | Yes | Job queue for email reminders |
| **NEW: Email worker** | Yes | CronJob-based reminder dispatch |

### URLs

- `radar.istayintek.com` (portal — no separate landing)
- `radar-api.istayintek.com` (API)

### Database

Own database. Tables: entities, filing_deadlines, deadline_rules (template), documents, notifications, notification_log.

### Template Gaps Exposed

- **Email worker CronJob**: New component type not in TaxLens template. Need a `worker` component alongside `api`.
- **Calendar iCal export**: Static file serving from API, not currently templated.

### Estimates

- First deploy: 5-6 waves
- v1.0: 12 waves
- Key risk: Deadline rule database is large (50 states × 10+ filing types × quarterly/annual). Must be curated, not computed.

---

## Priority 3: BenchmarkIQ — Small Business Financial Benchmarking via IRS SOI Data

**One-line**: Compare a small business's financial metrics against IRS Statistics of Income (SOI) industry averages to identify outlier ratios that trigger audits or reveal inefficiencies.

**Target user**: Small business owners and their accountants who want to know "am I normal?"

**Why this and not something else**: TaxLens already has an audit risk module that compares against IRS statistical norms. BenchmarkIQ takes this further — it's a standalone analytics product that ingests Schedule C/K-1 data and returns industry-specific benchmarks. Different shape: read-heavy analytics with no state mutation (no drafts, no PDFs). Tests the template with a stateless, cacheable, read-optimized workload.

**Synergy with TaxLens**: Direct data feed — TaxLens `compute_tax` results include Schedule C profit, expense categories, and industry codes. BenchmarkIQ consumes these to auto-generate benchmark reports. The audit risk module in TaxLens could delegate to BenchmarkIQ for deeper analysis.

### Component Breakdown

| Component | Applies? | Notes |
|-----------|----------|-------|
| API | Yes | FastAPI, benchmark computation |
| Portal | No | Embed in TaxLens portal |
| Landing | No | Feature page on TaxLens landing |
| Agent | No | MCP tool in TaxLens agent |
| PostgreSQL | Yes | SOI data tables (IRS publishes annually) |
| PostgREST | Yes | Read-heavy, cacheable |
| Redis | Yes | Cache layer for SOI lookups |
| **NEW: Data loader** | Yes | Annual SOI data import Job |

### URLs

- `benchmark-api.istayintek.com` (API only — no UI, consumed by TaxLens)

### Database

Own database. Tables: soi_industry_stats, naics_codes, benchmark_rules, percentile_tables. Loaded annually from IRS SOI CSV publications.

### MCP Tools Provided

- `benchmark_business` — Compare Schedule C metrics against industry averages
- `get_industry_norms` — Raw SOI data for a NAICS code
- `identify_outliers` — Flag metrics that deviate >2σ from industry mean

### Template Gaps Exposed

- **Data loader Job**: One-time bulk import (not migration, not CronJob). New component type.
- **Cross-app MCP**: BenchmarkIQ provides MCP tools consumed by TaxLens agent. Need service-to-service auth.

### Estimates

- First deploy: 4-5 waves
- v1.0: 10 waves
- Key risk: SOI data quality. IRS publishes aggregated stats, not raw data. Industry categories are broad (NAICS 2-digit), limiting granularity.

---

# SECTION 4 — CROSS-CUTTING CONCERNS

## Cross-App Authentication

**Current state**: Each app has independent API key auth. No SSO.

**Recommendation**: Shared JWT issuer via TaxLens OAuth endpoint (`POST /token`).
- TaxLens already issues JWTs with tenant_id and scopes
- New apps accept the same JWT, validate against shared `DB_JWT_SECRET`
- Session cookie domain: `.istayintek.com` (covers all subdomains)
- Portal SSO: Single login at `portal.istayintek.com`, JWT valid across all portals
- **Don't add Keycloak.** The cluster can't afford the memory. The existing OAuth endpoint handles client_credentials + PKCE.

## Cross-App Authorization

**Per-app scopes on shared JWT**:
- Scopes: `taxlens:compute`, `taxlens:drafts`, `estatemap:compute`, `radar:read`, `benchmark:read`
- JWT payload: `{"tenant_id": "t-xxx", "scopes": ["taxlens:compute", "radar:read"]}`
- Each app validates only its own scopes
- Admin scope: `admin:{app}` for management endpoints

## Cross-App Data Sharing

**Pattern**: Service-to-service via internal K8s DNS + shared JWT.

```
TaxLens Agent → taxlens-api.taxlens.svc:8000/api/tax-draft (JWT)
TaxLens Agent → benchmark-api.benchmark.svc:8000/api/benchmark (same JWT)
ComplianceRadar → taxlens-api.taxlens.svc:8000/api/tax-draft (service account JWT)
```

NetworkPolicy must allow cross-namespace traffic for participating apps.

## Shared Component Versioning

**No shared libraries.** Each app is fully self-contained. Common patterns are copy-paste from the template, not imported packages.

If a shared auth library emerges:
- Publish to private PyPI (or vendor as git submodule)
- Pin exact versions in each app's `requirements.txt`
- Breaking changes require coordinated deploy

## Tenant Isolation

**Current**: Single-tenant per deployment (API key → tenant_id via PostgREST RLS).

**Multi-tenant already works** for TaxLens (Wave 11b):
- API key hashed → tenant_id
- PostgREST RLS enforces row-level isolation
- Quota enforcement per tenant (feature_gate middleware)
- New apps inherit the same pattern via the library chart's PostgREST + migration templates

## Per-App Cost Attribution

Not implemented. Options:
- **Namespace labels**: `cost-center: taxlens` on namespace → OpenCost picks it up
- **Not urgent**: 2-node cluster, single operator. Cost attribution matters at 10+ apps.

## Disaster Recovery

### Full Cluster Rebuild

1. Provision 2 nodes via Ansible playbooks (`/var/lib/rancher/ansible/playbooks/`)
2. Install RKE2 (phase-2, phase-3 playbooks)
3. Apply StorageClass
4. For each app: `provision-node-dirs.sh` → `setup-secrets.sh` → `helm install` → import images
5. Restore PostgreSQL from latest backup: `gunzip -c backup.sql.gz | psql`
6. Reconfigure Cloudflare tunnel routes

### RTO/RPO

| Tier | RTO | RPO | Apps |
|------|-----|-----|------|
| Critical | 2 hours | 24 hours | TaxLens API |
| Standard | 4 hours | 24 hours | Portal, Agent, new apps |
| Best-effort | 8 hours | 7 days | Landing pages, Gastown |

**Gap**: No off-site backup. PG backups are on the same node as the data.

## Documentation

- **Substrate doc**: This file (`PLATFORM-SUBSTRATE.md`) in the TaxLens repo
- **Per-app docs**: `DEPLOYMENT.md` + `DECISIONS.md` + `NEXT-STEPS.md` in each app repo
- **Memory system**: `/home/hr1/.claude/projects/-var-lib-rancher-ansible/memory/` auto-loads in Claude Code sessions
- **Kept in sync**: DECISIONS.md updated every wave. Memory updated every session. Drift is low because a single developer + Claude Code operates the entire cluster.

---

## Prioritized Backlog — Top 10

| # | Item | Unblocking Power | Effort | Priority |
|---|------|-----------------|--------|----------|
| 1 | **Extract library Helm chart from TaxLens manifests** — Create `istayintek-app` chart with conditional components. Diff-test against current TaxLens output. | Unblocks all 3 new apps | 4-6 hours | **P0** |
| 2 | **Create `scripts/new-app.sh` runbook script** — Automates the 7-step "new app in 30 minutes" flow (mkdir, provision dirs, secrets, tunnel route). | Eliminates manual steps for every new app | 2 hours | **P0** |
| 3 | **Off-site PG backup** — rsync daily backup tar to mgplcb03 (or S3 bucket). Currently all backups die with mgplcb05. | Prevents total data loss | 1 hour | **P1** |
| 4 | **Shared JWT validation middleware** — Extract TaxLens auth.py into a standalone module that any app can import. Add cross-app scope validation. | Enables cross-app API calls | 3 hours | **P1** |
| 5 | **Bootstrap EstateMap API** — First real consumer of the library chart. Minimal: `/health`, `/compute-estate-tax`, 3 test scenarios. | Validates template end-to-end | 6-8 hours | **P1** |
| 6 | **Add Playwright contract test for PostgREST schema endpoint** — Verify schema reload after migration, test RLS isolation. Run as CronJob. | Catches migration regressions before they reach API | 4 hours | **P2** |
| 7 | **Cross-namespace NetworkPolicy template** — Allow service-to-service calls between app namespaces (e.g., radar → taxlens API). Currently blocked by default-deny. | Required for ComplianceRadar ↔ TaxLens integration | 2 hours | **P2** |
| 8 | **Canary deployment support in library chart** — Optional 2nd Deployment at 10% traffic (via weighted Service or Istio VirtualService). | Reduces blast radius of bad deploys | 6 hours | **P2** |
| 9 | **Automated image import to both nodes** — `build-and-deploy.sh` should cat-pipe to both mgplcb03 and mgplcb05, eliminating nodeSelector as a hard requirement. | Removes scheduling constraints, enables HA | 2 hours | **P3** |
| 10 | **Add Trivy image scan to build script** — `trivy image localhost/{app}:latest` before save+transfer. Fail on CRITICAL CVEs. | Security gate with zero infrastructure cost | 1 hour | **P3** |
