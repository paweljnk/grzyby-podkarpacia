"""Połączenie z PostGIS i log importów."""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg

from .config import database_url


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url(), autocommit=False)


class ImportRun:
    """Wpis w meta.import_log; status ustawiany w finish()/fail()."""

    def __init__(self, conn: psycopg.Connection, source_id: str, target: str, area: str | None, params: dict):
        self.conn = conn
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO meta.import_log (source_id, target, area, params) VALUES (%s,%s,%s,%s) RETURNING id",
                (source_id, target, area, json.dumps(params)),
            )
            self.id = cur.fetchone()[0]
        conn.commit()
        self.records = 0
        self.status = "ok"
        self.message: str | None = None

    def _close(self, status: str, message: str | None) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE meta.import_log SET finished_at=now(), status=%s, records=%s, message=%s WHERE id=%s",
                (status, self.records, message, self.id),
            )
        self.conn.commit()

    def set_status(self, status: str, message: str | None = None) -> None:
        """Zmienia status końcowy (np. 'partial'); zapisywany przy wyjściu z import_run."""
        self.status, self.message = status, message


@contextmanager
def import_run(conn, source_id: str, target: str, area: str | None = None, params: dict | None = None) -> Iterator[ImportRun]:
    run = ImportRun(conn, source_id, target, area, params or {})
    try:
        yield run
    except Exception as e:
        conn.rollback()
        from .etl.http import SourceUnavailable  # import lokalny: etl zależy od db
        status = "skipped" if isinstance(e, SourceUnavailable) else "failed"
        run._close(status, f"{e.__class__.__name__}: {e}")
        raise
    else:
        run._close(run.status, run.message)


def migrate() -> list[str]:
    """Stosuje db/init/*.sql (wszystkie idempotentne: IF NOT EXISTS) — dla baz utworzonych starszą wersją."""
    from .config import ROOT
    applied = []
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute("SET client_min_messages = warning")
        for f in sorted((ROOT / "db" / "init").glob("*.sql")):
            conn.execute(f.read_text(encoding="utf-8"))
            applied.append(f.name)
    return applied


def last_import(conn, source_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, status, finished_at, records, area, message FROM meta.import_log "
            "WHERE source_id=%s ORDER BY started_at DESC LIMIT 1",
            (source_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return dict(zip(["id", "status", "finished_at", "records", "area", "message"], row))
