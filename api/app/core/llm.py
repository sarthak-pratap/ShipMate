"""Prompt mode (Mode 1) — plain English -> Topology, via Azure AI Foundry.

The LLM only produces a *structured service list*; the deterministic generator
still writes the YAML. That keeps the risky part (free-form text) contained and
the trustworthy part (schema-correct YAML) in our own code.

Credentials come from env (never hard-coded):
  AZURE_OPENAI_ENDPOINT   e.g. https://my-resource.openai.azure.com
  AZURE_OPENAI_API_KEY
  AZURE_OPENAI_DEPLOYMENT e.g. gpt-4o
  AZURE_OPENAI_API_VERSION (optional, defaults below)
"""
from __future__ import annotations

import json
import os
from typing import Optional

from .schema import Port, Service, Topology

_SYSTEM = """You are a cloud architecture planner for the Zerops platform.
Given a plain-English app description, output ONLY JSON describing the services.

Schema:
{
  "project_name": "kebab-case-name",
  "services": [
    {
      "hostname": "api",
      "role": "frontend|api|worker|database|cache|storage|broker|search",
      "runtime_base": "python@3.12 | nodejs@22 | go@1 | ...",  // runtimes only
      "managed_type": "postgresql@16 | valkey@7.2 | keydb@6 | mariadb@10.4 | nats@2.10 | kafka@3.9 | elasticsearch@8.16 | qdrant@1.12 | object-storage",  // managed only — ONLY these exist on Zerops (no MongoDB, no RabbitMQ)
      "port": 8000,            // runtimes that serve traffic
      "public": true,          // exposed to the internet
      "start": "uvicorn app.main:app --host 0.0.0.0 --port 8000",
      "depends_on": ["db","cache"]
    }
  ]
}
Rules: use private hostnames (never localhost); databases/caches are managed
types with no runtime_base; keep it minimal but complete. Output JSON only."""


def available() -> bool:
    return bool(
        os.getenv("AZURE_OPENAI_ENDPOINT")
        and os.getenv("AZURE_OPENAI_API_KEY")
        and os.getenv("AZURE_OPENAI_DEPLOYMENT")
    )


def _get_client():
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].strip().strip('"').strip("'")
    api_key = os.environ["AZURE_OPENAI_API_KEY"].strip().strip('"').strip("'")
    
    from urllib.parse import urlparse
    parsed = urlparse(endpoint)
    host = parsed.netloc or parsed.path.split('/')[0]
    scheme = parsed.scheme or "https"
    
    if "services.ai.azure.com" in host:
        from openai import OpenAI
        base_url = f"{scheme}://{host}/openai/v1"
        return OpenAI(
            base_url=base_url,
            api_key=api_key,
            default_headers={"api-key": api_key},
        )
    else:
        from openai import AzureOpenAI
        clean_endpoint = f"{scheme}://{host}"
        return AzureOpenAI(
            azure_endpoint=clean_endpoint,
            api_key=api_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01"),
        )

