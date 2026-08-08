"""Tests for offline prompt mode (no LLM / no network)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.core.prompt_heuristic import topology_from_prompt_offline as gen


def _roles(topo):
    return {s.hostname: s for s in topo.services}


def test_realtime_chat():
    t = gen("a realtime chat app with websockets, redis presence and postgres history")
    s = _roles(t)
    assert "api" in s
    assert s["db"].type == "postgresql@16"
    assert s["cache"].type == "valkey@7"          # redis -> valkey
    assert any("realtime" in w.lower() for w in t.warnings)


def test_booking_with_worker():
    t = gen("a booking app with postgres and a nightly reminder worker")
    s = _roles(t)
    assert "worker" in s
    assert s["worker"].depends_on and "db" in s["worker"].depends_on
    assert s["api"].public is True


def test_rag_gets_postgres_and_storage():
    t = gen("a document search tool: uploads to object storage, a worker builds embeddings into postgres")
    s = _roles(t)
    assert "storage" in s and "db" in s and "worker" in s


def test_node_stack_detected():
    t = gen("an express + typescript REST api with mongodb")
    s = _roles(t)
    assert s["api"].base == "nodejs@22"
    assert s["db"].type == "mongodb@7"


def test_frontend_wired_to_api():
    t = gen("a react dashboard with a python api and postgres")
    s = _roles(t)
    assert "web" in s and s["web"].role == "frontend"
    assert "api" in s["web"].depends_on


def test_minimal_prompt_still_yields_api():
    t = gen("a simple url shortener")
    assert t.by_hostname("api") is not None


# --- AI enhancement merge (pure, no network) ---
from app.core.llm import apply_enhancement
from app.core.schema import Port, Service, Topology


def test_apply_enhancement_fills_and_adds():
    topo = Topology(project_name="x", services=[
        Service(hostname="app", role="api", type="python@3.12", base="python@3.12",
                ports=[], start=None),   # gaps: no port, no start
    ])
    data = {
        "fill": [{"hostname": "app", "start": "gunicorn app:app", "port": 8080}],
        "add": [{"hostname": "cache", "role": "cache", "managed_type": "valkey@7",
                 "depended_by": ["app"]}],
        "notes": ["celery in deps implies a broker/cache"],
    }
    notes = apply_enhancement(topo, data)
    app = topo.by_hostname("app")
    assert app.start == "gunicorn app:app"
    assert app.ports[0].port == 8080
    assert topo.by_hostname("cache") is not None
    assert "cache" in app.depends_on          # wired via depended_by
    assert any("celery" in n for n in notes)


def test_apply_enhancement_never_overwrites():
    topo = Topology(project_name="x", services=[
        Service(hostname="app", role="api", type="go@1", base="go@1",
                ports=[Port(9000)], start="./server"),
    ])
    # LLM tries to change good values — must be ignored
    apply_enhancement(topo, {"fill": [{"hostname": "app", "start": "WRONG", "port": 1}]})
    app = topo.by_hostname("app")
    assert app.start == "./server" and app.ports[0].port == 9000


# --- lint score + persistence roundtrip ---
from app.core.linter import score as lint_score
from app import store


def test_score_grades():
    assert lint_score([])["grade"] == "ship it"
    assert lint_score([])["score"] == 10
    warn = [{"severity": "warning"}]
    assert lint_score(warn)["grade"] == "deploys, review"
    err = [{"severity": "error"}, {"severity": "warning"}]
    s = lint_score(err)
    assert s["grade"] == "won't deploy" and s["errors"] == 1 and s["score"] == 6


def test_store_roundtrip_in_memory():
    payload = {"project_name": "demo", "zerops_yaml": "zerops: []",
               "import_yaml": "project: {}", "graph": {"nodes": [], "edges": []},
               "lint": [], "warnings": [], "score": {"score": 10}}
    rec = store.save_generation("demo", "compose", payload)
    got = store.get_generation(rec["id"])
    assert got and got["project_name"] == "demo"
    assert got["zerops_yaml"] == "zerops: []"
    assert store.get_generation("nope") is None
