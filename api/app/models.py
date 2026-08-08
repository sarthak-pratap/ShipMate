from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class GenerateRequest(BaseModel):
    mode: str                              # "compose" | "repo" | "prompt"
    project_name: Optional[str] = None
    # mode=compose
    compose: Optional[str] = None
    # mode=repo
    repo_url: Optional[str] = None
    files: Optional[List[str]] = None
    file_contents: Optional[Dict[str, str]] = None
    # mode=prompt
    prompt: Optional[str] = None
    # optional: use the LLM to fill gaps in a detected topology (repo/compose)
    ai_enhance: Optional[bool] = False


class GenerateResponse(BaseModel):
    id: Optional[str] = None
    project_name: Optional[str] = None
    zerops_yaml: Optional[str] = None
    import_yaml: Optional[str] = None
    graph: Optional[Dict[str, Any]] = None
    lint: Optional[List[Dict[str, Any]]] = None
    warnings: Optional[List[str]] = None
    score: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
