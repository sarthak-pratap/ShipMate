# ShipMate 🛰️

**Describe an app → get a validated `zerops.yaml` + a live architecture map.**

A zerops.yaml Copilot and architecture visualizer. Give it a plain-English
description, a GitHub repo, or a `docker-compose.yml`, and it:

1. **Generates** a schema-correct `zerops.yaml` + project-import file
2. **Visualizes** the resulting service topology over Zerops' private network
3. **Lints** the config for the mistakes that make first deploys fail

Built for **The Zerops Challenge** (Aug 8–9, 2026). ShipMate itself runs on the
full Zerops stack — frontend + API + worker + Postgres + Valkey — so its own
deployment is live proof that the configs it writes actually work.

---

## Docs

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — design: the one-IR idea, the three input modes, how it runs on Zerops (read this to understand the code)
- [`DEPLOY.md`](DEPLOY.md) — step-by-step Zerops deployment with `zcli`
- [`AI_DISCLOSURE.md`](AI_DISCLOSURE.md) — AI-usage disclosure (challenge rules)

## Repo layout

```
shipmate/
├── zerops-project-import.yml   # ShipMate's own 5-service Zerops topology
├── docker-compose.yml          # LOCAL dev: postgres + valkey
├── .env.example                # local + Azure OpenAI config
├── Makefile                    # make infra / api / worker / web / test / cli
├── examples/                   # sample inputs
├── api/                        # FastAPI — the generator, linter, detector, LLM
│   ├── app/core/               # ⭐ the core logic (hand-written, unit-tested)
│   │   ├── schema.py               #   the Topology intermediate representation
│   │   ├── compose_parser.py       #   Mode 3: docker-compose → Topology
│   │   ├── detector.py             #   Mode 2: repo files → Topology
│   │   ├── llm.py                  #   Mode 1: prompt → Topology (Azure OpenAI)
│   │   ├── zerops_generator.py     #   Topology → zerops.yaml + import + graph
│   │   ├── linter.py               #   the misconfig rules
│   │   └── mappings.py             #   image/runtime → Zerops type table
│   ├── shipmate_cli.py         # try the core with no server
│   ├── tests/                  # pytest (13 tests, all green)
│   └── zerops.yaml             # api service build/run config
├── worker/                     # background repo analysis + long LLM calls
│   └── zerops.yaml
└── web/                        # React + Vite frontend + SVG diagram
    └── zerops.yaml
```

## Can I build locally now and deploy to Zerops later?

**Yes — that's exactly how it's set up.** The app reads every connection detail
from environment variables, so "local" vs "Zerops" is only a difference in env
values. Nothing is hard-wired to Zerops.

### Run it locally (today)

```bash
# 0. optional: local Postgres + Valkey (app works without them too — in-memory fallback)
make infra                       # docker compose up -d
cp .env.example .env             # fill in Azure OpenAI keys for prompt mode

# 1. the fastest smoke test — no server needed
cd api && pip install -r requirements.txt
python shipmate_cli.py compose ../examples/taskboard-compose.yml

# 2. run the API + frontend
make api                         # FastAPI on http://localhost:8000
make web                         # Vite on   http://localhost:3000  (proxies /api)

# 3. run the tests
make test                        # 13 passing
```

Prompt mode (Mode 1) activates automatically once the `AZURE_OPENAI_*` vars are
set; without them the app still runs (compose + repo modes, in-memory history).

### Deploy to Zerops (at event time)

```bash
# 1. install the Zerops CLI and log in
zcli login <token>

# 2. create the project + all five services in one shot
zcli project project-import zerops-project-import.yml

# 3. add secrets (Azure OpenAI) to the api + worker services in the Zerops GUI,
#    then push each service — it deploys using its own zerops.yaml
zcli push --serviceId <api-id>      # from api/
zcli push --serviceId <worker-id>   # from worker/
zcli push --serviceId <web-id>      # from web/
```

That's it — you get a live URL for `web`, wired to `api`, `worker`, `db` and
`cache` over the private network.

## The three input modes

| Mode | Input | Path | LLM? |
|------|-------|------|------|
| 3 · compose | `docker-compose.yml` | `compose_parser.py` | no (deterministic, most reliable) |
| 2 · repo | GitHub URL | `worker.py` → `detector.py` | no |
| 1 · prompt | plain English | `llm.py` (Azure OpenAI) → deterministic generator | yes |

All three converge on one `Topology`, so the trustworthy part (schema-correct
YAML) always comes from our own code — the LLM only proposes a service list.

## Tech

React + Vite · Python / FastAPI · Azure AI Foundry (GPT) · PostgreSQL 16 ·
Valkey 7 · deployed on Zerops.

## AI-usage note (challenge rules)

The core logic — compose parser, detector, linter rules, generator — is
hand-written and unit-tested. AI assistance was used for boilerplate/UI and is
disclosed in the submission form. Every architectural decision here is
explainable.
