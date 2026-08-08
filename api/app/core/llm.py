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
      "managed_type": "postgresql@16 | valkey@7 | ...",        // managed only
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


def topology_from_prompt(prompt: str) -> Topology:
    if not available():
        raise RuntimeError(
            "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT, "
            "AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT."
        )
    # imported lazily so the rest of the app runs without the SDK installed
    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01"),
    )
    resp = client.chat.completions.create(
        model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
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
