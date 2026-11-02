"""sg data: the import pipeline from the terminal (SG-21, plan §10.3).

`sg data profile <file>` and `sg data import <file> --department dental-cs` run the same code as
the app. Real files are read from their local path and never copied into the repo; reports
hold column names, entity types and row numbers, never matched text. Without --commit nothing
is written anywhere but the report.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path
from typing import Any

import typer

from sg_cli import core
from sg_cli.commands.db import db_url

app = typer.Typer(no_args_is_help=True)


def _read(path: Path) -> bytes:
    if not path.is_file():
        raise typer.BadParameter(f"{path} is not a file")
    return path.read_bytes()


def _summary(result: core.Result, res: Any) -> None:
    rep = res.parse_report
    where = f", sheet {rep.sheet!r}" if rep.sheet else ""
    result.add(
        f"parsed {rep.rows} rows x {rep.columns} columns ({rep.file_type}{where}, "
        f"header row {rep.header_rows})"
    )
    if res.dropped_columns:
        result.add(f"PHI guard dropped columns: {', '.join(res.dropped_columns)}")
    cells = [f for f in res.phi_findings if f["row"] is not None]
    if cells:
        types = sorted({f["entity_type"] for f in cells})
        result.add(f"PHI guard blocked {len(cells)} cells ({', '.join(types)})")
    for m in res.mapping:
        target = m.field or "(not mapped)"
        how = f" ({m.method}, {m.score:g})" if m.method else ""
        result.add(f"  {m.column} -> {target}{how}")
    for note in res.transform_notes:
        result.add(f"note: {note}")
    result.add(f"valid rows: {res.valid_rows}; errors: {len(res.errors)}")
    for e in res.errors[:20]:
        row = "file" if e["row"] is None else f"row {e['row'] + 1}"
        result.add(f"  {row} {e['column'] or ''}: {e['message']}")


@app.command("profile", help="Parse, PHI-scan, profile and propose a mapping. Writes nothing.")
def profile_cmd(
    file: Path = typer.Argument(..., help="Local CSV or Excel file (never copied)"),
    sheet: str | None = typer.Option(None, "--sheet"),
    week_start: str | None = typer.Option(
        None, "--week-start", help="YYYY-MM-DD for Mon..Fri headers"
    ),
) -> None:
    from sg_data.imports import run

    result = core.Result("data", "profile")
    res = run(
        _read(file),
        file.name,
        sheet=sheet,
        week_start=dt.date.fromisoformat(week_start) if week_start else None,
    )
    _summary(result, res)
    for col in res.profile:
        samples = "" if col["phi"] else f" e.g. {', '.join(col['samples'][:3])}"
        result.add(
            f"  {col['column']}: {col['dtype']}, {col['null_pct']}% empty, "
            f"{col['distinct']} distinct{samples}"
        )
    result.data.update(report=res.report())
    result.finish()


class PostgresBackend:
    """Commit through a direct connection (service level, like sg demo). Triggers audit it."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def committed_job(self, department_id: str, content_hash: str) -> dict[str, Any] | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "select j.id, d.id from public.import_jobs j "
                "left join public.datasets d on d.import_job_id = j.id "
                "where j.department_id = %s and j.content_hash = %s and j.status = 'committed' "
                "order by j.created_at limit 1",
                (department_id, content_hash),
            )
            row = cur.fetchone()
        return {"id": str(row[0]), "dataset_id": row[1] and str(row[1])} if row else None

    def existing_dates(self, department_id: str, dates: list[dt.date]) -> set[dt.date]:
        with self.conn.cursor() as cur:
            cur.execute(
                "select plan_date from public.shift_plans where department_id = %s "
                "and source = 'real' and plan_date = any(%s) "
                "union select shift_date from public.shift_actuals where department_id = %s "
                "and source = 'real' and shift_date = any(%s)",
                (department_id, dates, department_id, dates),
            )
            return {r[0] for r in cur.fetchall()}

    def write(
        self,
        dataset: dict[str, Any],
        plans: list[dict[str, Any]],
        actuals: list[dict[str, Any]],
        overwrite: bool,
    ) -> None:
        with self.conn.cursor() as cur:
            self._insert(cur, "datasets", [dataset], None, False)
            self._insert(cur, "shift_plans", plans, "department_id, plan_date, source", overwrite)
            self._insert(
                cur, "shift_actuals", actuals, "department_id, shift_date, source", overwrite
            )

    @staticmethod
    def _insert(
        cur: Any, table: str, rows: list[dict[str, Any]], conflict: str | None, overwrite: bool
    ) -> None:
        if not rows:
            return
        cols = list(rows[0])
        marks = ", ".join(["%s"] * len(cols))
        sql = f"insert into public.{table} ({', '.join(cols)}) values ({marks})"
        if conflict:
            if overwrite:
                updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "id")
                sql += f" on conflict ({conflict}) do update set {updates}"
            else:
                sql += f" on conflict ({conflict}) do nothing"
        cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows])


