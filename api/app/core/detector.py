"""Repo stack detection (Mode 2).

Given a flat list of file paths from a cloned repo, infer the runtime and a
sensible default topology. The worker does the actual `git clone`; this module
is pure and unit-testable so we can reason about it without the network.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from .mappings import DETECT_FILES
from .schema import ROLE_API, Port, Service, Topology


def detect_from_filelist(
    files: List[str],
    project_name: str = "detected-project",
    file_contents: Optional[Dict[str, str]] = None,
) -> Topology:
    """`files` is repo-root-relative paths. `file_contents` optionally maps a
    filename to its text (e.g. package.json) so we can read scripts/ports."""
    file_contents = file_contents or {}
    topo = Topology(project_name=project_name)
    root = {f.split("/")[0] for f in files} | set(files)

    base = None
    role = ROLE_API
    start = None
    for marker, (mbase, mrole, mstart) in DETECT_FILES.items():
        if marker in files or marker in root:
            base, role, start = mbase, mrole, mstart
            break

    if base is None:
        topo.warnings.append("No known runtime marker found; defaulting to nodejs@22.")
        base, start = "nodejs@22", "npm run start"

    port = 8000 if base.startswith("python") else 3000
    build_cmds = _build_for(base)

    # refine from package.json if present
    if base.startswith("nodejs") and "package.json" in file_contents:
        pkg = _safe_json(file_contents["package.json"])
        scripts = (pkg or {}).get("scripts", {})
        if "start" in scripts:
            start = "npm run start"
        elif "dev" in scripts:
            start = "npm run dev"

    has_dockerfile = any(f.lower().endswith("dockerfile") for f in files)
    if has_dockerfile:
        topo.warnings.append("Dockerfile present; Zerops can build from it, but a native base is faster.")

    api = Service(
        hostname="app",
        role=role,
        type=base,
        base=base,
        ports=[Port(port=port, http_support=True)],
        start=start,
        build_commands=build_cmds,
        public=True,
    )
    topo.services.append(api)

    # naive add-on detection from lockfiles / deps
    deps_blob = " ".join(file_contents.values()).lower()
    if any(k in deps_blob for k in ("psycopg", "pg", "postgres", "prisma", "sequelize", "typeorm")):
        topo.services.append(Service(hostname="db", role="database", type="postgresql@16"))
        api.env["DB_HOST"] = "db"
        api.depends_on.append("db")
    if any(k in deps_blob for k in ("redis", "ioredis", "valkey")):
        topo.services.append(Service(hostname="cache", role="cache", type="valkey@7"))
        api.env["CACHE_HOST"] = "cache"
        api.depends_on.append("cache")

    return topo


def _safe_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def _build_for(base: str) -> List[str]:
    if base.startswith("python"):
        return ["pip install -r requirements.txt"]
    if base.startswith("nodejs"):
        return ["npm ci", "npm run build"]
    if base.startswith("go"):
        return ["go build -o app ."]
    return []
