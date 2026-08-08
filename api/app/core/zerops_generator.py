"""Topology -> zerops.yaml + zerops-project-import.yml.

Two artifacts, matching the real Zerops schema:

  zerops.yaml            -> per-runtime build/run config (the `zerops:` list)
  zerops-project-import  -> `project:` + `services:` declaring every service
                            (managed types, runtimes, HA mode, subdomain access)
"""
from __future__ import annotations

from typing import Dict, List

import yaml

from .schema import Service, Topology


class _IndentDumper(yaml.Dumper):
    """Make list indentation readable (2-space, nested under keys)."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def _str_representer(dumper, data):
    """Multiline strings (monorepo `cd dir` build blocks) dump as literal `|`
    blocks — quoted style would fold the newlines into spaces and break the
    shell commands."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_IndentDumper.add_representer(str, _str_representer)


def _dump(data) -> str:
    return yaml.dump(
        data,
        Dumper=_IndentDumper,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )


def _cd_commands(src: str, cmds: List[str]) -> List[str]:
    """Build commands run in /build/source (the repo root as pushed). For a
    monorepo service, run them inside its subdir via one shell block."""
    if not src:
        return list(cmds)
    return ["\n".join(["cd " + src] + list(cmds))]


def build_zerops_yaml(topo: Topology) -> str:
    """The `zerops:` config — one entry per runtime service.

    Monorepo-aware: when a service's source lives in a subdir (src_dir), build
    commands `cd` into it and deployFiles ships `<dir>/~` (the dir's contents),
    so pushing from the repo root works. Python deps follow the official Zerops
    pattern: installed in run.prepareCommands with requirements.txt carried
    over via build.addToRunPrepare (a build-container pip install would never
    reach the runtime container).
    """
    setups: List[Dict] = []
    for svc in topo.runtimes():
        src = (svc.src_dir or "").strip("/")
        p = f"{src}/" if src else ""
        is_python = bool(svc.base and svc.base.startswith("python"))
        is_node = bool(svc.base and svc.base.startswith("nodejs"))

        build_block: Dict = {"base": svc.base}
        run_block: Dict

        # Frontends: build with node, SERVE STATIC. Never ship a dev server.
        is_static_frontend = (
            svc.role == "frontend" and is_node and not _looks_ssr(svc)
        )
        if is_static_frontend:
            cmds = svc.build_commands or ["npm ci", "npm run build"]
            build_block["buildCommands"] = _cd_commands(src, cmds)
            build_block["deployFiles"] = f"{p}dist/~"    # vite/CRA output only
            build_block["cache"] = f"{p}node_modules"
            if svc.env:
                build_block["envVariables"] = dict(svc.env)  # baked at build time
            run_block = {"base": "static"}
        elif is_python:
            # official Zerops python pattern: deps install at runtime prepare
            build_block["deployFiles"] = f"{src}/~" if src else "./"
            build_block["addToRunPrepare"] = [f"{p}requirements.txt"]
            run_block = {
                "base": svc.base,
                "prepareCommands": [
                    f"python3 -m pip install --ignore-installed -r {p}requirements.txt"
                ],
            }
            if svc.ports:
                run_block["ports"] = [
                    {"port": pt.port, "httpSupport": pt.http_support} for pt in svc.ports
                ]
            if svc.start:
                run_block["start"] = svc.start
            if svc.env:
                run_block["envVariables"] = dict(svc.env)
        else:
            if svc.build_commands:
                build_block["buildCommands"] = _cd_commands(src, svc.build_commands)
            build_block["deployFiles"] = f"{src}/~" if src else svc.deploy_files
            if is_node:
                build_block["cache"] = f"{p}node_modules"
            run_block = {"base": svc.base}
            if svc.ports:
                run_block["ports"] = [
                    {"port": pt.port, "httpSupport": pt.http_support} for pt in svc.ports
                ]
            if svc.start:
                run_block["start"] = svc.start
            if svc.env:
                run_block["envVariables"] = dict(svc.env)

        setups.append({"setup": svc.hostname, "build": build_block, "run": run_block})

    if not setups:
        # only managed services (db/cache/...) — they have no build/run block;
        # they're declared in the project-import file instead.
        return (
            "# No runtime services in this topology — only managed services\n"
            "# (databases, caches, etc.). Managed services have no zerops.yaml\n"
            "# build/run block; they're declared in zerops-project-import.yml.\n"
            "# Add an app service (or use Repo URL mode) to get build/run config.\n"
            "zerops: []\n"
        )
    return _dump({"zerops": setups})


def _looks_ssr(svc: Service) -> bool:
    """Next/Nuxt/SSR frontends keep a node runtime; plain vite/CRA go static."""
    s = (svc.start or "").lower()
    return any(k in s for k in ("next", "nuxt", "remix", "node server", "ssr"))


def build_import_yaml(topo: Topology) -> str:
    """The project-import config — declares every service in the project."""
    services: List[Dict] = []
    for svc in topo.services:
        stype = svc.type
        if (svc.role == "frontend" and svc.base
                and svc.base.startswith("nodejs") and not _looks_ssr(svc)):
            stype = "static"   # matches the static run base in zerops.yaml
        entry: Dict = {"hostname": svc.hostname, "type": stype}
        if svc.is_managed:
            entry["mode"] = "HA" if svc.ha else "NON_HA"
        if svc.public:
            entry["enableSubdomainAccess"] = True
        services.append(entry)

    return _dump({"project": {"name": topo.project_name}, "services": services})


def build_topology_graph(topo: Topology) -> Dict:
    """A JSON-friendly nodes+edges graph for the frontend diagram (reactflow)."""
    nodes = []
    for svc in topo.services:
        nodes.append(
            {
                "id": svc.hostname,
                "role": svc.role,
                "type": svc.type,
                "public": svc.public,
                "label": svc.hostname,
                "subtitle": svc.type,
            }
        )
    edges = []
    for svc in topo.services:
        for dep in svc.depends_on:
            if topo.by_hostname(dep):
                edges.append({"source": svc.hostname, "target": dep})
    # public traffic -> each public service
    for svc in topo.services:
        if svc.public:
            edges.append({"source": "__public__", "target": svc.hostname, "kind": "public"})
    return {"nodes": nodes, "edges": edges, "project": topo.project_name}


def generate_all(topo: Topology) -> Dict:
    return {
        "zerops_yaml": build_zerops_yaml(topo),
        "import_yaml": build_import_yaml(topo),
        "graph": build_topology_graph(topo),
        "warnings": topo.warnings,
    }
