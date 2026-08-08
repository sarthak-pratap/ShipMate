# ShipMate — Complete Feature Reference

Every feature of the product, end to end: what it does, how to use it, how it
behaves without configuration, and its limits. For the design rationale see
[`ARCHITECTURE.md`](ARCHITECTURE.md); for hosting see [`DEPLOY.md`](DEPLOY.md).

---

## 1. Input modes

ShipMate turns **three kinds of input** into the same output bundle
(zerops.yaml + project-import + diagram + lint + score). Switch modes with the
tabs at the top of the input rail.

### 1.1 🐳 docker-compose mode

Paste any `docker-compose.yml`. Fully deterministic — no AI involved.

What it understands:

| Compose concept | Becomes |
|---|---|
| `services:` entries | Zerops services |
| `image: postgres:16`, `redis:7`, … | managed services (verified types: `postgresql@16`, `valkey@7.2`, `keydb@6`, `mariadb@10.4`, `nats@2.10`, `kafka@3.9`, `elasticsearch@8.16`, `meilisearch@1.20`, `typesense@27.1`, `qdrant@1.12`, `clickhouse@25.3`, `object-storage`) |
| `image: mongo` / `rabbitmq` | **substituted** (Postgres / NATS) with an explicit warning — Zerops has no managed MongoDB or RabbitMQ |
| `image: node:22`, `python:3.11`, … | runtime services with the right base |
| `build: ./dir` (+ optional `dockerfile:`) | the service's **Dockerfile is read** and its `FROM/EXPOSE/CMD/ENV` refine the base, port, start command and env (multi-stage aliases resolved; `mcr`/`ghcr` registry images matched by keyword) |
| `ports: "8000:8000"` | `run.ports` with `httpSupport` (true unless it's a known DB/broker port) |
| `depends_on` / `links` | private-network edges in the diagram |
| `environment` | `run.envVariables`; `localhost` values are flagged |
| `deploy.replicas > 1` | `mode: HA` on HA-capable managed services |
| service names (`web`, `worker`, `cron`…) | role inference: frontend / api / worker |

Special case — **infra-only compose**: if the file declares *only* managed
services (a local-dev `db` + `cache` pattern), compose mode faithfully outputs
just those and explains why the zerops.yaml has no build/run blocks. Repo mode
handles the merge with your real app (see 1.2).

### 1.2 🐙 Repo URL mode

Paste a **public GitHub repo URL**. ShipMate fetches the file tree + manifests
via the GitHub API (no clone) and infers the topology. Detection priority,
most authoritative first:

1. **Root docker-compose** (`docker-compose.yml`/`.yaml`, `compose.yml`/`.yaml`)
   — if it has runtime services, it's the source of truth (with per-service
   Dockerfile refinement). If it's **infra-only**, its managed services are
   remembered and **merged** with the app detected from the code.
2. **Monorepo** — runtime manifests in two or more top-level dirs
   (`backend/`, `frontend/`, `worker/`…) → one service per dir.
   Hostname aliases: `backend`/`server` → `api`, `frontend`/`client` → `web`.
   Frontends are auto-wired to APIs.
3. **Dockerfile** — `FROM` → base (multi-stage alias chains resolved),
   `EXPOSE` → port, `CMD`/`ENTRYPOINT` → start, `ENV` → env vars.
4. **Language markers** — `package.json`, `requirements.txt`, `pyproject.toml`,
   `go.mod`, `composer.json`, `Gemfile`, `pom.xml`, `Cargo.toml`.
5. **Dependency scan** — DB/cache/storage client libraries in manifests add
   managed services (e.g. `sqlalchemy`/`prisma` → Postgres, `redis`/`celery` →
   Valkey, `boto3`/`minio` → object storage) and wire the env vars.

Also:
- **Secrets awareness** — keys in `.env.example` that look secret
  (`*_KEY`, `*_SECRET`, `TOKEN`, `PASSWORD`, `ENDPOINT`…) are surfaced as a
  note telling you to set them as `envSecrets` in the Zerops GUI. Values are
  never baked into YAML.
- **Vite/CRA detection** — a package.json with `vite` and no server framework
  is classified as a static frontend.
- One-click **example chips**: `dockersamples/example-voting-app` (6 services,
  3 languages), `miguelgrinberg/microblog`, `fastapi/full-stack-fastapi-template`.

