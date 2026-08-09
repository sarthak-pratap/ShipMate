"""Tests for Mode 3: docker-compose -> zerops.yaml + import + graph."""
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.core.compose_parser import parse_compose
from app.core.zerops_generator import generate_all, build_zerops_yaml, build_import_yaml

COMPOSE = """
name: taskboard
services:
  web:
    image: node:22
    ports:
      - "3000:3000"
    environment:
      API_URL: http://api:8000
    depends_on:
      - api
  api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      DB_HOST: db
      REDIS_HOST: cache
    depends_on:
      - db
      - cache
  db:
    image: postgres:16
  cache:
    image: redis:7
  worker:
    build: ./worker
    environment:
      DB_HOST: db
"""


def _topo():
    return parse_compose(COMPOSE)


def test_all_services_parsed():
    topo = _topo()
    names = {s.hostname for s in topo.services}
    assert names == {"web", "api", "db", "cache", "worker"}


def test_managed_type_mapping():
    topo = _topo()
    assert topo.by_hostname("db").type == "postgresql@16"
    # redis maps to Zerops' Valkey
    assert topo.by_hostname("cache").type == "valkey@7.2"


def test_roles():
    topo = _topo()
    assert topo.by_hostname("web").role == "frontend"
    assert topo.by_hostname("api").role == "api"
    assert topo.by_hostname("worker").role == "worker"


def test_zerops_yaml_is_valid_and_has_runtimes_only():
    topo = _topo()
    doc = yaml.safe_load(build_zerops_yaml(topo))
    setups = {s["setup"] for s in doc["zerops"]}
    # only runtimes get a zerops.yaml setup block
    assert setups == {"web", "api", "worker"}
    for s in doc["zerops"]:
        assert "base" in s["build"]
        assert "base" in s["run"]


def test_import_yaml_declares_all_services_with_modes():
    topo = _topo()
    doc = yaml.safe_load(build_import_yaml(topo))
    assert doc["project"]["name"] == "taskboard"
    svc = {s["hostname"]: s for s in doc["services"]}
    assert svc["db"]["type"] == "postgresql@16"
    assert svc["db"]["mode"] in ("HA", "NON_HA")
    # public runtimes get subdomain access
    assert svc["web"].get("enableSubdomainAccess") is True


def test_graph_has_public_edge():
    topo = _topo()
    graph = generate_all(topo)["graph"]
    kinds = [e for e in graph["edges"] if e.get("kind") == "public"]
    assert len(kinds) >= 1
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "api" in node_ids and "db" in node_ids


def test_db_port_not_http():
    topo = _topo()
    # postgres has no runtime ports; ensure no http port leaked onto managed svc
    assert topo.by_hostname("db").ports == []


def test_env_interpolation_cleaned():
    """Compose ${VAR} self-refs are dropped; ${VAR:-default} keeps the default;
    cross-service literals stay. This is the fastapi-template footgun."""
    compose = """
services:
  backend:
    image: python:3.12
    ports: ["8000:8000"]
    environment:
      SECRET_KEY: ${SECRET_KEY?Variable not set}
      POSTGRES_SERVER: db
      TAG: ${TAG-latest}
      LOG_LEVEL: ${LOG_LEVEL:-info}
      DSN: postgres://${POSTGRES_USER}@db
      PLAIN: hello
  db:
    image: postgres:16
"""
    topo = parse_compose(compose)
    env = topo.by_hostname("backend").env
    assert "SECRET_KEY" not in env          # ${VAR?...} dropped
    assert "DSN" not in env                 # partial interpolation dropped
    assert env["POSTGRES_SERVER"] == "db"   # cross-service literal kept
    assert env["TAG"] == "latest"           # default extracted
    assert env["LOG_LEVEL"] == "info"       # :- default extracted
    assert env["PLAIN"] == "hello"
    assert any("dropped" in w and "interpolation" in w for w in topo.warnings)
