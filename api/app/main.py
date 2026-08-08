"""ShipMate API — FastAPI entrypoint.

Endpoints:
  GET  /api/health              liveness (used by Zerops + local checks)
  POST /api/generate            {mode, ...} -> {zerops_yaml, import_yaml, graph, lint, warnings}
  POST /api/lint                {zerops_yaml?} deterministic re-lint of a topology
  GET  /api/history             recent generations (Postgres-backed, in-memory fallback)

The heavy lifting lives in app.core.* — this layer is thin on purpose.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core import llm
from .core.compose_parser import parse_compose
from .core.detector import detect_from_filelist
from .core.linter import lint, rule_count, score as lint_score
from .core.zerops_generator import generate_all
from .models import DeployScriptRequest, GenerateRequest, GenerateResponse
from . import store

app = FastAPI(title="ShipMate API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
@app.get("/api/health")
def health():
    return {"status": "ok", "linter_rules": rule_count(), "llm_ready": llm.available()}


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    enh_contents: dict = {}   # manifests captured for the optional AI-enhance pass
    if req.mode == "compose":
        topo = parse_compose(req.compose or "", req.project_name or "my-project")
    elif req.mode == "repo":
        files, contents = req.files or [], req.file_contents or {}
        name = req.project_name or "detected-project"
        if req.repo_url:  # fetch server-side (public GitHub repos)
            from .core.repo_fetcher import RepoFetchError, fetch_github, parse_github_url
            try:
                files, contents = fetch_github(req.repo_url)
                name = parse_github_url(req.repo_url)[1]
            except RepoFetchError as e:
                return GenerateResponse(error=str(e))
        enh_contents = contents
        topo = detect_from_filelist(files, name, contents)
    elif req.mode == "prompt":
        from .core.prompt_heuristic import topology_from_prompt_offline
        text = (req.prompt or "").strip()
        if not text:
            return GenerateResponse(error="Describe your app first, then hit generate.")
        if llm.available():
            try:
                topo = llm.topology_from_prompt(text)
            except Exception as e:  # noqa: BLE001 — never 500; fall back to keywords
                topo = topology_from_prompt_offline(text)
                topo.warnings.insert(0, f"LLM call failed ({e}); generated offline from keywords.")
        else:
            topo = topology_from_prompt_offline(text)
            topo.warnings.insert(
                0,
                "No Azure OpenAI configured — generated offline from keywords. "
                "Set AZURE_OPENAI_* for LLM-quality results.",
            )
    else:
        return GenerateResponse(error=f"unknown mode '{req.mode}'")

    # optional AI gap-filling for detected topologies (repo / compose)
    if req.ai_enhance and req.mode in ("repo", "compose"):
        if llm.available():
            try:
                summary = _repo_summary(req.compose, enh_contents, req.repo_url, topo)
                print(f"=== LLM ENHANCE CALL === Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT')!r}", flush=True)
                data = llm.enhance_topology(topo, summary)
                notes = llm.apply_enhancement(topo, data)
                topo.warnings.extend(notes or ["AI enhance: no gaps found."])
            except Exception as e:
                import traceback
                print(f"=== LLM ENHANCE EXCEPTION ===\n{traceback.format_exc()}", flush=True)
                # log it but don't fail the whole request
                topo.warnings.append(f"AI enhance skipped (LLM error: {e}).")
        else:
            topo.warnings.append(
                "AI enhance requested but no Azure OpenAI configured — set AZURE_OPENAI_* to enable it."
            )

    result = generate_all(topo)
    findings = lint(topo)
    sc = lint_score(findings)
    payload = {
        "project_name": topo.project_name,
        "zerops_yaml": result["zerops_yaml"],
        "import_yaml": result["import_yaml"],
        "graph": result["graph"],
        "lint": findings,
        "warnings": result["warnings"],
        "score": sc,
    }
    record = store.save_generation(topo.project_name, req.mode, payload)
    return GenerateResponse(id=record["id"], **payload)


@app.get("/api/generation/{gid}")
def get_generation(gid: str):
    """Fetch a saved generation by id — powers shareable /?g=<id> links."""
    rec = store.get_generation(gid)
    if not rec:
        return GenerateResponse(error="Generation not found or expired.")
    return GenerateResponse(
        id=rec.get("id"),
        project_name=rec.get("project_name"),
        zerops_yaml=rec.get("zerops_yaml"),
        import_yaml=rec.get("import_yaml"),
        graph=rec.get("graph"),
        lint=rec.get("lint"),
        warnings=rec.get("warnings"),
        score=rec.get("score"),
    )


@app.post("/api/deploy-script")
def deploy_script(req: DeployScriptRequest):
    """The Deploy wizard: answers -> a deterministic, situation-specific script."""
    from .core.deploy_script import build_deploy_script
    rec = store.get_generation(req.id)
    if not rec:
        return {"error": "Generation not found or expired — regenerate first."}
    options = {
        "project_name": req.project_name,
        "target": req.target,
        "push": req.push,
        "ha_db": req.ha_db,
        "public": req.public,
    }
    return {"script": build_deploy_script(rec, options)}


def _repo_summary(compose_text, contents, repo_url, topo) -> str:
    """Compact context for the LLM: file list + manifest excerpts."""
    parts = []
    if repo_url:
        parts.append(f"repo: {repo_url}")
    if compose_text:
        parts.append("docker-compose.yml:\n" + compose_text[:3000])
    for name, text in list((contents or {}).items())[:8]:
        parts.append(f"--- {name} ---\n{text[:800]}")
    if not parts:
        parts.append("services: " + ", ".join(s.hostname for s in topo.services))
    return "\n\n".join(parts)


@app.get("/api/history")
def history():
    return {"items": store.recent(limit=20)}