def topology_from_prompt(prompt: str) -> Topology:
    if not available():
        raise RuntimeError(
            "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT, "
            "AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT."
        )

    client = _get_client()
    resp = client.chat.completions.create(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content
    return topology_from_json(raw)


def topology_from_json(raw: str) -> Topology:
    """Pure parser — also used in tests with canned JSON, no network needed."""
    data = json.loads(raw)
    topo = Topology(project_name=data.get("project_name", "my-project"))
    for item in data.get("services", []):
        role = item.get("role", "api")
        is_managed = role in ("database", "cache", "storage", "broker", "search")
        if is_managed:
            topo.services.append(Service(
                hostname=item["hostname"],
                role=role,
                type=item.get("managed_type", "postgresql@16"),
                depends_on=item.get("depends_on", []) or [],
            ))
        else:
            base = item.get("runtime_base", "nodejs@22")
            port = item.get("port")
            ports = [Port(port=int(port), http_support=True)] if port else []
            topo.services.append(Service(
                hostname=item["hostname"],
                role=role,
                type=base,
                base=base,
                ports=ports,
                start=item.get("start"),
                public=bool(item.get("public")),
                depends_on=item.get("depends_on", []) or [],
                build_commands=_build_for(base),
            ))
    return topo


def _build_for(base: str):
    if base.startswith("python"):
        return ["pip install -r requirements.txt"]
    if base.startswith("nodejs"):
        return ["npm ci", "npm run build"]
    if base.startswith("go"):
        return ["go build -o app ."]
    return []


# ---------------------------------------------------------------------------
# AI gap-filling for repo/compose detection
# ---------------------------------------------------------------------------

_ENHANCE_SYSTEM = """You refine a Zerops topology that a deterministic analyzer
already produced from a real repository. You may ONLY:
  1. FILL gaps — supply a missing run.start, a missing port, or a missing
     runtime base for a service that has none.
  2. ADD a managed service (database/cache/broker/storage/search) or a worker
     that the code clearly needs but the analyzer missed.
Do NOT rename, retype, or overwrite fields the analyzer already set. Be
conservative: only act when the evidence in the summary supports it.

Return ONLY JSON:
{
  "fill": [ {"hostname": "app", "start": "...", "port": 8000, "runtime_base": "python@3.12"} ],
  "add":  [ {"hostname": "cache", "role": "cache", "managed_type": "valkey@7.2",
             "runtime_base": null, "port": null, "public": false, "depends_on": ["app"]} ],
  "notes": ["one short human-readable reason per change"]
}
Omit empty arrays' items. Output JSON only, no prose."""


def enhance_topology(topo: "Topology", repo_summary: str) -> dict:
    """Ask Azure OpenAI to fill gaps in an already-detected topology.

    Returns the raw enhancement dict (see _ENHANCE_SYSTEM). Raises if Azure is
    not configured — callers should guard with available() and handle failures.
    """
    if not available():
        raise RuntimeError("Azure OpenAI is not configured.")
    client = _get_client()
    current = _topo_to_json(topo)
    user = (
        f"Detected topology:\n{json.dumps(current, indent=2)}\n\n"
        f"Repository summary (files + manifest excerpts):\n{repo_summary[:6000]}"
    )
    resp = client.chat.completions.create(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        messages=[
            {"role": "system", "content": _ENHANCE_SYSTEM},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def apply_enhancement(topo: "Topology", data: dict) -> list:
    """Merge an enhancement dict into the topology, conservatively. Pure &
    unit-testable (no network). Returns a list of human-readable notes."""
    from .schema import Port, Service  # local import avoids cycles at load

    notes = []

    # 1. FILL — only touch empty fields on existing services
    for item in data.get("fill", []) or []:
        svc = topo.by_hostname(item.get("hostname", ""))
        if not svc:
            continue
        if not svc.start and item.get("start"):
            svc.start = item["start"]
            notes.append(f"AI: set start for '{svc.hostname}'.")
        if not svc.ports and item.get("port"):
            try:
                svc.ports = [Port(int(item["port"]))]
                notes.append(f"AI: exposed port {item['port']} on '{svc.hostname}'.")
            except (TypeError, ValueError):
                pass
        if not svc.base and item.get("runtime_base"):
            svc.base = svc.type = item["runtime_base"]
            notes.append(f"AI: set base {item['runtime_base']} for '{svc.hostname}'.")

    # 2. ADD — only brand-new hostnames
    for item in data.get("add", []) or []:
        host = item.get("hostname")
        if not host or topo.by_hostname(host):
            continue
        role = item.get("role", "api")
        is_managed = role in ("database", "cache", "storage", "broker", "search")
        if is_managed:
            svc = Service(hostname=host, role=role,
                          type=item.get("managed_type") or "postgresql@16",
                          depends_on=item.get("depends_on", []) or [])
        else:
            base = item.get("runtime_base") or "nodejs@22"
            port = item.get("port")
            svc = Service(
                hostname=host, role=role, type=base, base=base,
                ports=[Port(int(port))] if port else [],
                public=bool(item.get("public")),
                depends_on=item.get("depends_on", []) or [],
                build_commands=_build_for(base),
            )
        topo.services.append(svc)
        # wire any existing service that should depend on a new datastore
        for dep in item.get("depended_by", []) or []:
            d = topo.by_hostname(dep)
            if d and host not in d.depends_on:
                d.depends_on.append(host)
        notes.append(f"AI: added '{host}' ({svc.type}).")

    for n in data.get("notes", []) or []:
        notes.append(f"AI: {n}")
    return notes


def _topo_to_json(topo: "Topology") -> dict:
    return {
        "project_name": topo.project_name,
        "services": [
            {
                "hostname": s.hostname, "role": s.role, "type": s.type,
                "base": s.base, "ports": [p.port for p in s.ports],
                "start": s.start, "public": s.public, "depends_on": s.depends_on,
            }
            for s in topo.services
        ],
    }
