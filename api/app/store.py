"""Persistence for generation history + shareable results.

Uses Postgres when DB_HOST is set (Zerops), otherwise an in-memory dict so the
app runs locally with zero dependencies. The full payload (generated YAML,
graph, lint, score) is stored so a saved generation can be re-opened by id via
a shareable link.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Dict, List, Optional

# id -> full record (payload included), newest-first order tracked separately
_MEM: Dict[str, Dict] = {}
_ORDER: List[str] = []


def _pg_conn():
    if not os.getenv("DB_HOST"):
        return None
    try:
        import psycopg
    except ImportError:
        return None
    try:
        conn = psycopg.connect(
            host=os.environ["DB_HOST"],
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME", "shipmate"),
            user=os.getenv("DB_USER", "shipmate"),
            password=os.getenv("DB_PASS", ""),
            connect_timeout=3,
        )
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS generations (
                    id TEXT PRIMARY KEY,
                    project_name TEXT,
                    mode TEXT,
                    payload JSONB,
                    created_at DOUBLE PRECISION
                )"""
            )
        conn.commit()
        return conn
    except Exception:
        return None


def save_generation(project_name: str, mode: str, payload: Dict) -> Dict:
    """Persist a full generation payload; return a short record (with id)."""
    gid = uuid.uuid4().hex[:12]
    created = time.time()
    rec = {"id": gid, "project_name": project_name, "mode": mode,
           "created_at": created, "lint_count": len(payload.get("lint", []) or [])}

    conn = _pg_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO generations (id, project_name, mode, payload, created_at) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (gid, project_name, mode, json.dumps(payload), created),
                )
            conn.commit()
            conn.close()
            return rec
        except Exception:
            pass

    _MEM[gid] = {**rec, "payload": payload}
    _ORDER.insert(0, gid)
    for stale in _ORDER[100:]:
        _MEM.pop(stale, None)
    del _ORDER[100:]
    return rec


def get_generation(gid: str) -> Optional[Dict]:
    """Fetch a saved generation's full payload by id (for shareable links)."""
    conn = _pg_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, project_name, mode, payload, created_at "
                    "FROM generations WHERE id = %s",
                    (gid,),
                )
                row = cur.fetchone()
            conn.close()
            if row:
                payload = row[3] if isinstance(row[3], dict) else json.loads(row[3])
                return {"id": row[0], "project_name": row[1], "mode": row[2],
                        "created_at": row[4], **payload}
        except Exception:
            pass
    rec = _MEM.get(gid)
    if rec:
        return {"id": rec["id"], "project_name": rec["project_name"],
                "mode": rec["mode"], "created_at": rec["created_at"], **rec["payload"]}
    return None


def recent(limit: int = 20) -> List[Dict]:
    conn = _pg_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, project_name, mode, created_at FROM generations "
                    "ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
            conn.close()
            return [{"id": r[0], "project_name": r[1], "mode": r[2], "created_at": r[3]}
                    for r in rows]
        except Exception:
            pass
    return [{k: _MEM[g][k] for k in ("id", "project_name", "mode", "created_at")}
            for g in _ORDER[:limit]]
