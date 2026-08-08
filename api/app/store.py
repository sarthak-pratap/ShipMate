"""Persistence for generation history.

Uses Postgres when DB_HOST is set (Zerops), otherwise an in-memory list so the
app runs locally with zero dependencies. Valkey caching is a thin optional layer
on top. Kept deliberately small — swap for SQLAlchemy if the schema grows.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Dict, List

_MEM: List[Dict] = []


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


def save_generation(project_name: str, mode: str, result: Dict, findings: List) -> Dict:
    rec = {
        "id": uuid.uuid4().hex[:12],
        "project_name": project_name,
        "mode": mode,
        "created_at": time.time(),
        "lint_count": len(findings),
    }
    conn = _pg_conn()
    if conn:
        try:
            payload = json.dumps({"result": result, "lint": findings})
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO generations (id, project_name, mode, payload, created_at) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (rec["id"], project_name, mode, payload, rec["created_at"]),
                )
            conn.commit()
            conn.close()
            return rec
        except Exception:
            pass
    _MEM.insert(0, rec)
    del _MEM[50:]
    return rec


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
            return [
                {"id": r[0], "project_name": r[1], "mode": r[2], "created_at": r[3]}
                for r in rows
            ]
        except Exception:
            pass
    return _MEM[:limit]
