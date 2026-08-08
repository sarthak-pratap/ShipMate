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


def _dump(data) -> str:
    return yaml.dump(
        data,
        Dumper=_IndentDumper,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )


def build_zerops_yaml(topo: Topology) -> str:
    """The `zerops:` config — one entry per runtime service."""
    setups: List[Dict] = []
    for svc in topo.runtimes():
        build_block: Dict = {"base": svc.base}
        if svc.build_commands:
            build_block["buildCommands"] = list(svc.build_commands)
        build_block["deployFiles"] = svc.deploy_files
        if svc.base and svc.base.startswith("python"):
            build_block["cache"] = "~/.cache/pip"
        elif svc.base and svc.base.startswith("nodejs"):
            build_block["cache"] = "node_modules"

        run_block: Dict = {"base": svc.base}
        if svc.ports:
            run_block["ports"] = [
                {"port": p.port, "httpSupport": p.http_support} for p in svc.ports
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


def build_import_yaml(topo: Topology) -> str:
    """The project-import config — declares every service in the project."""
    services: List[Dict] = []
    for svc in topo.services:
        entry: Dict = {"hostname": svc.hostname, "type": svc.type}
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
