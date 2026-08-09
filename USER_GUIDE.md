# ShipMate — User Guide

Everything you need to go from an app to a live Zerops deployment. No install
required — just open the live app.

> **Live app:** https://web-2b15.prg1.zerops.app
> **How-it-works page:** https://web-2b15.prg1.zerops.app/guide.html

---

## What ShipMate does

You give it an app; it gives you a **validated Zerops deployment config**, an
**architecture map**, a **deploy-readiness score**, and a **one-command deploy
script**. It removes the hand-written-YAML step between "my code works" and
"it's live."

---

## Step 1 — Choose how you describe your app

ShipMate has three input modes (tabs at the top-left):

### 🐳 docker-compose
Paste a `docker-compose.yml`. Best when you already have one. Fully
deterministic — every service, image, port and `depends_on` maps straight to
Zerops. Try the built-in sample to see it instantly.

### 🐙 repo URL
Paste a **public GitHub repo** URL (or click an example chip — *voting app*,
*microblog*, *fastapi template*). ShipMate reads the repo's files and
manifests, detects the stack — including **monorepos** (one service per
top-level folder) and **Dockerfiles** — and builds the topology. No clone, no
setup.

### 💬 prompt
Describe the app in plain English: *"a booking app with Postgres and a nightly
reminder worker."* With an Azure OpenAI key configured it uses the LLM;
without one it falls back to a built-in keyword parser — so it always works.

Optional: tick **✨ use AI to fill gaps** (repo/compose modes) to let the LLM
add anything the static analysis missed — it only fills blanks, never
overwrites a correct detection.

## Step 2 — Generate

Hit **Generate →**. You immediately get:

- **Topology diagram** — drag nodes, scroll to zoom, drag the background to
  pan, and **⛶ expand** to fullscreen. Public traffic edges are dashed;
  private-network edges are solid.
- **Deploy-readiness score** — a 0–10 badge: `ship it` / `deploys, review` /
  `won't deploy`.
- **`zerops.yaml`** tab — the per-service build/run config.
- **`project-import`** tab — declares every service (runtimes + managed
  databases/caches).
- **Notes** — plain-English explanations of every inference ("monorepo
  detected", "dropped 16 env vars with unresolvable interpolation", etc.).

## Step 3 — Review the lint tab

The **lint** tab lists misconfigurations, each with a one-line fix — missing
start commands, `localhost` references, undeclared databases, self-referencing
env vars, and more. Aim for a green **`ship it`** score before deploying.

## Step 4 — Deploy

Click **▲ deploy to zerops**. The wizard asks the few questions that change the
command:

1. **Project name**
2. **New project** or **add to an existing one**
3. **Which runtime services** to build & push
4. **Database resilience** — NON_HA (cheaper) or HA (survives node failure)

Then **⬇ download `deploy.sh`** and, from your app's repo root:

```bash
bash deploy.sh
```

> Don't paste the script line-by-line — the heredocs and `zcli` prompts break
> on partial pastes. Download and run it.

The script writes `zerops.yaml` + `zerops-project-import.yml`, creates the
project, and pushes each service. Prereqs: [`zcli`](https://docs.zerops.io) installed and `zcli login <token>` done.

## Step 5 — Finish in the Zerops GUI

- **Secrets:** anything ShipMate flagged (API keys, DB passwords) is
  intentionally left out of the YAML — add them as env vars/secrets on the
  service in the Zerops GUI.
- **Public URL:** enable the service's Zerops subdomain **after** the first
  successful deploy (see the gotcha in [`DEPLOY.md`](DEPLOY.md)).
- **Frontend → API:** set `VITE_API_BASE` (build-time) to the API's public URL,
  then re-push the web service.

## Share & revisit

Every generation gets a **🔗 share** link (`/?g=<id>`) — send it to a teammate
or reopen it later; it restores the exact diagram, YAML, lint and score.

---

## Feature list

| Feature | What it gives you |
|---|---|
| 3 input modes | docker-compose · GitHub repo · plain-English prompt |
| Monorepo detection | one service per top-level dir, correct build contexts |
| Dockerfile parsing | base/port/start from `FROM`/`EXPOSE`/`CMD`, multi-stage aware |
| Verified service types | only types Zerops actually offers; unsupported ones substituted + flagged |
| Production-correct output | static frontends, official Python dep pattern, real worker commands |
| Interactive diagram | drag · zoom · pan · fullscreen |
| Misconfig linter + score | mistakes caught early, each with a fix, rolled into 0–10 |
| AI gap-fill (optional) | LLM fills only blanks; never overwrites |
| Deploy wizard | question-driven, deterministic `deploy.sh` |
| Shareable links | reopen any generation by URL |

## FAQ

**Do I need to install anything to try it?** No — the live app runs in your
browser. You only need `zcli` when you actually deploy.

**Does it need an API key?** No. Prompt mode and AI gap-fill use one if
present, but everything has an offline fallback.

**Private repos?** Not yet — public GitHub repos only.

**Is the generated config guaranteed perfect?** It's a strong,
review-then-ship starting point, validated against the Zerops docs and real
deploys. Always read the notes and the lint tab before shipping.

**Something broke on deploy.** See [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) —
it covers the real errors (502s, secrets, monorepo build contexts, DNS) with
fixes, and how to use ZCP to debug.
