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
