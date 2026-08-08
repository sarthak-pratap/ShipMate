"""Offline prompt mode — plain English → Topology with NO LLM.

Prompt mode should always work, even with no Azure OpenAI key configured. This
deterministic keyword parser is the zero-config fallback (and the safety net if
a live LLM call fails). When Azure is configured, `llm.py` takes over for
higher-quality results; otherwise this runs and the API annotates the output
with a note so the user knows how it was produced.

It's intentionally simple and fully explainable: scan the description for
signals, assemble a sensible multi-service topology, wire it over the private
network.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from .schema import (
    ROLE_API,
    ROLE_BROKER,
    ROLE_CACHE,
    ROLE_DATABASE,
    ROLE_FRONTEND,
    ROLE_SEARCH,
    ROLE_STORAGE,
    ROLE_WORKER,
    Port,
    Service,
    Topology,
)

# (type, hostname, [keywords]) — first match wins per group.
# Types verified against docs.zerops.io. NOTE: Zerops has no managed MongoDB —
# mongo-ish prompts get Postgres plus an explanatory note (added below).
_DB_SIGNALS: List[Tuple[str, str, List[str]]] = [
    ("postgresql@16", "db", ["mongo", "mongodb", "document db", "nosql"]),
    ("mariadb@10.4", "db", ["mysql", "mariadb"]),
    ("postgresql@16", "db", ["postgres", "postgresql", "pgvector", "sql", "relational",
                              "database", "db", "rag", "embedding", "vector"]),
]
_MONGO_KW = ["mongo", "mongodb", "document db", "nosql"]
_CACHE_KW = ["redis", "valkey", "cache", "session", "presence", "rate limit",
             "rate-limit", "queue", "celery"]
# product-intent words that imply persistence even when no DB tech is named
_DB_INTENT_KW = ["to-do", "todo", "to do", "note", "task", "list", "save",
                 "store", "persist", "record", "crud", "account", "user",
                 "profile", "post", "comment", "history", "track", "inventory",
                 "booking", "order", "catalog", "blog", "meeting", "message",
                 "log", "review", "ticket", "form", "survey", "poll", "wiki",
                 "shorten", "shortener", "link", "document", "doc", "page",
                 "content", "report", "manage", "crm", "e-commerce", "shop",
                 "store front", "storefront", "forum", "feed", "library"]
# words implying multi-user collaboration / realtime sync (→ cache + note)
_COLLAB_KW = ["collab", "shared", "with others", "team", "multiplayer",
              "together", "sync", "concurrent", "co-edit", "coedit"]
_WORKER_KW = ["worker", "background", "job", "cron", "scheduled", "nightly",
              "reminder", "email", "digest", "ingest", "pipeline", "consumer",
              "process", "batch", "etl"]
_FRONTEND_KW = ["frontend", "front-end", "react", "vue", "svelte", "next",
                "spa", "dashboard", " ui", "web app", "webapp", "website",
                "landing", "client app", "portal", "interface"]
_BROKER_KW = ["rabbitmq", "kafka", "nats", "message queue", "message broker",
              "broker", "pub/sub", "pubsub", "event stream", "amqp"]
_STORAGE_KW = ["upload", "file storage", "object storage", "s3", "media",
               "image", "photo", "video", "attachment", "bucket", "pdf",
               "document store"]
_SEARCH_KW = ["elasticsearch", "opensearch", "full-text", "full text",
              "typesense", "meilisearch"]
_NODE_KW = ["node", "nodejs", "express", "nestjs", "typescript", "javascript",
            "fastify", "koa"]
_WS_KW = ["websocket", "realtime", "real-time", "live ", "multiplayer",
          "collaborative", "chat"]


def _has(text: str, kws: List[str]) -> bool:
    return any(k in text for k in kws)


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop = {"a", "an", "the", "with", "and", "for", "of", "app", "that", "to",
            "my", "our", "some", "using", "built"}
    keep = [w for w in words if w not in stop][:3]
    return "-".join(keep) or "my-app"


def topology_from_prompt_offline(prompt: str) -> Topology:
    t = " " + prompt.lower() + " "
    topo = Topology(project_name=_slug(prompt))

    is_node = _has(t, _NODE_KW)
    api_base = "nodejs@22" if is_node else "python@3.12"
    api_start = ("npm run start" if is_node
                 else "uvicorn app.main:app --host 0.0.0.0 --port 8000")
    api_port = 3000 if is_node else 8000

    api = Service(
        hostname="api", role=ROLE_API, type=api_base, base=api_base,
        ports=[Port(api_port)], start=api_start, public=True,
        build_commands=(["npm ci", "npm run build"] if is_node
                        else ["pip install -r requirements.txt"]),
    )
    topo.services.append(api)

    collab = _has(t, _COLLAB_KW)

    # database (one, first explicit signal wins; else infer from product intent).
    # Collaboration implies shared state, so it also implies persistence.
    db_type = None
    for ztype, host, kws in _DB_SIGNALS:
        if _has(t, kws):
            db_type = ztype
            break
    if db_type is None and (_has(t, _DB_INTENT_KW) or collab):
        db_type = "postgresql@16"
        topo.warnings.append("Persistence implied by the description — added Postgres.")
    if db_type:
        topo.services.append(Service(hostname="db", role=ROLE_DATABASE, type=db_type))
        api.env["DB_HOST"] = "db"
        api.depends_on.append("db")
        if _has(t, _MONGO_KW):
            topo.warnings.append(
                "Zerops has no managed MongoDB — used PostgreSQL instead; "
                "adapt your data layer or run Mongo in a container."
            )

    # collaboration / realtime → cache for presence & sync
    if _has(t, _CACHE_KW) or _has(t, _WS_KW) or collab:
        topo.services.append(Service(hostname="cache", role=ROLE_CACHE, type="valkey@7.2"))
        api.env["CACHE_HOST"] = "cache"
        api.depends_on.append("cache")
        if collab:
            topo.warnings.append("Collaboration detected — cache added for presence/live sync.")

    if _has(t, _BROKER_KW):
        topo.services.append(Service(hostname="broker", role=ROLE_BROKER, type="nats@2.10"))
        api.depends_on.append("broker")

    if _has(t, _STORAGE_KW):
        topo.services.append(Service(hostname="storage", role=ROLE_STORAGE, type="object-storage"))
        api.depends_on.append("storage")

    if _has(t, _SEARCH_KW):
        topo.services.append(Service(hostname="search", role=ROLE_SEARCH, type="elasticsearch@8.16"))
        api.depends_on.append("search")

    # worker
    if _has(t, _WORKER_KW):
        w = Service(
            hostname="worker", role=ROLE_WORKER, type=api_base, base=api_base,
            start=("node worker.js" if is_node else "python worker.py"),
            build_commands=api.build_commands,
        )
        # worker shares the datastores
        for dep in ("db", "cache", "broker"):
            if topo.by_hostname(dep):
                w.depends_on.append(dep)
                if dep == "db":
                    w.env["DB_HOST"] = "db"
                if dep == "cache":
                    w.env["CACHE_HOST"] = "cache"
        topo.services.append(w)

    # frontend
    if _has(t, _FRONTEND_KW):
        web = Service(
            hostname="web", role=ROLE_FRONTEND, type="nodejs@22", base="nodejs@22",
            ports=[Port(3000)], start="npm run start", public=True,
            build_commands=["npm ci", "npm run build"],
            depends_on=["api"], env={"VITE_API_BASE": "${api_url}"},
        )
        topo.services.append(web)

    if _has(t, _WS_KW):
        topo.warnings.append("Realtime/websocket detected — the api serves websockets; cache added for presence/pub-sub.")

    return topo
