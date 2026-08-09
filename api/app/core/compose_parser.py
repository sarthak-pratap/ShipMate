"""docker-compose.yml -> Topology (Mode 3, the deterministic core).

This is the most reliable of ShipMate's three input modes: no LLM in the loop,
just a documented mapping from Compose concepts to Zerops concepts:

    compose service          -> Zerops service
    image                    -> Zerops managed type / runtime base
    ports "8000:8000"        -> run.ports[].port (+ httpSupport)
    depends_on / links       -> private-network wiring (edges)
    environment              -> run.envVariables (localhost rewritten to hostname)
"""
from __future__ import annotations

import re
from typing import Dict, List

import yaml

from .mappings import match_managed, match_runtime, match_unsupported
from .schema import (
    ROLE_API,
    ROLE_FRONTEND,
    ROLE_WORKER,
    Port,
    Service,
    Topology,
)

_LOCALHOST_RE = re.compile(r"(localhost|127\.0\.0\.1)")


def _parse_ports(raw_ports: List) -> List[Port]:
    ports: List[Port] = []
    for entry in raw_ports or []:
        # forms: "8000:8000", "80:8080", 8000, {target: 8000, published: 80}
        target = None
        if isinstance(entry, int):
            target = entry
        elif isinstance(entry, str):
            parts = entry.split(":")
            target = parts[-1].split("/")[0]
        elif isinstance(entry, dict):
            target = entry.get("target") or entry.get("published")
        try:
            p = int(target)
            ports.append(Port(port=p, http_support=_looks_http(p)))
        except (TypeError, ValueError):
            continue
    return ports


def _looks_http(port: int) -> bool:
    # common non-http ports we should NOT mark httpSupport on
    non_http = {5432, 3306, 27017, 6379, 5672, 9092, 4222, 9200}
    return port not in non_http


def _norm_env(env) -> Dict[str, str]:
    """Compose env can be a dict or a `KEY=value` list."""
    out: Dict[str, str] = {}
    if isinstance(env, dict):
        for k, v in env.items():
            out[str(k)] = "" if v is None else str(v)
    elif isinstance(env, list):
        for item in env or []:
            if "=" in str(item):
                k, v = str(item).split("=", 1)
                out[k] = v
    return out


def _guess_runtime_role(name: str) -> str:
    n = name.lower()
    if any(w in n for w in ("web", "front", "ui", "client", "nginx")):
        return ROLE_FRONTEND
    if any(w in n for w in ("worker", "job", "cron", "queue", "consumer", "beat")):
        return ROLE_WORKER
    return ROLE_API


def parse_compose(text: str, project_name: str = "my-project") -> Topology:
    data = yaml.safe_load(text) or {}
    services_raw = data.get("services", {}) or {}
    topo = Topology(project_name=data.get("name", project_name))

    # first pass: collect the set of hostnames so we can rewrite localhost refs
    hostnames = set(services_raw.keys())

    for name, cfg in services_raw.items():
        cfg = cfg or {}
        image = cfg.get("image", "")
        has_build = "build" in cfg

        managed = match_managed(image) if image else None
        if managed:
            ztype, role, ha_capable = managed
            svc = Service(
                hostname=name,
                role=role,
                type=ztype,
                ha=bool(ha_capable and _wants_ha(cfg)),
                depends_on=list(cfg.get("depends_on", []) or []),
            )
            topo.services.append(svc)
            continue

        unsupported = match_unsupported(image) if image else None
        if unsupported:
            ztype, role, note = unsupported
            topo.warnings.append(f"service '{name}': {note}")
            topo.services.append(Service(
                hostname=name, role=role, type=ztype,
                depends_on=list(cfg.get("depends_on", []) or []),
            ))
            continue

        # runtime service (either an explicit runtime image or a local build)
        base = "nodejs@22"
        if image:
            rt = match_runtime(image)
            if rt:
                base = rt[0]
            else:
                topo.warnings.append(
                    f"service '{name}': unknown image '{image}', defaulting base to {base}"
                )
        elif has_build:
            topo.warnings.append(
                f"service '{name}': builds from a Dockerfile; verify the base ({base})"
            )

        role = _guess_runtime_role(name)
        ports = _parse_ports(cfg.get("ports", []))
        env, dropped = _clean_interpolations(_norm_env(cfg.get("environment")))
        env = _rewrite_localhost(env, hostnames)
        if dropped:
            shown = ", ".join(dropped[:6]) + (", …" if len(dropped) > 6 else "")
            topo.warnings.append(
                f"service '{name}': dropped {len(dropped)} env var(s) with unresolvable "
                f"${{...}} interpolation ({shown}) — set them as env vars/secrets in the "
                f"Zerops GUI. A 'VAR: ${{VAR}}' mapping would store the literal placeholder."
            )

        build_ctx = None  # normalized path to the service's Dockerfile
        if has_build:
            b = cfg.get("build")
            if isinstance(b, str):
                ctx, dfile = b, "Dockerfile"
            else:
                ctx = (b or {}).get("context", ".")
                dfile = (b or {}).get("dockerfile", "Dockerfile")
            import posixpath
            build_ctx = posixpath.normpath(
                posixpath.join(ctx.lstrip("./") or ".", dfile)
            ).lstrip("./") or None

        svc = Service(
            hostname=name,
            role=role,
            type=base,
            base=base,
            ports=ports,
            env=env,
            depends_on=list(cfg.get("depends_on", []) or []),
            public=bool(ports) and role in (ROLE_FRONTEND, ROLE_API),
            start=_default_start(base, role),
            build_commands=_default_build(base),
            build_context=build_ctx,
            # when a compose service builds from a subdir, its source lives there
            src_dir=(build_ctx.rsplit("/", 1)[0] if build_ctx and "/" in build_ctx else None),
        )
        topo.services.append(svc)

    if not topo.runtimes() and topo.managed():
        topo.warnings.append(
            "This compose declares only managed services (no app/runtime) — so the "
            "zerops.yaml has no build/run blocks. Paste a compose that includes your "
            "app, or use Repo URL mode to detect the app from your code."
        )

    return topo


