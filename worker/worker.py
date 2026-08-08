"""ShipMate worker — heavy/slow analysis off the API request path.

Responsibilities (Phase 2+):
  - `git clone` a submitted repo into a temp dir and read its manifest files,
    then hand a file list to app.core.detector.
  - run longer Azure OpenAI calls for prompt mode when a request is queued.

The worker polls a simple job list in Valkey (falling back to a no-op loop so
it boots cleanly even before the queue exists). Kept dependency-light on
purpose; wire it to the API via the private-network cache host.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# make the API's core importable (shared logic, single source of truth)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

MANIFESTS = {
    "package.json", "requirements.txt", "pyproject.toml", "go.mod",
    "composer.json", "Gemfile", "pom.xml", "Cargo.toml", "Dockerfile",
    "docker-compose.yml", "docker-compose.yaml",
}


def analyze_repo(git_url: str) -> dict:
    """Clone shallow, collect a file list + manifest contents, detect topology."""
    from app.core.detector import detect_from_filelist
    from app.core.zerops_generator import generate_all
    from app.core.linter import lint

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["git", "clone", "--depth", "1", git_url, tmp],
            check=True, capture_output=True, timeout=120,
        )
        root = Path(tmp)
        files, contents = [], {}
        for p in root.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(root))
                files.append(rel)
                if p.name in MANIFESTS and p.stat().st_size < 200_000:
                    try:
                        contents[p.name] = p.read_text(errors="ignore")
                    except Exception:
                        pass
        topo = detect_from_filelist(files, project_name=_name_from_url(git_url),
                                    file_contents=contents)
        result = generate_all(topo)
        result["lint"] = lint(topo)
        return result


def _name_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].replace(".git", "") or "repo"


def _cache():
    host = os.getenv("CACHE_HOST")
    if not host:
        return None
    try:
        import redis
        return redis.Redis(host=host, port=int(os.getenv("CACHE_PORT", "6379")),
                           decode_responses=True)
    except Exception:
        return None


def main():
    r = _cache()
    print(f"[worker] started; cache={'connected' if r else 'none (idle loop)'}", flush=True)
    while True:
        if r is not None:
            job = r.lpop("shipmate:jobs")
            if job:
                try:
                    data = json.loads(job)
                    out = analyze_repo(data["git_url"])
                    r.set(f"shipmate:result:{data['id']}", json.dumps(out), ex=3600)
                    print(f"[worker] analyzed {data['git_url']}", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"[worker] job failed: {e}", flush=True)
                continue
        time.sleep(2)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # one-shot local use: python worker.py <git_url>
        print(json.dumps(analyze_repo(sys.argv[1]), indent=2))
    else:
        main()
