"""Fetch a public GitHub repo's file list + manifest contents — no clone needed.

Uses the GitHub REST API (unauthenticated works for public repos; set
GITHUB_TOKEN to raise rate limits). stdlib-only so it adds zero dependencies.

    files, contents = fetch_github("https://github.com/user/project")

`files` is every blob path in the default branch; `contents` maps manifest
filenames (package.json, requirements.txt, Dockerfile, ...) to their text.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Dict, List, Tuple

# manifests worth reading (checked by basename, any depth)
MANIFESTS = {
    "package.json", "requirements.txt", "pyproject.toml", "go.mod",
    "composer.json", "gemfile", "pom.xml", "cargo.toml", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "procfile", "fly.toml", "render.yaml", ".env.example",
}

_GH_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com[/:]([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$"
)


class RepoFetchError(Exception):
    pass


def parse_github_url(url: str) -> Tuple[str, str]:
    m = _GH_RE.match(url.strip())
    if not m:
        raise RepoFetchError(
            f"'{url}' doesn't look like a GitHub repo URL (expected github.com/owner/repo)."
        )
    return m.group(1), m.group(2)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "shipmate",
        "Accept": "application/vnd.github+json",
        **({"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}
           if os.getenv("GITHUB_TOKEN") else {}),
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def fetch_github(url: str) -> Tuple[List[str], Dict[str, str]]:
    owner, repo = parse_github_url(url)

    # default branch
    try:
        meta = json.loads(_get(f"https://api.github.com/repos/{owner}/{repo}"))
    except Exception as e:  # noqa: BLE001
        raise RepoFetchError(
            f"Could not reach github.com/{owner}/{repo} — is it public? ({e})"
        )
    branch = meta.get("default_branch", "main")

    # full file tree
    tree = json.loads(_get(
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    ))
    files = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]

    # manifest contents (root-level first, then shallow nested)
    contents: Dict[str, str] = {}
    candidates = sorted(
        (p for p in files if p.rsplit("/", 1)[-1].lower() in MANIFESTS),
        key=lambda p: p.count("/"),
    )
    for path in candidates[:20]:  # cap the fetches; keyed by full path
        try:
            raw = _get(
                f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
            )
            if len(raw) < 200_000:
                contents[path] = raw.decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue

    return files, contents
