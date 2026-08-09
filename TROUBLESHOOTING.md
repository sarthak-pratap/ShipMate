# Deploying on Zerops — Errors You'll Hit & How to Debug Them

> A field guide written from a real deployment. Every error below is one we
> actually hit taking ShipMate from `zcli push` to a live URL — with the exact
> symptom, root cause, and fix. If you're deploying *any* app to Zerops (not
> just ShipMate), this will save you hours.

## TL;DR — ZCP is a debugging tool, not just a build tool

The single most useful thing we learned: the **Zerops Control Plane (ZCP)** —
the dev container that lives *inside your project's private network* — is a
first-class **debugger**. It's usually pitched as "prompt an agent, get a live
URL," but its real superpower is that it can see and query your running
services from the inside:

- `zerops_logs` — pull a service's runtime log and read the **actual Python
  traceback**, not the sanitized message the UI shows you
- `zerops_discover` — the live topology: each service's OS/base, status,
  autoscaling, and generated subdomains
- `zerops_events` — the deploy/build timeline (was my fix *actually* the
  active version, and when?)
- a real **terminal** on the private network — `getent hosts`, `curl`,
  `cat /etc/resolv.conf`, `pip show`, or a one-off Python repro, run from a
  container that shares the network with your app

Nearly every mystery below was solved not by guessing but by **asking ZCP a
precise question**. A two-day "Connection error" collapsed the instant we read
one log line through `zerops_logs`. Treat ZCP as `kubectl exec` + `journalctl`
for your project.

