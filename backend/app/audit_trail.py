"""Every Buyer Agent decision layer and checkout attempt writes here — the
audit trail viewer reads it back end to end: mandate, each layer's output,
and any failure/recovery."""

from __future__ import annotations

import json


def log_audit(cur, mandate_id: str, layer: str, payload: dict) -> None:
    cur.execute(
        "INSERT INTO audit_trail (mandate_id, layer, payload) VALUES (%s, %s, %s)",
        (mandate_id, layer, json.dumps(payload, default=str)),
    )


def fetch_audit_trail(cur, mandate_id: str) -> list[dict]:
    # Ordered by seq, not created_at: rows logged within one request share a
    # single transaction-start timestamp (Postgres now() semantics), so
    # created_at alone can't order rows from the same request correctly.
    cur.execute(
        "SELECT layer, payload, created_at FROM audit_trail WHERE mandate_id = %s ORDER BY seq ASC",
        (mandate_id,),
    )
    return [
        {"layer": row[0], "payload": row[1], "created_at": row[2].isoformat()}
        for row in cur.fetchall()
    ]
