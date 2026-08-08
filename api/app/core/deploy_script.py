"""Deterministic deploy-script builder (powers the Deploy wizard).

Takes a saved generation payload + the user's answers and produces the exact
shell script for their situation. All logic is explicit — no LLM anywhere:

  options = {
    "project_name": "my-app",          # rename the project
    "target": "new" | "existing",      # project-import vs service-import
    "push": ["api", "web"],            # which runtime services to push
    "ha_db": true,                     # HA mode for database services
    "public": {"api": true}            # override subdomain access per service
  }
"""
from __future__ import annotations

from typing import Dict, List, Optional

import yaml

RUNTIME_ROLES = ("frontend", "api", "worker")


def build_deploy_script(payload: Dict, options: Optional[Dict] = None) -> str:
    options = options or {}
    import_yaml = payload.get("import_yaml") or ""
    zerops_yaml = payload.get("zerops_yaml") or ""
    graph = payload.get("graph") or {}

    doc = yaml.safe_load(import_yaml) or {}
    services = doc.get("services", []) or []

    # --- apply answers to the import document ---
    project_name = options.get("project_name") or (doc.get("project") or {}).get("name") or "my-project"
    doc["project"] = {"name": project_name}

    if options.get("ha_db") is not None:
        for svc in services:
            if "mode" in svc and _is_database(svc.get("type", "")):
                svc["mode"] = "HA" if options["ha_db"] else "NON_HA"

    for host, is_public in (options.get("public") or {}).items():
        for svc in services:
            if svc.get("hostname") == host:
                if is_public:
                    svc["enableSubdomainAccess"] = True
                else:
                    svc.pop("enableSubdomainAccess", None)

    new_import = yaml.dump(doc, sort_keys=False, default_flow_style=False)

    # --- which runtimes to push ---
    runtimes = [n["id"] for n in graph.get("nodes", []) if n.get("role") in RUNTIME_ROLES]
    push = [h for h in (options.get("push") or runtimes) if h in runtimes] or runtimes

    target = options.get("target", "new")
    if target == "existing":
        import_cmd = (
            "# add these services to an EXISTING project (zcli asks which one)\n"
            "zcli project service-import zerops-project-import.yml"
        )
    else:
        import_cmd = (
            "# create the project + all services\n"
            "zcli project project-import zerops-project-import.yml"
        )

    push_block = "\n".join(f"zcli push {h}" for h in push) if push else \
        "# (no runtime services selected — managed services deploy from the import alone)"

    secret_notes = [w for w in (payload.get("warnings") or []) if "envSecrets" in w]
    secrets_block = ""
    if secret_notes:
        secrets_block = "\n# ⚠ SECRETS — set these in the Zerops GUI before the app fully works:\n" + \
            "".join(f"#   {n}\n" for n in secret_notes)

    return f"""# ShipMate → Zerops · deterministic deploy script
# Run from the ROOT of your application's repository (where the source lives),
# with zcli installed and logged in (zcli login <token>).

cat > zerops.yaml <<'ZEOF'
{zerops_yaml.rstrip()}
ZEOF

cat > zerops-project-import.yml <<'IEOF'
{new_import.rstrip()}
IEOF

{import_cmd}

# build & deploy the selected runtime services
{push_block}
{secrets_block}"""


def _is_database(stype: str) -> bool:
    return any(stype.startswith(p) for p in
               ("postgresql", "mariadb", "clickhouse", "keydb", "valkey"))