def _wants_ha(cfg: dict) -> bool:
    dep = cfg.get("deploy", {}) or {}
    replicas = dep.get("replicas")
    return bool(replicas and int(replicas) > 1)


# a value that is exactly one ${VAR}, ${VAR:-default}, ${VAR-default} or ${VAR?msg}
_FULL_INTERP = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-|-)(.*)|(\?.*))?\}$")


def _clean_interpolations(env: Dict[str, str]):
    """Compose `environment:` often uses shell interpolation (`${VAR}`,
    `${VAR:-default}`, `${VAR?required}`). Zerops has no outer shell to expand
    these, and `VAR: ${VAR}` is a self-reference that stores the literal
    placeholder (the bug that cost us a live deploy). So:

      - `${VAR:-default}` / `${VAR-default}`  -> keep the default value
      - `${VAR}` / `${VAR?required}`          -> DROP (must be a GUI env/secret)
      - text containing `${...}`               -> DROP (can't safely resolve)
      - plain values & cross-service refs      -> keep unchanged

    Returns (clean_env, dropped_keys).
    """
    clean: Dict[str, str] = {}
    dropped = []
    for k, v in env.items():
        s = str(v).strip()
        m = _FULL_INTERP.match(s)
        if m:
            if m.group(2) is not None:      # has a :- / - default
                clean[k] = m.group(3)
            else:                            # ${VAR} or ${VAR?msg} -> unresolvable
                dropped.append(k)
            continue
        if "${" in s:                        # partial interpolation in text
            dropped.append(k)
            continue
        clean[k] = str(v)
    return clean, dropped


def _rewrite_localhost(env: Dict[str, str], hostnames: set) -> Dict[str, str]:
    """If a value points at localhost but a sibling service exists, leave a hint.

    We can't always know which hostname the user meant, so we only strip the
    scheme host when it's an obvious `localhost`, and the linter will still flag
    anything suspicious. This keeps the transform conservative & explainable.
    """
    out = {}
    for k, v in env.items():
        out[k] = _LOCALHOST_RE.sub("HOSTNAME", v) if _LOCALHOST_RE.search(v) else v
    return out


def _default_start(base: str, role: str):
    if base.startswith("python"):
        return "uvicorn app.main:app --host 0.0.0.0 --port 8000"
    if base.startswith("nodejs"):
        return "npm run start"
    if base.startswith("go"):
        return "./app"
    return None


def _default_build(base: str) -> List[str]:
    if base.startswith("python"):
        return ["pip install -r requirements.txt"]
    if base.startswith("nodejs"):
        return ["npm ci", "npm run build"]
    if base.startswith("go"):
        return ["go build -o app ."]
    return []
