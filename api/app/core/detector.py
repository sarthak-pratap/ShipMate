"""Repo stack detection (Mode 2).

Given a repo's file list + manifest contents, infer the runtime(s) and a
sensible topology. Priority order (most authoritative first):

  1. docker-compose  — if present, hand off to the compose parser (multi-service truth)
  2. monorepo        — runtime manifests in several subdirs → one service per subdir
  3. Dockerfile      — FROM → base, EXPOSE → port, CMD/ENTRYPOINT → start, ENV → env
  4. language marker — package.json / requirements.txt / go.mod / ...
  5. dependency scan — postgres/redis/s3 client libs → managed services

`file_contents` may be keyed by full path ("backend/requirements.txt") or by
basename ("requirements.txt") — both are accepted.

Pure functions, no network: the worker or the repo_fetcher supply the inputs.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from .mappings import DETECT_FILES, match_runtime
from .schema import ROLE_API, ROLE_FRONTEND, ROLE_WORKER, Port, Service, Topology

_FROM_RE = re.compile(
    r"^\s*FROM\s+(?:--platform=\S+\s+)?([^\s]+)(?:\s+[Aa][Ss]\s+([^\s]+))?",
    re.IGNORECASE | re.MULTILINE,
)
_EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+(\d+)", re.IGNORECASE | re.MULTILINE)
_CMD_RE = re.compile(r"^\s*(?:CMD|ENTRYPOINT)\s+(.+)$", re.IGNORECASE | re.MULTILINE)
_ENV_RE = re.compile(r"^\s*ENV\s+(.+)$", re.IGNORECASE | re.MULTILINE)
_PY_VER_RE = re.compile(r"python:(\d+\.\d+)")
_NODE_VER_RE = re.compile(r"node:(\d+)")

_FRONTEND_DIRS = ("frontend", "web", "client", "ui", "www", "app-web")
_WORKER_DIRS = ("worker", "workers", "jobs", "cron", "consumer", "tasks")

# markers that identify a runtime root (subset of DETECT_FILES keys, lowercase)
_RUNTIME_MARKERS = {m.lower() for m in DETECT_FILES}


class _Contents:
    """Path-or-basename lookup over the provided file_contents mapping."""

    def __init__(self, raw: Dict[str, str]):
        self.raw = raw or {}

    def get(self, path: str) -> Optional[str]:
        if path in self.raw:
            return self.raw[path]
        base = path.rsplit("/", 1)[-1]
        if base in self.raw:
            return self.raw[base]
        # case-insensitive fallback (Dockerfile vs dockerfile)
        for k, v in self.raw.items():
            if k.lower() == path.lower() or k.rsplit("/", 1)[-1].lower() == base.lower():
                return v
        return None

    def blob(self) -> str:
        return " ".join(self.raw.values()).lower()


def detect_from_filelist(
    files: List[str],
    project_name: str = "detected-project",
    file_contents: Optional[Dict[str, str]] = None,
) -> Topology:
    contents = _Contents(file_contents or {})

    # --- 1. root docker-compose?
    #   • has app/runtime services -> it's the whole story, use it
    #   • only managed services (db/cache/... local-dev infra) -> remember them,
    #     but keep detecting the real app from the code and merge later
    infra_managed = []  # managed services from an "infra-only" compose
    for f in files:
        base = f.rsplit("/", 1)[-1].lower()
        if base in ("docker-compose.yml", "docker-compose.yaml",
                    "compose.yml", "compose.yaml") and f.count("/") == 0:
            text = contents.get(f)
            if not text:
                continue
            from .compose_parser import parse_compose
            ctopo = parse_compose(text, project_name)
            _refine_from_service_dockerfiles(ctopo, contents)
            if ctopo.runtimes():
                ctopo.warnings.insert(0, f"Detected {base}; topology derived from it.")
                return ctopo
            infra_managed = ctopo.managed()  # infra-only; merge after code detection
            break

    # --- 2. locate runtime roots: dirs (incl. repo root "") holding a marker
    roots: Dict[str, str] = {}  # dir -> marker filename
    for f in files:
        parts = f.split("/")
        base = parts[-1].lower()
        if base in _RUNTIME_MARKERS:
            d = "/".join(parts[:-1])
            if d.count("/") <= 0 and d not in roots:  # root or first-level dirs only
                roots[d] = parts[-1]

    topo = Topology(project_name=project_name)

    if len([d for d in roots if d != ""]) >= 2 and "" not in roots:
        # --- monorepo: one runtime service per top-level dir
        topo.warnings.append(
            f"Monorepo detected ({', '.join(sorted(roots))}); one service per directory."
        )
        for d in sorted(roots):
            svc = _detect_service(d, files, contents, hostname=_hostname_for(d))
            topo.services.append(svc)
        _wire_frontend_to_api(topo)
    else:
        # --- single service at the repo root (or the one subdir that has code)
        root = "" if "" in roots else (sorted(roots)[0] if roots else "")
        svc = _detect_service(root, files, contents, hostname="app")
        if root:
            topo.warnings.append(f"Runtime found in '{root}/'.")
        if svc.base is None:
            topo.warnings.append("No runtime marker found; defaulting to nodejs@22.")
            svc.base = svc.type = "nodejs@22"
            svc.start = svc.start or "npm run start"
        topo.services.append(svc)

    # --- merge managed services from an infra-only root compose
    apis = [s for s in topo.services if s.role in (ROLE_API, ROLE_WORKER)]
    attach = apis[0] if apis else (topo.services[0] if topo.services else None)
    if infra_managed:
        topo.warnings.append(
            "Root compose is infra-only; merged its managed services with the app detected from code."
        )
        for m in infra_managed:
            if topo.by_hostname(m.hostname):
                continue
            topo.services.append(m)
            if not attach:
                continue
            if m.role == "database":
                attach.env.setdefault("DB_HOST", m.hostname)
                attach.depends_on.append(m.hostname)
            elif m.role == "cache":
                attach.env.setdefault("CACHE_HOST", m.hostname)
                attach.depends_on.append(m.hostname)
            else:
                attach.depends_on.append(m.hostname)

    # --- secrets awareness: surface keys from .env.example that must be set
    # as envSecrets in the Zerops GUI (we never bake secret values into YAML)
    env_example = None
    for key in contents.raw:
        if key.lower().endswith(".env.example"):
            env_example = contents.raw[key]
            break
    if env_example:
        secretish = []
        for line in env_example.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k = line.split("=", 1)[0].strip()
            if any(t in k.upper() for t in ("KEY", "SECRET", "TOKEN", "PASSWORD",
                                             "PASS", "ENDPOINT", "API", "DSN")):
                secretish.append(k)
        if secretish:
            topo.warnings.append(
                "Secrets found in .env.example (" + ", ".join(secretish[:6]) +
                (", …" if len(secretish) > 6 else "") +
                ") — set these as envSecrets on the runtime services in the "
                "Zerops GUI after import; they are intentionally not in the YAML."
            )

    # --- dependency scan → managed services (skip roles already present)
    blob = contents.blob()
    have = {s.role for s in topo.services}
    if attach:
        if "database" not in have and _mentions(
                blob, "psycopg", "asyncpg", "postgres", "prisma", "sequelize",
                "typeorm", "sqlalchemy", "sqlmodel"):
            topo.services.append(Service(hostname="db", role="database", type="postgresql@16"))
            attach.env.setdefault("DB_HOST", "db")
            attach.depends_on.append("db")
        if "cache" not in have and _mentions(blob, "redis", "ioredis", "valkey", "celery"):
            topo.services.append(Service(hostname="cache", role="cache", type="valkey@7.2"))
            attach.env.setdefault("CACHE_HOST", "cache")
            attach.depends_on.append("cache")
        if "storage" not in have and _mentions(blob, "boto3", "minio", "aws-sdk", "s3client"):
            topo.services.append(Service(hostname="storage", role="storage", type="object-storage"))
            attach.depends_on.append("storage")

    return topo


def _refine_from_service_dockerfiles(topo: Topology, contents: _Contents) -> None:
    """Compose services that `build:` a directory get their base/port/start
    corrected from that directory's Dockerfile (compose alone can't know)."""
    for svc in topo.runtimes():
        ctx = svc.build_context  # normalized Dockerfile path from the compose file
        if not ctx:
            continue
        df_text = contents.get(ctx)
        if not df_text:
            continue
        df = _parse_dockerfile(df_text)
        if df["base"]:
            svc.base = svc.type = df["base"]
            svc.build_commands = _build_for(df["base"])
            if not df["start"]:
                svc.start = _default_start_for(df["base"])
        if df["start"]:
            svc.start = df["start"]
        if df["port"] and not svc.ports:
            svc.ports = [Port(port=df["port"], http_support=True)]
        for k, v in df["env"].items():
            svc.env.setdefault(k, v)
        topo.warnings.append(f"'{svc.hostname}': refined from {ctx}.")


def _default_start_for(base: str) -> Optional[str]:
    if base.startswith("python"):
        return "uvicorn app.main:app --host 0.0.0.0 --port 8000"
    if base.startswith("nodejs"):
        return "npm run start"
    if base.startswith("go"):
        return "./app"
    return None


def _detect_service(dir_prefix: str, files: List[str], contents: _Contents,
                    hostname: str) -> Service:
    """Detect one runtime service rooted at `dir_prefix` ("" = repo root)."""
    pfx = f"{dir_prefix}/" if dir_prefix else ""

    # Dockerfile in this dir is authoritative
    df_text = contents.get(f"{pfx}Dockerfile")
    df = _parse_dockerfile(df_text) if df_text else None

    # language marker fallback
    base, role, start = None, ROLE_API, None
    scoped = {f[len(pfx):] for f in files if f.startswith(pfx)}
    scoped_lower = {s.lower() for s in scoped if "/" not in s}
    for marker, (mbase, mrole, mstart) in DETECT_FILES.items():
        if marker.lower() in scoped_lower:
            base, role, start = mbase, mrole, mstart
            break

    port, env = None, {}
    if df:
        base = df["base"] or base
        start = df["start"] or start
        port = df["port"]
        env = df["env"]

    # role refinement from the directory name
    dname = dir_prefix.lower()
    if any(w in dname for w in _FRONTEND_DIRS):
        role = ROLE_FRONTEND
    elif any(w in dname for w in _WORKER_DIRS):
        role = ROLE_WORKER

    # refine from package.json — NEVER pick `dev` scripts (dev servers don't
    # belong in production; frontends get built to static instead)
    pkg_text = contents.get(f"{pfx}package.json")
    if base and base.startswith("nodejs") and pkg_text:
        pkg = _safe_json(pkg_text) or {}
        scripts = pkg.get("scripts", {})
        if not (df and df.get("start")):
            if "start" in scripts:
                start = "npm run start"
            elif "serve" in scripts:
                start = "npm run serve"
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "vite" in deps and not any(d in deps for d in ("express", "fastify", "koa", "next")):
            role = ROLE_FRONTEND

    # workers are background processes: no ports, and their start command is
    # the worker script — not a copy of the API's server command
    if role == ROLE_WORKER:
        port = None
        if not (df and df.get("start")):
            start = _worker_start(base, scoped)

    if port is None and base and role != ROLE_WORKER:
        port = 8000 if base.startswith("python") else 3000

    return Service(
        hostname=hostname,
        role=role,
        type=base or "nodejs@22",
        base=base,
        ports=[Port(port=port, http_support=True)] if port else [],
        start=start,
        build_commands=_build_for(base or "nodejs@22"),
        env=env,
        public=role in (ROLE_FRONTEND, ROLE_API),
    )


def _worker_start(base: Optional[str], scoped_files: set) -> Optional[str]:
    """Pick a sensible background-process start command from real files."""
    lower = {s.lower() for s in scoped_files}
    if base and base.startswith("python"):
        for cand in ("worker.py", "main.py", "run.py", "app.py", "tasks.py"):
            if cand in lower:
                return f"python {cand}"
        return "python worker.py"
    if base and base.startswith("nodejs"):
        for cand in ("worker.js", "index.js", "main.js"):
            if cand in lower:
                return f"node {cand}"
        return "node worker.js"
    if base and base.startswith("go"):
        return "./app"
    return None


def _wire_frontend_to_api(topo: Topology) -> None:
    fronts = [s for s in topo.services if s.role == ROLE_FRONTEND]
    apis = [s for s in topo.services if s.role == ROLE_API]
    for f in fronts:
        for a in apis:
            f.depends_on.append(a.hostname)


def _hostname_for(d: str) -> str:
    name = re.sub(r"[^a-z0-9]", "", d.lower()) or "app"
    aliases = {"backend": "api", "server": "api", "frontend": "web", "client": "web"}
    return aliases.get(name, name)


def _parse_dockerfile(text: str) -> Dict:
    """Extract base, port, start command and ENV vars from a Dockerfile."""
    out: Dict = {"base": None, "port": None, "start": None, "env": {}}

    stages = _FROM_RE.findall(text)
    if stages:
        # resolve the final stage through `FROM <img> AS <alias>` chains
        aliases = {alias.lower(): img for img, alias in stages if alias}
        image, seen = stages[-1][0], set()
        while image.lower() in aliases and image.lower() not in seen:
            seen.add(image.lower())
            image = aliases[image.lower()]
        image = image.lower()

        pyv = _PY_VER_RE.search(image)
        nodev = _NODE_VER_RE.search(image)
        if pyv:
            out["base"] = f"python@{pyv.group(1)}"
        elif nodev:
            out["base"] = f"nodejs@{nodev.group(1)}"
        else:
            rt = match_runtime(image.split(" ")[0])
            out["base"] = rt[0] if rt else _image_keyword_base(image)

    expose = _EXPOSE_RE.search(text)
    if expose:
        out["port"] = int(expose.group(1))

    cmd = _CMD_RE.findall(text)
    if cmd:
        out["start"] = _cmd_to_start(cmd[-1].strip())

    for env_line in _ENV_RE.findall(text):
        for pair in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s\\]+)", env_line):
            out["env"][pair[0]] = pair[1]

    return out


def _image_keyword_base(image: str) -> Optional[str]:
    """Last-resort mapping for registry-prefixed images (mcr, gcr, ghcr...)."""
    for kw, base in (
        ("dotnet", "dotnet@8"), ("aspnet", "dotnet@8"),
        ("python", "python@3.12"), ("node", "nodejs@22"),
        ("golang", "go@1"), ("temurin", "java@21"), ("openjdk", "java@21"),
        ("php", "php@8.3"), ("ruby", "ruby@3.3"), ("rust", "rust@1"),
    ):
        if kw in image:
            return base
    return None


def _cmd_to_start(raw: str) -> str:
    """CMD ["python","-m","app.run"] or CMD python -m app.run → shell command."""
    raw = raw.strip()
    if raw.startswith("["):
        try:
            parts = json.loads(raw)
            return " ".join(str(p) for p in parts)
        except Exception:  # noqa: BLE001
            pass
    return raw


def _mentions(blob: str, *needles: str) -> bool:
    return any(n in blob for n in needles)


def _safe_json(text: str):
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return None


def _build_for(base: str) -> List[str]:
    if base.startswith("python"):
        return ["pip install -r requirements.txt"]
    if base.startswith("nodejs"):
        return ["npm ci", "npm run build"]
    if base.startswith("go"):
        return ["go build -o app ."]
    return []
