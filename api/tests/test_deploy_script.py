"""Tests for the deterministic deploy-script builder (Deploy wizard)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import yaml
from app.core.deploy_script import build_deploy_script

PAYLOAD = {
    "zerops_yaml": "zerops:\n  - setup: api\n    build:\n      base: python@3.12\n",
    "import_yaml": (
        "project:\n  name: demo\n"
        "services:\n"
        "  - hostname: api\n    type: python@3.12\n    enableSubdomainAccess: true\n"
        "  - hostname: web\n    type: static\n    enableSubdomainAccess: true\n"
        "  - hostname: db\n    type: postgresql@16\n    mode: NON_HA\n"
    ),
    "graph": {"nodes": [
        {"id": "api", "role": "api"}, {"id": "web", "role": "frontend"},
        {"id": "db", "role": "database"},
    ]},
    "warnings": ["Secrets found in .env.example (API_KEY) — set these as envSecrets ..."],
}


def _import_doc(script):
    body = script.split("<<'IEOF'")[1].split("IEOF")[0]
    return yaml.safe_load(body)


def test_defaults_push_all_runtimes_new_project():
    s = build_deploy_script(PAYLOAD, {})
    assert "zcli project project-import" in s
    assert "zcli push api" in s and "zcli push web" in s
    assert "zcli push db" not in s               # managed services aren't pushed
    assert "ROOT of your application" in s
    assert "envSecrets" in s                     # secrets warning carried through


def test_rename_and_existing_project():
    s = build_deploy_script(PAYLOAD, {"project_name": "renamed", "target": "existing"})
    assert "zcli project service-import" in s
    assert "project-import zerops" not in s.split("service-import")[0].split("cat >")[-1]
    assert _import_doc(s)["project"]["name"] == "renamed"


def test_push_selection_filtered_to_real_runtimes():
    s = build_deploy_script(PAYLOAD, {"push": ["web", "db", "bogus"]})
    assert "zcli push web" in s
    assert "zcli push db" not in s and "zcli push bogus" not in s
    assert "zcli push api" not in s


def test_ha_toggle_hits_database_only():
    s = build_deploy_script(PAYLOAD, {"ha_db": True})
    doc = _import_doc(s)
    db = next(x for x in doc["services"] if x["hostname"] == "db")
    assert db["mode"] == "HA"


def test_public_override():
    s = build_deploy_script(PAYLOAD, {"public": {"api": False}})
    doc = _import_doc(s)
    api = next(x for x in doc["services"] if x["hostname"] == "api")
    assert "enableSubdomainAccess" not in api
