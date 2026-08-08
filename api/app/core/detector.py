"""Repo stack detection (Mode 2).

Given a repo's file list + manifest contents, infer the runtime and a sensible
topology. Priority order (most authoritative first):

  1. Dockerfile      — FROM → base, EXPOSE → port, CMD/ENTRYPOINT → start, ENV → env
  2. docker-compose  — if present, hand off to the compose parser (multi-service truth)
  3. language marker — package.json / requirements.txt / go.mod / ...
  4. dependency scan — postgres/redis client libs → managed services

Pure functions, no network: the worker or the repo_fetcher supply the inputs.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from .mappings import DETECT_FILES, match_runtime
from .schema import ROLE_API, ROLE_FRONTEND, ROLE_WORKER, Port, Service, Topology

_FROM_RE = re.compile(r"^\s*FROM\s+([^\s]+)", re.IGNORECASE | re.MULTILINE)
_EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+(\d+)", re.IGNORECASE | re.MULTILINE)
_CMD_RE = re.compile(r"^\s*(?:CMD|ENTRYPOINT)\s+(.+)$", re.IGNORECASE | re.MULTILINE)
_ENV_RE = re.compile(r"^\s*ENV\s+(.+)$", re.IGNORECASE | re.MULTILINE)
_PY_VER_RE = re.compile(r"python:(\d+\.\d+)")
_NODE_VER_RE = re.compile(r"node:(\d+)")


def detect_from_filelist(
    files: List[str],
    project_name: str = "detected-project",
    file_contents: Optional[Dict[str, str]] = None,
) -> Topology:
    file_contents = file_contents or {}
    lower_names = {f.rsplit("/", 1)[-1].lower(): f for f in files}

    # --- 1. docker-compose in the repo? that's the multi-service source of truth
    for key in ("docker-compose.yml", "docker-compose.yaml"):
        if key in file_contents:
            from .compose_parser import parse_compose  # local import, no cycle at module load
            topo = parse_compose(file_contents[key], project_name)
            topo.warnings.insert(0, "Detected docker-compose.yml; topology derived from it.")
            return topo

    topo = Topology(project_name=project_name)

    # --- 2. Dockerfile (authoritative for base/port/start)
    dockerfile = file_contents.get("Dockerfile") or file_contents.get("dockerfile")
    df = _parse_dockerfile(dockerfile) if dockerfile else None

    # --- 3. language marker fallback
    base, role, start = None, ROLE_API, None
    for marker, (mbase, mrole, mstart) in DETECT_FILES.items():
        if marker.lower() in lower_names:
            base, role, start = mbase, mrole, mstart
            break

    if df:
        base = df["base"] or base or "nodejs@22"
        start = df["start"] or start
        port = df["port"]
        env = df["env"]
        topo.warnings.append("Dockerfile found; base, port and start derived from it.")
    else:
        port, env = None, {}
        if base is None:
            topo.warnings.append("No runtime marker found; defaulting to nodejs@22.")
            base, start = "nodejs@22", "npm run start"

    # refine start/port from manifests
    if base.startswith("nodejs") and "package.json" in file_contents:
        pkg = _safe_json(file_contents["package.json"]) or {}
        scripts = pkg.get("scripts", {})
        if not df or not df.get("start"):
            start = "npm run start" if "start" in scripts else ("npm run dev" if "dev" in scripts else start)
        # a vite/CRA app with no server deps is a static frontend
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "vite" in deps and not any(d in deps for d in ("express", "fastify", "koa", "next")):
            role = ROLE_FRONTEND

    if port is None:
        port = 8000 if base.startswith("python") else 3000

    app = Service(
        hostname="app",
        role=role,
        type=base,
        base=base,
        ports=[Port(port=port, http_support=True)],
        start=start,
        build_commands=_build_for(base),
        env=env,
        public=True,
    )
    topo.services.append(app)

    # --- 4. dependency scan → managed services
    deps_blob = " ".join(file_contents.values()).lower()
    if _mentions(deps_blob, "psycopg", "asyncpg", "postgres", "prisma", "sequelize", "typeorm", "sqlalchemy"):
        topo.services.append(Service(hostname="db", role="database", type="postgresql@16"))
        app.env.setdefault("DB_HOST", "db")
        app.depends_on.append("db")
    if _mentions(deps_blob, "redis", "ioredis", "valkey", "celery"):
        topo.services.append(Service(hostname="cache", role="cache", type="valkey@7"))
        app.env.setdefault("CACHE_HOST", "cache")
        app.depends_on.append("cache")
    if _mentions(deps_blob, "boto3", "minio", "aws-sdk", "s3client"):
        topo.services.append(Service(hostname="storage", role="storage", type="object-storage"))
        app.depends_on.append("storage")

    return topo


def _parse_dockerfile(text: str) -> Dict:
    """Extract base, port, start command and ENV vars from a Dockerfile."""
    out: Dict = {"base": None, "port": None, "start": None, "env": {}}

    froms = _FROM_RE.findall(text)
    if froms:
        image = froms[-1].lower()  # last stage wins in multi-stage builds
        pyv = _PY_VER_RE.search(image)
        nodev = _NODE_VER_RE.search(image)
        if pyv:
            out["base"] = f"python@{pyv.group(1)}"
        elif nodev:
            out["base"] = f"nodejs@{nodev.group(1)}"
        else:
            rt = match_runtime(image.split(" ")[0])
            out["base"] = rt[0] if rt else None

    expose = _EXPOSE_RE.search(text)
    if expose:
        out["port"] = int(expose.group(1))

    cmd = _CMD_RE.findall(text)
    if cmd:
        out["start"] = _cmd_to_start(cmd[-1].strip())

    for env_line in _ENV_RE.findall(text):
        # handles both `ENV A=1 B=2` and continuation-style `ENV A=1 \`
        for pair in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s\\]+)", env_line):
            out["env"][pair[0]] = pair[1]

    return out


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
