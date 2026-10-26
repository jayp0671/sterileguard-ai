"""sg demo: the demo organization (SG-16).

seed-demo creates one demo user per role (plus-addressed team emails, memberships in dental-cs,
TOTP enrolled through the Auth API) and 90 days of simulated history: final plans, approved
actuals and forecasts from the active model. reset-demo deletes the demo department's demo rows
and reseeds them deterministically, so every demo starts from the same state.

Safety: local and staging only; prod needs --allow-prod-demo (decided in SG-34). Only rows this
command created are deleted: the simulated demo dataset, forecasts in the demo window, and plans
for today or later entered during a demo. Real actuals and earlier real plans are never touched.
User passwords and TOTP secrets go to the gitignored ops/secrets/demo-totp.json.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import secrets
import struct
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import typer

from sg_cli import core
from sg_cli.commands.db import db_url

app = typer.Typer(no_args_is_help=True)

DEMO_DEPARTMENT = "00000000-0000-4000-8000-000000000003"  # supabase/seed.sql (dental-cs)
DEMO_TZ = ZoneInfo("America/New_York")
ROLES = ("technician", "supervisor", "dept_admin", "data_steward", "platform_admin")
SECRETS_FILE = Path("ops/secrets/demo-totp.json")
ENV_VARS = {
    "local": ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"),
    "staging": ("SUPABASE_URL_STAGING", "SUPABASE_SERVICE_ROLE_KEY_STAGING"),
    "prod": ("SUPABASE_URL_PROD", "SUPABASE_SERVICE_ROLE_KEY_PROD"),
}


# ---------------------------------------------------------------------------
# TOTP (RFC 6238, the same codes an authenticator app shows)
# ---------------------------------------------------------------------------


def totp(secret: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    counter = struct.pack(">Q", int((at if at is not None else time.time()) // step))
    mac = hmac.new(key, counter, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % 10**digits
    return str(code).zfill(digits)


def plus_address(base: str, role: str) -> str:
    local, _, domain = base.partition("@")
    if not domain:
        raise typer.BadParameter("DEMO_EMAIL_BASE must be an email address")
    return f"{local}+{role.replace('_', '-')}@{domain}"


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def target(env: str, allow_prod: bool) -> dict[str, str]:
    if env not in ENV_VARS:
        raise typer.BadParameter("--env must be local, staging or prod")
    if env == "prod" and not allow_prod:
        raise SystemExit("refusing to seed demo data in prod without --allow-prod-demo (SG-34)")
    url_var, key_var = ENV_VARS[env]
    found = core.require_env(url_var, key_var)
    return {"db": db_url(env), "url": found[url_var].rstrip("/"), "key": found[key_var]}


def load_secrets(root: Path) -> dict[str, Any]:
    path = root / SECRETS_FILE
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return data


def save_secrets(root: Path, data: dict[str, Any]) -> None:
    path = root / SECRETS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Users (Supabase Auth admin API with the service role)
# ---------------------------------------------------------------------------


class Auth:
    def __init__(self, url: str, key: str) -> None:
        import httpx

        self.url = url
        self.client = httpx.Client(timeout=30.0)
        self.admin = {"apikey": key, "Authorization": f"Bearer {key}"}
        self.anon_key = key

    def _ok(self, resp: Any, what: str) -> Any:
        if resp.status_code >= 400:
            raise SystemExit(f"{what} failed ({resp.status_code})")
        return resp.json() if resp.content else None

    def find(self, email: str) -> dict[str, Any] | None:
        page = 1
        while True:
            body = self._ok(
                self.client.get(
                    f"{self.url}/auth/v1/admin/users",
                    params={"page": page, "per_page": 200},
                    headers=self.admin,
                ),
                "list users",
            )
            users = body.get("users", []) if isinstance(body, dict) else []
            for u in users:
                if str(u.get("email", "")).lower() == email.lower():
                    return dict(u)
            if len(users) < 200:
                return None
            page += 1

    def ensure_user(self, email: str, password: str) -> dict[str, Any]:
        user = self.find(email)
        if user is None:
            return dict(
                self._ok(
                    self.client.post(
                        f"{self.url}/auth/v1/admin/users",
                        json={"email": email, "password": password, "email_confirm": True},
                        headers=self.admin,
                    ),
                    f"create {email}",
                )
            )
        self._ok(
            self.client.put(
                f"{self.url}/auth/v1/admin/users/{user['id']}",
                json={"password": password},
                headers=self.admin,
            ),
            f"update {email}",
        )
        return user

    def enroll_totp(self, user: dict[str, Any], email: str, password: str) -> str:
        """Remove old factors, sign in with the password, enroll and verify a new TOTP factor."""
        for factor in user.get("factors") or []:
            self._ok(
                self.client.delete(
                    f"{self.url}/auth/v1/admin/users/{user['id']}/factors/{factor['id']}",
                    headers=self.admin,
                ),
                "remove old factor",
            )
        session = self._ok(
            self.client.post(
                f"{self.url}/auth/v1/token",
                params={"grant_type": "password"},
                json={"email": email, "password": password},
                headers={"apikey": self.anon_key},
            ),
            f"sign in {email}",
        )
        user_h = {"apikey": self.anon_key, "Authorization": f"Bearer {session['access_token']}"}
        factor = self._ok(
            self.client.post(
                f"{self.url}/auth/v1/factors",
                json={"factor_type": "totp", "friendly_name": "demo"},
                headers=user_h,
            ),
            "enroll TOTP",
        )
        secret = str(factor["totp"]["secret"])
        challenge = self._ok(
            self.client.post(
                f"{self.url}/auth/v1/factors/{factor['id']}/challenge", headers=user_h
            ),
            "TOTP challenge",
        )
        self._ok(
            self.client.post(
                f"{self.url}/auth/v1/factors/{factor['id']}/verify",
                json={"challenge_id": challenge["id"], "code": totp(secret)},
                headers=user_h,
            ),
            "TOTP verify",
        )
        return secret


def seed_users(t: dict[str, str], root: Path) -> dict[str, Any]:
    import psycopg

    base = core.require_env("DEMO_EMAIL_BASE")["DEMO_EMAIL_BASE"]
    store = load_secrets(root)
    auth = Auth(t["url"], t["key"])
    with psycopg.connect(t["db"]) as conn:
        for role in ROLES:
            entry = store.get(role) or {}
            email = plus_address(base, role)
            password = entry.get("password") or secrets.token_urlsafe(18) + "aA1!"
            user = auth.ensure_user(email, password)
            verified = [f for f in user.get("factors") or [] if f.get("status") == "verified"]
            secret = entry.get("totp_secret") if verified and entry.get("totp_secret") else None
            if secret is None:
                secret = auth.enroll_totp(user, email, password)
            conn.execute(
                "insert into public.memberships (user_id, department_id, role) values (%s, %s, %s) "
                "on conflict do nothing",
                (user["id"], DEMO_DEPARTMENT, role),
            )
            store[role] = {
                "email": email,
                "password": password,
                "totp_secret": secret,
                "user_id": user["id"],
            }
            save_secrets(root, store)  # after each user, so a failure keeps what worked
        conn.commit()
    return store


# ---------------------------------------------------------------------------
# History and forecasts
# ---------------------------------------------------------------------------


def active_artifact(t: dict[str, str]) -> tuple[str, dict[str, Any]]:
    import httpx
    import psycopg

    from sg_ml.registry import load_artifact

    with psycopg.connect(t["db"]) as conn:
        row = conn.execute(
            "select version, artifact_path from public.model_versions "
            "where status = 'active' and feature_set = 'full'"
        ).fetchone()
    if row is None:
        raise SystemExit("no active full model: run sg ml evaluate, register and activate first")
    resp = httpx.get(
        f"{t['url']}/storage/v1/object/models/{row[1]}",
        headers={"apikey": t["key"], "Authorization": f"Bearer {t['key']}"},
        timeout=120.0,
    )
    if resp.status_code >= 400:
        raise SystemExit(f"could not download {row[1]} ({resp.status_code})")
    return str(row[0]), load_artifact(resp.content)


def reseed_data(
    t: dict[str, str], days: int, today: dt.date, created_by: str | None
) -> dict[str, Any]:
    import psycopg
    from psycopg.types.json import Jsonb

    from sg_data.schema import TIER2_INPUTS, db_columns
    from sg_ml import demo
    from sg_ml.data import CALIBRATED
    from sg_sim.config import load_config

    cfg = load_config(CALIBRATED)
    df = demo.history(cfg, today, DEMO_DEPARTMENT, days)
    version, artifact = active_artifact(t)
    forecasts, drivers = demo.forecasts(df, artifact, version, created_by)
    dataset_id = demo.demo_id("dataset", DEMO_DEPARTMENT)
    start = today - dt.timedelta(days=days)

    plan_cols = list(db_columns("shift_plans"))
    actual_cols = list(db_columns("shift_actuals"))
    plans, actuals = [], []
    for rec in df.to_dict("records"):
        day = rec["date"].date()
        p = {c: rec.get("date" if c == "plan_date" else c) for c in plan_cols}
        p.update(plan_date=day, **{f"{n}__missing": False for n in TIER2_INPUTS})
        p.update(id=demo.demo_id("plan", DEMO_DEPARTMENT, day.isoformat()), status="final")
        plans.append(p)
        a = {c: rec.get("date" if c == "shift_date" else c) for c in actual_cols}
        a.update(shift_date=day, id=demo.demo_id("actual", DEMO_DEPARTMENT, day.isoformat()))
        a.update(status="approved")
        actuals.append(a)

    def insert(cur: Any, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        cols = list(rows[0])
        marks = ", ".join(["%s"] * len(cols))
        sql = f"insert into public.{table} ({', '.join(cols)}) values ({marks})"
        cur.executemany(
            sql,
            [tuple(Jsonb(r[c]) if isinstance(r[c], dict) else r[c] for c in cols) for r in rows],
        )

    with psycopg.connect(t["db"]) as conn, conn.cursor() as cur:
        cur.execute(
            "delete from public.forecasts where department_id = %s and (target_date >= %s "
            "or plan_id in (select id from public.shift_plans where dataset_id = %s))",
            (DEMO_DEPARTMENT, start, dataset_id),
        )
        cur.execute(
            "delete from public.shift_plans where department_id = %s and source = 'real' "
            "and plan_date >= %s",
            (DEMO_DEPARTMENT, today),
        )
        # Deleting the demo dataset cascades to its plans and actuals.
        cur.execute("delete from public.datasets where id = %s", (dataset_id,))
        cur.execute(
            "insert into public.datasets (id, department_id, source, name, row_count, "
            "content_hash, config_hash, seed) "
            "values (%s, %s, 'simulated', 'demo-history', %s, %s, %s, %s)",
            (
                dataset_id,
                DEMO_DEPARTMENT,
                len(df),
                f"demo-{today.isoformat()}",
                cfg.config_hash,
                demo.DEMO_SEED,
            ),
        )
        insert(cur, "shift_plans", plans)
        insert(cur, "shift_actuals", actuals)
        insert(cur, "forecasts", forecasts)
        insert(cur, "forecast_drivers", drivers)
        conn.commit()
    return {**demo.summary(df), "model_version": version, "forecasts": len(forecasts)}


def checksum(t: dict[str, str], days: int, today: dt.date) -> str:
    """Fingerprint of the demo rows, to show a reset reproduces the same state."""
    import psycopg

    start = today - dt.timedelta(days=days)
    with psycopg.connect(t["db"]) as conn:
        row = conn.execute(
            "select md5(string_agg(x, '|' order by x)) from ("
            " select concat_ws(',', id, plan_date, regular_patients, morning_staff_present,"
            "   status) x"
            "   from public.shift_plans where department_id = %(d)s and plan_date >= %(s)s"
            " union all select concat_ws(',', id, shift_date, ot_labor_hours, status)"
            "   from public.shift_actuals where department_id = %(d)s and shift_date >= %(s)s"
            " union all select concat_ws(',', id, target_date, ot_p10, ot_p50, ot_p90,"
            "   burden_class)"
            "   from public.forecasts where department_id = %(d)s and target_date >= %(s)s"
            " union all select concat_ws(',', forecast_id, rank, feature, contribution_hours)"
            "   from public.forecast_drivers fd join public.forecasts f on f.id = fd.forecast_id"
            "   where f.department_id = %(d)s and f.target_date >= %(s)s) t",
            {"d": DEMO_DEPARTMENT, "s": start},
        ).fetchone()
    return str(row[0] if row else "")


def _today(override: str | None) -> dt.date:
    return dt.date.fromisoformat(override) if override else dt.datetime.now(DEMO_TZ).date()


@app.command("seed-demo", help="Demo users (one per role, TOTP) and 90 days of demo history.")
def seed_demo(
    env: str = typer.Option("local", "--env", help="local | staging (prod needs the flag)"),
    allow_prod_demo: bool = typer.Option(False, "--allow-prod-demo"),
    users: bool = typer.Option(True, "--users/--no-users", help="create or refresh demo users"),
    days: int = typer.Option(90, "--days"),
    today: str | None = typer.Option(None, "--today", help="YYYY-MM-DD (default: today, ET)"),
) -> None:
    result = core.Result("demo", "seed-demo")
    t = target(env, allow_prod_demo)
    if core.OPTIONS.dry_run:
        result.add(f"would seed {'users and ' if users else ''}{days} days of demo data on {env}")
        result.finish()
        return
    root = core.repo_root()
    store = seed_users(t, root) if users else load_secrets(root)
    created_by = (store.get("supervisor") or {}).get("user_id")
    data = reseed_data(t, days, _today(today), created_by)
    result.data.update(env=env, users=sorted(store), **data)
    result.add(f"demo users: {', '.join(sorted(store)) or 'none'} (secrets in {SECRETS_FILE})")
    result.add(
        f"{data['days']} demo days {data['first']} to {data['last']}, model {data['model_version']}"
    )
    result.finish()


@app.command("reset-demo", help="Delete demo rows and reseed them deterministically.")
def reset_demo(
    env: str = typer.Option("local", "--env", help="local | staging (prod needs the flag)"),
    allow_prod_demo: bool = typer.Option(False, "--allow-prod-demo"),
    days: int = typer.Option(90, "--days"),
    today: str | None = typer.Option(None, "--today", help="YYYY-MM-DD (default: today, ET)"),
) -> None:
    result = core.Result("demo", "reset-demo")
    t = target(env, allow_prod_demo)
    if core.OPTIONS.dry_run:
        result.add(f"would reset {days} days of demo data on {env}")
        result.finish()
        return
    day = _today(today)
    created_by = (load_secrets(core.repo_root()).get("supervisor") or {}).get("user_id")
    data = reseed_data(t, days, day, created_by)
    fingerprint = checksum(t, days, day)
    result.data.update(env=env, checksum=fingerprint, **data)
    result.add(f"reset {data['days']} demo days on {env}; state checksum {fingerprint}")
    result.finish()
