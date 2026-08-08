"""Tests for Mode 2: repo detection, incl. the Dockerfile parser."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.core.detector import detect_from_filelist

DOCKERFILE = """\
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 ROOTCAUSE_TICK_SECONDS=3
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY rootcause ./rootcause
EXPOSE 8099
CMD ["python", "-m", "rootcause.run"]
"""

FILES = [
    "Dockerfile", "requirements.txt", "README.md",
    "rootcause/app.py", "rootcause/run.py",
]
CONTENTS = {
    "Dockerfile": DOCKERFILE,
    "requirements.txt": "fastapi>=0.110\nuvicorn[standard]>=0.29\nrequests>=2.31\n",
}


def test_dockerfile_drives_base_port_start():
    topo = detect_from_filelist(FILES, "rootcause-hydro", CONTENTS)
    app = topo.by_hostname("app")
    assert app.base == "python@3.11"
    assert app.ports[0].port == 8099
    assert app.start == "python -m rootcause.run"
    assert app.env.get("PYTHONUNBUFFERED") == "1"


def test_node_dockerfile_version():
    topo = detect_from_filelist(
        ["Dockerfile", "package.json"],
        "web-app",
        {
            "Dockerfile": 'FROM node:22-alpine\nEXPOSE 3000\nCMD ["npm","start"]',
            "package.json": '{"scripts": {"start": "node server.js"}}',
        },
    )
    app = topo.by_hostname("app")
    assert app.base == "nodejs@22"
    assert app.ports[0].port == 3000
    assert app.start == "npm start"


def test_multistage_dockerfile_uses_last_stage():
    df = "FROM node:22 AS build\nRUN npm ci\nFROM python:3.12\nEXPOSE 8000\nCMD uvicorn app:app"
    topo = detect_from_filelist(["Dockerfile"], "x", {"Dockerfile": df})
    assert topo.by_hostname("app").base == "python@3.12"


def test_compose_in_repo_takes_over():
    compose = """
services:
  api:
    image: python:3.12
    ports: ["8000:8000"]
  db:
    image: postgres:16
"""
    topo = detect_from_filelist(
        ["docker-compose.yml", "api/main.py"], "multi",
        {"docker-compose.yml": compose},
    )
    names = {s.hostname for s in topo.services}
    assert names == {"api", "db"}


def test_dep_scan_adds_managed_services():
    topo = detect_from_filelist(
        ["requirements.txt"], "x",
        {"requirements.txt": "fastapi\nsqlalchemy\npsycopg[binary]\nredis\n"},
    )
    names = {s.hostname for s in topo.services}
    assert "db" in names and "cache" in names


def test_vite_frontend_detected_as_frontend():
    topo = detect_from_filelist(
        ["package.json"], "x",
        {"package.json": '{"scripts":{"dev":"vite"},"devDependencies":{"vite":"^5"}}'},
    )
    assert topo.by_hostname("app").role == "frontend"


def test_monorepo_backend_frontend():
    files = [
        "backend/requirements.txt", "backend/app/main.py",
        "frontend/package.json", "frontend/src/App.jsx",
        "README.md",
    ]
    contents = {
        "backend/requirements.txt": "fastapi\nuvicorn\nsqlmodel\n",
        "frontend/package.json": '{"scripts":{"dev":"vite","build":"vite build"},"devDependencies":{"vite":"^5"}}',
    }
    topo = detect_from_filelist(files, "casemind", contents)
    names = {s.hostname: s for s in topo.services}
    assert "api" in names and "web" in names          # backend->api, frontend->web
    assert names["api"].base.startswith("python")
    assert names["web"].role == "frontend"
    assert "db" in names                               # sqlmodel -> postgres
    assert "api" in names["web"].depends_on            # frontend wired to api


def test_infra_only_compose_merges_with_code():
    # a repo whose root compose is only local-dev infra (db + cache),
    # with the real app split across api/ and web/ dirs
    files = [
        "docker-compose.yml",
        "api/requirements.txt", "api/app/main.py",
        "web/package.json", "web/src/main.jsx",
    ]
    contents = {
        "docker-compose.yml": (
            "services:\n"
            "  db:\n    image: postgres:16\n"
            "  cache:\n    image: redis:7\n"
        ),
        "api/requirements.txt": "fastapi\nuvicorn\n",
        "web/package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"^5"}}',
    }
    topo = detect_from_filelist(files, "shipmate", contents)
    names = {s.hostname: s for s in topo.services}
    # app services from code + managed services from the infra compose
    assert {"api", "web", "db", "cache"} <= set(names)
    assert names["api"].base.startswith("python")
    assert names["web"].role == "frontend"
    # no duplicate db/cache, and api wired to them
    assert sum(1 for s in topo.services if s.role == "database") == 1
    assert "db" in names["api"].depends_on and "cache" in names["api"].depends_on


def test_frontend_generates_static_not_dev_server():
    """A vite frontend must build to static — never run `npm run dev` in prod."""
    import yaml as _yaml
    from app.core.zerops_generator import build_zerops_yaml, build_import_yaml
    topo = detect_from_filelist(
        ["frontend/package.json", "backend/requirements.txt"],
        "x",
        {
            "frontend/package.json": '{"scripts":{"dev":"vite","build":"vite build"},"devDependencies":{"vite":"^5"}}',
            "backend/requirements.txt": "fastapi\nuvicorn\n",
        },
    )
    zy = build_zerops_yaml(topo)
    assert "npm run dev" not in zy
    doc = _yaml.safe_load(zy)
    web = next(s for s in doc["zerops"] if s["setup"] == "web")
    assert web["run"]["base"] == "static"
    assert web["build"]["deployFiles"] == "dist/~"
    imp = _yaml.safe_load(build_import_yaml(topo))
    web_imp = next(s for s in imp["services"] if s["hostname"] == "web")
    assert web_imp["type"] == "static"


def test_worker_gets_worker_start_and_no_ports():
    """Workers run their script (python worker.py), never a copy of the API server."""
    topo = detect_from_filelist(
        ["api/requirements.txt", "worker/requirements.txt", "worker/worker.py"],
        "x",
        {
            "api/requirements.txt": "fastapi\nuvicorn\n",
            "worker/requirements.txt": "redis\n",
        },
    )
    w = topo.by_hostname("worker")
    assert w.start == "python worker.py"
    assert "uvicorn" not in (w.start or "")
    assert w.ports == []


def test_unsupported_managed_images_substituted():
    """mongo/rabbitmq have no managed Zerops service — substitute + warn."""
    from app.core.compose_parser import parse_compose
    topo = parse_compose(
        "services:\n  db:\n    image: mongo:7\n  mq:\n    image: rabbitmq:3\n"
    )
    assert topo.by_hostname("db").type == "postgresql@16"
    assert topo.by_hostname("mq").type == "nats@2.10"
    assert any("MongoDB" in w for w in topo.warnings)
    assert any("RabbitMQ" in w for w in topo.warnings)


def test_env_example_secrets_flagged():
    topo = detect_from_filelist(
        ["requirements.txt", ".env.example"],
        "x",
        {
            "requirements.txt": "fastapi\n",
            ".env.example": "AZURE_OPENAI_API_KEY=xxx\nAZURE_OPENAI_ENDPOINT=https://x\nDEBUG=1\n",
        },
    )
    note = next((w for w in topo.warnings if "envSecrets" in w), "")
    assert "AZURE_OPENAI_API_KEY" in note
    assert "DEBUG" not in note
