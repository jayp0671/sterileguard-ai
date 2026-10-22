"""Schema-to-database drift test (SG-08). Needs the local Supabase stack (sg dev or
supabase start); skipped when it is not reachable. Never points at a hosted database."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

from sg_data import schema

psycopg = pytest.importorskip("psycopg")

LOCAL_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
NON_SCHEMA = {
    "id",
    "status",
    "created_at",
    "updated_at",
    "updated_by",
    "submitted_by",
    "approved_by",
    "approved_at",
}


def _connect() -> psycopg.Connection:
    url = os.environ.get("SUPABASE_DB_URL") or LOCAL_URL
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost"}:
        pytest.skip("drift test only runs against the local stack")
    try:
        return psycopg.connect(url, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local Supabase is not running")


@pytest.mark.integration
@pytest.mark.parametrize("table", ["shift_plans", "shift_actuals"])
def test_schema_matches_database(table: str) -> None:
    with _connect() as conn:
        rows = conn.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema = 'public' and table_name = %s",
            (table,),
        ).fetchall()
    actual = {name: dtype for name, dtype in rows if name not in NON_SCHEMA}
    assert actual == schema.db_columns(table)  # type: ignore[arg-type]
