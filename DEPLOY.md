# Deploying ShipMate to Zerops

ShipMate is five services in one Zerops project: `web`, `api`, `worker`, `db`,
`cache`. This walks through getting them live.

> Prereqs: a Zerops account (free `$15` credit is plenty) and the `zcli`
> command-line tool. Install: `npm i -g @zerops/zcli` (or see the Zerops docs).

## 1. Log in

```bash
zcli login <your-personal-access-token>   # from the Zerops GUI → Settings → Access tokens
```

## 2. Create the project + all services in one shot

The import file at the repo root declares every service:

```bash
zcli project project-import zerops-project-import.yml
```

This creates the `shipmate` project with `web` (static), `api` (python@3.12),
`worker` (python@3.12), `db` (postgresql@16) and `cache` (valkey@7.2), wired on a
private network.

## 3. Add secrets (Azure AI Foundry — for prompt mode)

In the Zerops GUI, open the **api** and **worker** services → **Environment
variables** → add these as *secret* env vars (never commit them):

| Variable | Value |
|----------|-------|
| `AZURE_OPENAI_ENDPOINT` | `https://<your-resource>.openai.azure.com` |
| `AZURE_OPENAI_API_KEY` | your key |
| `AZURE_OPENAI_DEPLOYMENT` | your GPT deployment name (e.g. `gpt-4o-mini`) |
| `AZURE_OPENAI_API_VERSION` | `2024-06-01` (optional) |

`db` and `cache` connection details are injected automatically on the private
network; the service `zerops.yaml` files already reference the `db` / `cache`
hostnames.

> ShipMate runs fine **without** these — compose and repo modes work, and
> history falls back to in-memory. Add them only to unlock prompt mode.

## 4. Deploy each runtime service

Each service deploys using its own `zerops.yaml`. From the repo root:

```bash
# find the service IDs once, from the GUI or:
zcli service list

zcli push --serviceId <web-id>      --workingDir web
zcli push --serviceId <api-id>      --workingDir api
zcli push --serviceId <worker-id>   --workingDir worker
```

(Or `cd` into each directory and run `zcli push --serviceId <id>`.)

## 5. Wire the frontend to the API

The `web` build reads `VITE_API_BASE` at build time. Set it (GUI → web service →
env, build-time) to the public URL of the `api` service, then re-push `web`.

## 6. Verify

- Open the `web` service's subdomain URL — the app should load.
- `GET https://<api-subdomain>/api/health` → `{"status":"ok", ...}`.
- Generate a config from the UI and confirm the diagram + YAML render.

## ⚠ The subdomain-before-deploy 502 gotcha (we hit this)

The Zerops L7 route for a subdomain is generated from the service's **declared
HTTP port at the moment subdomain access is activated**. Our import file
intentionally declares no ports (they come from each `zerops.yaml` at deploy) —
so if you enable the subdomain in the GUI **before the first successful
deploy**, the route binds to a default port, nothing listens there, and you get
a **502 Bad Gateway** with *zero* requests reaching your app.

Telltale sign: the subdomain URL has **no port suffix** (e.g.
`api-xxxx.prg1.zerops.app` instead of `api-xxxx-8000.prg1.zerops.app`).

**Fix:** GUI → service → Public access: disable the Zerops subdomain →
confirm the current deploy is active (runtime log shows your server on its
port) → re-enable the subdomain. If it doesn't regenerate, toggle off →
`zcli push` once more → toggle on.

**Rule of thumb: deploy first, enable the subdomain second.**

## Troubleshooting

- **Build fails on `api`/`worker`** — check the build log; the base is
  `python@3.12` and it runs `pip install -r requirements.txt`.
- **`web` shows a blank page** — confirm `VITE_API_BASE` was set *before* the
  build and points at the reachable `api` URL.
- **Prompt mode returns an error** — the Azure secrets are missing or the
  deployment name is wrong; `GET /api/health` shows `"llm_ready": false`.
- **CORS** — `api` allows all origins by default (`app/main.py`); tighten to the
  `web` origin for production.

## Keep it live through judging

The challenge requires the deployment to stay reachable until judging completes.
Deploy early, keep dependencies minimal, and leave the services running.
