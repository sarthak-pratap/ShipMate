"""Tests for the misconfig linter and the LLM JSON parser (no network)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.core.linter import lint
from app.core.llm import topology_from_json
from app.core.schema import Port, Service, Topology


def test_flags_missing_start():
    topo = Topology(project_name="x", services=[
        Service(hostname="api", role="api", type="python@3.12", base="python@3.12",
                ports=[Port(8000)], public=True, start=None),
    ])
    rules = {f["rule"] for f in lint(topo)}
    assert "missing-start" in rules


def test_flags_localhost_reference():
    topo = Topology(project_name="x", services=[
        Service(hostname="api", role="api", type="nodejs@22", base="nodejs@22",
                ports=[Port(3000)], public=True, start="npm start",
                env={"DB_URL": "postgres://localhost:5432/app"}),
    ])
    rules = {f["rule"] for f in lint(topo)}
    assert "localhost-ref" in rules


def test_flags_db_referenced_but_not_declared():
    topo = Topology(project_name="x", services=[
        Service(hostname="api", role="api", type="python@3.12", base="python@3.12",
                ports=[Port(8000)], public=True, start="uvicorn app:app",
                env={"DB_HOST": "db"}),
    ])
    rules = {f["rule"] for f in lint(topo)}
    assert "db-not-declared" in rules


def test_hardcoded_secret_flagged_but_placeholder_ok():
    bad = Topology(project_name="x", services=[
        Service(hostname="api", role="api", type="nodejs@22", base="nodejs@22",
                ports=[Port(3000)], public=True, start="npm start",
                env={"API_KEY": "sk-live-abc123"}),
    ])
    good = Topology(project_name="x", services=[
        Service(hostname="api", role="api", type="nodejs@22", base="nodejs@22",
                ports=[Port(3000)], public=True, start="npm start",
                env={"API_KEY": "${API_KEY}"}),
    ])
    assert "hardcoded-secret" in {f["rule"] for f in lint(bad)}
    assert "hardcoded-secret" not in {f["rule"] for f in lint(good)}


def test_clean_topology_has_no_errors():
    topo = Topology(project_name="x", services=[
        Service(hostname="api", role="api", type="python@3.12", base="python@3.12",
                ports=[Port(8000)], public=True, start="uvicorn app.main:app --host 0.0.0.0 --port 8000",
                env={"DB_HOST": "db"}, depends_on=["db"]),
        Service(hostname="db", role="database", type="postgresql@16", ha=True),
    ])
    errors = [f for f in lint(topo) if f["severity"] == "error"]
    assert errors == []


def test_llm_json_parser_builds_topology():
    raw = """{
      "project_name": "notes-app",
      "services": [
        {"hostname":"api","role":"api","runtime_base":"python@3.12","port":8000,"public":true,"start":"uvicorn app.main:app --host 0.0.0.0 --port 8000","depends_on":["db"]},
        {"hostname":"db","role":"database","managed_type":"postgresql@16"}
      ]
    }"""
    topo = topology_from_json(raw)
    assert topo.project_name == "notes-app"
    assert topo.by_hostname("api").public is True
    assert topo.by_hostname("db").is_managed