@app.command("import", help="Run the import pipeline; --commit loads valid rows as source = real.")
def import_cmd(
    file: Path = typer.Argument(..., help="Local CSV or Excel file (never copied)"),
    department: str = typer.Option(..., "--department", help="Department slug, e.g. dental-cs"),
    env: str = typer.Option("local", "--env", help="local | staging"),
    sheet: str | None = typer.Option(None, "--sheet"),
    week_start: str | None = typer.Option(
        None, "--week-start", help="YYYY-MM-DD for Mon..Fri headers"
    ),
    commit_rows: bool = typer.Option(False, "--commit", help="Write the valid rows"),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Replace existing real days (dept_admin decision; audited)"
    ),
) -> None:
    import psycopg
    from psycopg.types.json import Jsonb

    from sg_data.imports import run
    from sg_data.imports.commit import commit
    from sg_data.imports.mapping import as_dict

    if env not in ("local", "staging"):
        raise typer.BadParameter("--env must be local or staging (never prod)")
    result = core.Result("data", "import")
    data = _read(file)
    with psycopg.connect(db_url(env)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, settings from public.departments where slug = %s", (department,)
            )
            dept = cur.fetchone()
            if dept is None:
                raise typer.BadParameter(f"no department with slug {department!r} on {env}")
            dept_id, settings = str(dept[0]), dict(dept[1] or {})
            cur.execute(
                "select column_signature, mapping from public.mapping_templates "
                "where department_id = %s",
                (dept_id,),
            )
            templates = {r[0]: r[1] for r in cur.fetchall()}
        res = run(
            data,
            file.name,
            settings=settings,
            templates=templates,
            sheet=sheet,
            week_start=dt.date.fromisoformat(week_start) if week_start else None,
        )
        _summary(result, res)
        report = res.report()
        result.data.update(department=department, env=env, report=report)
        if not commit_rows or core.OPTIONS.dry_run:
            result.add("dry run: nothing written (add --commit to load the valid rows)")
            result.finish()
            return
        job_id = str(uuid.uuid4())
        with conn.cursor() as cur:
            cur.execute(
                "insert into public.import_jobs (id, department_id, original_filename, "
                "content_hash, status, parse_report, mapping, validation_report, phi_findings) "
                "values (%s, %s, %s, %s, 'validated', %s, %s, %s, %s)",
                (
                    job_id,
                    dept_id,
                    file.name,
                    res.content_hash,
                    Jsonb(report["parse_report"]),
                    Jsonb(report["mapping"]),
                    Jsonb(report["validation_report"]),
                    Jsonb(report["phi_findings"]),
                ),
            )
        outcome = commit(
            PostgresBackend(conn),
            res.valid,
            department_id=dept_id,
            settings=settings,
            import_job_id=job_id,
            content_hash=res.content_hash,
            filename=file.name,
            overwrite=overwrite,
        )
        with conn.cursor() as cur:
            if outcome.already_committed:
                cur.execute(
                    "update public.import_jobs set status = 'cancelled', rows_committed = 0 "
                    "where id = %s",
                    (job_id,),
                )
            else:
                cur.execute(
                    "update public.import_jobs set status = 'committed', rows_committed = %s "
                    "where id = %s",
                    (outcome.rows_committed, job_id),
                )
                cur.execute(
                    "insert into public.mapping_templates (department_id, column_signature, "
                    "mapping) values (%s, %s, %s) on conflict (department_id, column_signature) "
                    "do update set mapping = excluded.mapping",
                    (dept_id, res.column_signature, Jsonb(as_dict(res.mapping))),
                )
        conn.commit()
    if outcome.already_committed:
        result.add(f"already imported (job {outcome.import_job_id}): nothing changed")
    else:
        result.add(
            f"committed {outcome.plans} plans and {outcome.actuals} actuals "
            f"(job {job_id}, dataset {outcome.dataset_id})"
        )
        if outcome.skipped_dates:
            result.add(f"skipped existing days: {', '.join(outcome.skipped_dates)}")
    result.data.update(commit=json.loads(json.dumps(outcome.to_dict(), default=str)))
    result.finish()