See [§ ZCP debugging cheat-sheet](#zcp-debugging-cheat-sheet) for the exact
commands.

---

## The gauntlet — 10 real errors, in the order we hit them

### 1. `502 Bad Gateway`, zero requests reaching the app
**Symptom:** app healthy in logs (Uvicorn on `0.0.0.0:8000`), but the public
URL returns 502 and the app logs show *no* incoming requests.
**Cause:** the subdomain's L7 route is generated from the service's declared
HTTP port **at the moment you enable subdomain access**. Enable it *before* the
first successful deploy and it binds to a default port nothing listens on.
**Telltale:** the URL has no port suffix (`api-xxxx.zerops.app` instead of
`api-xxxx-8000.zerops.app`).
**Fix:** deploy first, **then** enable the subdomain. If already wrong: disable
→ `zcli push` → re-enable.

### 2. Frontend `405` / posting to itself
**Symptom:** the SPA's API calls 405 or hit the static server.
**Cause:** `VITE_API_BASE: ${VITE_API_BASE}` in `web`'s `zerops.yaml` — a
**circular reference**. Zerops can't expand a var into itself, so it baked in
an empty string and the frontend called its own origin.
**Fix:** don't map a var to itself. Set `VITE_API_BASE` (build-time) in the GUI
to the api's public URL; remove the self-mapping from yaml. *(This is the same
bug as #9 — remember it.)*

### 3. GitHub `403 rate limit exceeded`
**Symptom:** repo-mode fetches fail after a handful of tries.
**Cause:** unauthenticated GitHub API calls from Zerops' shared egress IP hit
the 60 req/hr anonymous limit.
**Fix:** add a `GITHUB_TOKEN` env var → 5,000 req/hr.

### 4. `httpx.Client() got an unexpected keyword argument 'proxies'`
**Symptom:** the app crashes constructing the OpenAI client.
**Cause:** `openai==1.51.0` passes `proxies=` to `httpx`, removed in
`httpx>=0.28`. A fresh deploy pulled the newer httpx.
**Fix:** pin `httpx<0.28.0` in `requirements.txt`.

### 5. Azure OpenAI vs. Microsoft AI Foundry endpoint mismatch
**Symptom:** 404s / connection drops against the model endpoint.
**Cause:** a Foundry endpoint (`*.services.ai.azure.com`, with the details page
showing `/openai/v1/responses`) is **not** a classic `*.openai.azure.com`
resource. The `AzureOpenAI` client forced a `/openai/deployments/...` path the
endpoint rejected.
**Fix:** detect the host; for Foundry use the plain `OpenAI` client against
`https://<host>/openai/v1`; strip any trailing path/quotes from the endpoint.

### 6. `400 Unsupported value: 'temperature' does not support 0.1`
**Symptom:** the model returns 400 on every call.
**Cause:** reasoning models (e.g. `gpt-5.x` reasoning tiers) reject custom
sampler params like `temperature`.
**Fix:** omit `temperature` so it defaults; don't send sampler params to
reasoning models.

### 7. Red herring: `trust_env=False`
**Symptom:** chasing a suspected proxy tunnel, we set
`httpx.Client(trust_env=False)`.
**Cause:** there was no proxy. This change did nothing useful and muddied the
diagnosis. (The real issues were #5, #6, and #9.)
**Lesson:** don't add mitigations for unconfirmed causes — confirm first (ZCP).

### 8. `[Errno -5] Name has no usable address` (musl DNS)
**Symptom:** the app can reach GitHub but not the Azure endpoint; ZCP (a
different container) resolves both fine.
**Cause suspected:** the api ran on Alpine (**musl libc**), whose resolver
mishandles large/CNAME-chained DNS responses that glibc retries over TCP.
**Fix applied:** `os: ubuntu` (glibc) on build+run. *(Harmless and kept — but
it turned out the errno was a symptom of #9, not the true cause.)*

### 9. 🏆 THE root cause: a self-referencing secret
**Symptom:** persistent `Connection error` / `[Errno -2] Name or service not
known` on the Azure call, surviving every fix above.
**How we found it:** one line from `zerops_logs` —
```
=== LLM ENHANCE CALL === Endpoint: '${AZURE_OPENAI_ENDPOINT}'
```
The endpoint env var held the **literal string** `${AZURE_OPENAI_ENDPOINT}`.
**Cause:** `AZURE_OPENAI_ENDPOINT: ${AZURE_OPENAI_ENDPOINT}` in `zerops.yaml` —
a circular reference (identical to #2) that **overrode the GUI secret** with the
raw placeholder. The client then tried to DNS-resolve a "hostname" named
`${azure_openai_endpoint}`.
**Fix:** delete the mapping. GUI secrets inject into the runtime automatically —
never write `VAR: ${VAR}` in `envVariables`.
**Lesson:** the UI's generic "Connection error" hid a config bug; the **runtime
log named it in one line**. Log-first debugging beats theory.

### 10. Monorepo build context + build-vs-runtime deps
Two more that bit during the same run (details in
[`ARCHITECTURE.md`](ARCHITECTURE.md)):
- **`requirements.txt not found`** — pushing a monorepo from the repo root runs
  build commands in `/build/source`; a service in `api/` must use
  `deployFiles: api/~` and prefixed paths.
- **`ModuleNotFoundError` at runtime** — a `pip install` in `build.buildCommands`
  installs into the *build* container, which `deployFiles` never ships. Use
  `build.addToRunPrepare` + `run.prepareCommands` (the official Zerops pattern).

---

## Known limitation ShipMate surfaces: compose env interpolation

When repo/compose mode reads a `docker-compose.yml`, ShipMate copies each
service's `environment:` values **verbatim**. Docker Compose files often use
shell-style interpolation, e.g. the `fastapi/full-stack-fastapi-template`:

```yaml
envVariables:
  SECRET_KEY: ${SECRET_KEY?Variable not set}
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD?Variable not set}
  FRONTEND_HOST: ${FRONTEND_HOST?Variable not set}
```

**This is exactly the #9 footgun repeated across a whole service.** On Zerops,
`SECRET_KEY: ${SECRET_KEY?...}` is a self-reference: there's no outer shell
substituting these, so Zerops would store the literal placeholder.

**ShipMate now handles this automatically.** The compose parser:

1. **Drops** unresolvable `${VAR}` / `${VAR?required}` values and **lists them
   in the notes** ("dropped 16 env var(s) with unresolvable ${...} …").
2. **Keeps `${VAR:-default}` defaults** (uses the default value) and genuine
   cross-service references (e.g. `POSTGRES_SERVER: db`).
3. The linter's **`self-ref-env`** rule flags any self-reference that reaches a
   topology through another path.

So the generated `zerops.yaml` is deploy-clean. Your one remaining step: **set
the dropped vars as GUI env vars / secrets** on the service — Zerops injects
them into the runtime automatically. Treat ShipMate's output as a
**review-then-ship starting point**: structure, types, ports and wiring are
correct; the dropped-secret note tells you exactly what to add in the GUI.

---

## ZCP debugging cheat-sheet

Ask your ZCP agent (or run in its terminal). These are the exact moves that
solved the errors above.

**Read the real error (do this first, always):**
```
zerops_logs — api service, last hour. Print the full traceback, not the summary.
```

**Confirm what's actually deployed:**
```
zerops_discover — api: what OS/base is the ACTIVE version, and its status?
zerops_events   — api: timestamp of the last FINISHED deploy?
```

**Prove network reachability from inside the failing service:**
```bash
getent hosts <your-endpoint-host> ; echo exit:$?     # DNS
cat /etc/resolv.conf                                  # resolver config
curl -sv --max-time 10 https://<endpoint>/... -o /dev/null 2>&1 | tail -8   # TLS reach (401/404 = success!)
```

**Verify the code & deps that actually shipped:**
```bash
grep -n '<the line you fixed>' /var/www/app/core/llm.py
python3 -m pip show httpx openai | grep -E '^(Name|Version)'
python3 -c "import os; print(repr(os.environ['AZURE_OPENAI_ENDPOINT']))"   # repr() exposes ${...}, quotes, \n
```

**Reproduce the exact failing call, standalone** (bypasses your app code — if
this works but the app doesn't, the bug is in your request specifics):
```bash
python3 - <<'EOF'
import os
from openai import OpenAI
host = os.environ['AZURE_OPENAI_ENDPOINT'].strip().strip('"').split('//')[-1].split('/')[0]
c = OpenAI(base_url=f"https://{host}/openai/v1", api_key=os.environ['AZURE_OPENAI_API_KEY'],
           default_headers={"api-key": os.environ['AZURE_OPENAI_API_KEY']})
print(c.chat.completions.create(model=os.environ['AZURE_OPENAI_DEPLOYMENT'],
      messages=[{"role":"user","content":"say ok"}]).choices[0].message.content)
EOF
```

**Golden rule:** the UI/`str(exception)` message lies by omission. The runtime
log's full traceback — and a `repr()` of the suspect env var — tell the truth.