Limits: public repos only (private → clear error); manifests capped at 20
fetches; the default branch is used.

### 1.3 💬 Prompt mode

Describe the app in plain English.

- **With Azure OpenAI configured** (`AZURE_OPENAI_*` env vars): the LLM
  proposes a structured service list — the YAML itself is still written by the
  deterministic generator, so the output is always schema-correct.
- **Without keys (zero-config)**: a deterministic **offline parser** takes
  over. It reads *intent*, not just tech names:
  - tech keywords → services (`postgres`, `redis`, `kafka`, `elasticsearch`…)
  - product intent → persistence (`to-do`, `notes`, `booking`, `wiki`, `blog`,
    `shortener`… → Postgres)
  - collaboration (`collaborate`, `shared`, `team`, `together`) → cache for
    presence/sync + implied persistence
  - background work (`nightly`, `cron`, `reminder`, `digest`, `pipeline`) →
    worker wired to the datastores
  - realtime (`websocket`, `chat`, `multiplayer`) → cache + a note
  - uploads/media → object storage; full-text → search; queues → broker
  - `node/express/typescript` → nodejs stack, otherwise python
- **If a live LLM call fails**, it falls back to the offline parser — prompt
  mode never returns a 500.

Every inference adds a human-readable note (see §4).

---

## 2. Optional AI gap-fill (repo & compose modes)

The **“✨ use AI to fill gaps”** toggle runs a *second* pass after
deterministic detection (needs Azure keys):

- The detected topology + manifest excerpts go to the LLM, which may **only**:
  - **fill** an *empty* `start`, port, or base on an existing service
  - **add** a genuinely missing managed service or worker
- It can **never rename, retype, or overwrite** anything the deterministic
  pass produced — the merge is enforced in code and unit-tested.
- Every change is disclosed as a note (`AI: set start for 'app'`, …).
- Best-effort: if the call fails or keys are missing, you get a note and the
  deterministic result stands.

---

## 3. The output bundle

Every generation produces, in one shot:

### 3.1 `zerops.yaml` tab
Build/run config per **runtime** service, production-correct by construction:
- **Frontends** (vite/CRA): built with node, served from Zerops' `static`
  runtime — `deployFiles: dist/~`, never `npm run dev`. (SSR frontends —
  next/nuxt — keep a node runtime.)
- **Python services**: dependencies install via `build.addToRunPrepare`
  (requirements.txt) + `run.prepareCommands` — the official Zerops pattern;
  a build-container `pip install` never reaches the runtime container.
- **Workers**: real background commands (`python worker.py`, `node worker.js`
  — picked from actual files), and **no ports**.
- **Monorepos**: build commands `cd` into the service dir (single literal
  shell block), `deployFiles: <dir>/~`, caches point into the dir.
  Pushing from the repo root just works.

### 3.2 `project-import` tab
The infrastructure declaration: every service (managed types with `mode:
HA|NON_HA`, runtimes, static frontends), `enableSubdomainAccess` on public
services. Managed-only topologies are fully described here.

### 3.3 lint tab + deploy-readiness score
A misconfig linter with fix hints. Rules:

| Rule | Severity | Catches |
|---|---|---|
| missing-start | error | runtime with no `run.start` — container never boots |
| missing-ports | error | public service with no ports |
| db-not-declared | error | env references a DB (`DB_HOST`, `DATABASE_URL`…) but none exists |
| http-support | warning | public port without `httpSupport: true` |
| localhost-ref | warning | env pointing at `localhost`/`127.0.0.1` instead of a private hostname |
| no-subdomain | warning | service exposes ports but isn't publicly reachable |
| hardcoded-secret | warning | literal secret values in env (should be `envSecrets` / `${VAR}`) |
| deployfiles-output | info | build step present but `deployFiles: ./` ships everything |
| db-non-ha | info | single-container database in what looks like production |

The findings roll into a **0–10 score** shown as a headline badge:
10 = start; −3 per error, −1 per warning, −0.25 per info.
Grades: **`ship it`** (green) / **`deploys, review`** (yellow) /
**`won't deploy`** (pink).

