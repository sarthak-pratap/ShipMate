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