### 3.4 The interactive topology canvas
- Auto-layout in role bands (public → frontend → api/worker → managed), with
  wide bands **wrapping** (4 per row) so 8+ service graphs stay legible
- **Drag nodes** to rearrange · **drag the background to pan** ·
  **scroll to zoom** (cursor-anchored) · **⤢ reset** restores the layout
- **⛶ expand** pops the canvas into a fullscreen overlay (Esc / ✕ / backdrop
  click to close); all interactions work there too
- Public traffic edges are dashed; private-network edges solid; nodes are
  color-coded by role

### 3.5 Notes — “how this was inferred”
Every non-obvious decision is explained in the notes panel: monorepo
detection, Dockerfile refinements, substituted services, intent inferences,
AI-enhance changes, secrets found, and mode-specific guidance. Nothing is
silent.

---

## 4. Deploy wizard

**▲ deploy to zerops** opens a wizard that asks only the questions that change
the command:

1. **Project name** — rewrites the import document
2. **New vs existing project** — `zcli project project-import` vs
   `zcli project service-import`
3. **Which runtime services to build & push** — checkboxes; managed services
   are never pushed (they exist from the import)
4. **Database resilience** — `NON_HA` vs `HA` (shown only when a DB exists)

The answers go to the API, which **rebuilds the import YAML and emits an exact
shell script** — files written via heredocs, the right import command, one
`zcli push <hostname>` per selected service, and any secrets warnings carried
along as comments. Pure logic, no LLM, unit-tested. Copy → run from your
app repo's root.

---

## 5. Shareable results

Every generation is **persisted** (id, project, full output bundle):
- **🔗 share** copies a `/?g=<id>` link — anyone opening it sees the exact
  result (diagram, YAML, lint, score) without regenerating
- Backed by **PostgreSQL** on Zerops (`GET /api/generation/{id}`); falls back
  to in-memory storage when no DB is configured (links then live until restart)

---

## 6. HTTP API

The frontend is a thin client over a real API — usable directly:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | liveness + `linter_rules` count + `llm_ready` flag |
| `POST /api/generate` | `{mode: "compose"\|"repo"\|"prompt", compose?, repo_url?, prompt?, ai_enhance?}` → full output bundle |
| `GET /api/generation/{id}` | fetch a saved generation (share links) |
| `POST /api/deploy-script` | `{id, project_name?, target?, push?, ha_db?}` → deterministic deploy script |
| `GET /api/history` | recent generations |

Example:
```bash
curl -s -X POST localhost:8000/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"mode":"repo","repo_url":"https://github.com/dockersamples/example-voting-app"}'
```

---

## 7. CLI

No server needed — the core runs from a terminal:
```bash
cd api
python shipmate_cli.py compose ../examples/taskboard-compose.yml
python shipmate_cli.py prompt "a notes app with postgres and a nightly digest worker"
```
Prints the zerops.yaml, the project-import file, and the lint findings.

---

## 8. Configuration & graceful degradation

ShipMate is **zero-config by default** — every feature has an offline path:

| Env vars | Unlocks | Without them |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT/_API_KEY/_DEPLOYMENT` | LLM prompt mode, AI gap-fill | offline intent parser; gap-fill shows a hint |
| `DB_HOST/_PORT/_NAME/_USER/_PASS` | persistent share links & history (Postgres) | in-memory storage |
| `CACHE_HOST/_PORT` | Valkey caching / worker queue | skipped |
| `GITHUB_TOKEN` | higher GitHub API rate limits (repo mode) | anonymous limits |
| `VITE_API_BASE` (web, build-time) | frontend → api URL in production | dev proxy to `localhost:8000` |

Nothing hard-fails when a dependency is absent — the note panel says what ran
in fallback mode.

---

## 9. Known limits (honest edges)

- Repo mode: public GitHub only; other forges (GitLab/Bitbucket) not yet.
- Compose `profiles:` are not evaluated (services behind profiles are read as
  regular services or skipped by their images).
- The Dockerfile parser reads the *final stage*; exotic build args in `FROM`
  (`FROM ${BASE}`) fall back to language markers.
- `compose` mode renders exactly the file you paste — if your compose is
  local-dev infra only, use repo mode for the full app picture.
- Generated configs are a **strong starting point** validated against the
  Zerops docs and real deploys — always review the notes before shipping.
