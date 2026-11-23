"""sg compliance: Trust Center checks and the licenses page (SG-25, plan §14).

`check` fails when a legal page is missing or unversioned, security.txt is invalid or expired,
the footer notice is missing, the Terms/Privacy versions in the API and the pages disagree,
any page claims HIPAA compliance, or a table or column name in the schema contains
patient_name, mrn, ssn or dob (migrations always; the live database with --env).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import typer

from sg_cli import core

app = typer.Typer(no_args_is_help=True)

LEGAL = [
    "privacy",
    "terms",
    "hipaa-notice",
    "cookies",
    "accessibility",
    "ai-transparency",
    "security",
    "data-retention",
    "subprocessors",
    "employee-data-notice",
    "licenses",
]
FOOTER = "Academic prototype. Not for clinical use. Do not enter patient information."
FORBIDDEN_NAMES = ("patient_name", "mrn", "ssn", "dob")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CLAIM = re.compile(r"\b(is|are|fully)\s+hipaa[- ]compliant\b|\bhipaa[- ]certified\b", re.I)


def legal_dir(root: Path) -> Path:
    return root / "apps" / "web" / "src" / "content" / "legal" / "en"


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    out: dict[str, str] = {}
    for line in (m.group(1) if m else "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def forbidden(name: str) -> bool:
    """True when a table or column name contains one of the identifier words as a token."""
    low = name.lower()
    if "patient_name" in low:
        return True
    return any(tok in ("mrn", "ssn", "dob") for tok in re.split(r"[^a-z0-9]+", low))


def check_legal(root: Path) -> list[str]:
    problems = []
    for slug in LEGAL:
        path = legal_dir(root) / f"{slug}.md"
        if not path.exists():
            problems.append(f"legal page missing: {slug}")
            continue
        meta = frontmatter(path.read_text(encoding="utf-8"))
        if not SEMVER.match(meta.get("version", "")):
            problems.append(f"{slug}: version frontmatter missing or not semver")
        if not meta.get("title") or not re.match(
            r"^\d{4}-\d{2}-\d{2}$", meta.get("effective_date", "")
        ):
            problems.append(f"{slug}: title or effective_date frontmatter missing")
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CLAIM.search(line) and not re.search(r"\bnot\b", line, re.I):
                problems.append(f"{slug}:{i}: claims HIPAA compliance")
    return problems


def check_security_txt(root: Path, today: dt.date | None = None) -> list[str]:
    path = root / "apps" / "web" / "public" / ".well-known" / "security.txt"
    if not path.exists():
        return ["security.txt missing (apps/web/public/.well-known/security.txt)"]
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            fields[k.strip().lower()] = v.strip()
    problems = [
        f"security.txt: {f} missing" for f in ("contact", "expires", "policy") if f not in fields
    ]
    if "expires" in fields:
        try:
            exp = dt.datetime.fromisoformat(fields["expires"].replace("Z", "+00:00")).date()
        except ValueError:
            problems.append("security.txt: Expires is not an ISO 8601 date")
        else:
            today = today or dt.date.today()
            if exp <= today:
                problems.append("security.txt: Expires is in the past")
            elif exp > today + dt.timedelta(days=366):
                problems.append("security.txt: Expires is more than a year away (RFC 9116)")
    return problems


def check_footer(root: Path) -> list[str]:
    web = root / "apps" / "web" / "src"
    problems = []
    layout = (web / "app" / "layout.tsx").read_text(encoding="utf-8")
    if "<SiteFooter" not in layout:
        problems.append("root layout does not render SiteFooter")
    messages = json.loads((web / "messages" / "en.json").read_text(encoding="utf-8"))
    footer_component = (web / "components" / "compliance" / "site-footer.tsx").read_text(
        encoding="utf-8"
    )
    if messages.get("common", {}).get("footer") != FOOTER or FOOTER not in footer_component:
        problems.append("footer notice text is missing or changed")
    return problems


def check_versions(root: Path) -> list[str]:
    api = (root / "apps" / "api" / "src" / "sg_api" / "routers" / "compliance.py").read_text(
        encoding="utf-8"
    )
    m = re.search(r"POLICY_VERSIONS[^=]*=\s*(\{[^}]*\})", api)
    if not m:
        return ["POLICY_VERSIONS not found in the API"]
    versions = json.loads(m.group(1).replace("'", '"'))
    problems = []
    for policy, version in versions.items():
        page = legal_dir(root) / f"{policy}.md"
        have = (
            frontmatter(page.read_text(encoding="utf-8")).get("version") if page.exists() else None
        )
        if have != version:
            problems.append(f"{policy}: API asks users to accept {version} but the page is {have}")
    return problems


def check_migrations(root: Path) -> list[str]:
    problems = []
    for path in sorted((root / "supabase" / "migrations").glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(
            r"create table\s+(?:public\.)?(\w+)\s*\((.*?)\n\);", text, re.S | re.I
        ):
            names = [m.group(1)] + [
                ln.split()[0]
                for ln in m.group(2).splitlines()
                if ln.strip()
                and not ln.strip().startswith(("--", "constraint", "check", "primary", "unique"))
            ]
            problems += [f"{path.name}: {n}" for n in names if forbidden(n)]
        for m in re.finditer(r"add column\s+(\w+)", text, re.I):
            if forbidden(m.group(1)):
                problems.append(f"{path.name}: {m.group(1)}")
    return [f"identifier-like name in schema: {p}" for p in problems]


def check_database(url: str) -> list[str]:
    import psycopg

    with psycopg.connect(url, connect_timeout=15) as conn:
        rows = conn.execute(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = 'public'"
        ).fetchall()
    bad = {f"{t}.{c}" for t, c in rows if forbidden(t) or forbidden(c)}
    return [f"identifier-like name in the database: {b}" for b in sorted(bad)]


@app.command("check", help="Legal pages, security.txt, footer, policy versions, schema names.")
def check(
    env: str | None = typer.Option(
        None, "--env", help="Also scan the live database: local | staging"
    ),
) -> None:
    root = core.repo_root()
    result = core.Result("compliance", "check")
    problems = (
        check_legal(root) + check_security_txt(root) + check_footer(root) + check_versions(root)
    )
    problems += check_migrations(root)
    if env and not core.OPTIONS.dry_run:
        from sg_cli.commands.db import db_url

        problems += check_database(db_url(env))
    for p in problems:
        result.add(f"- FAIL {p}")
    if not problems:
        result.add(
            f"ok: {len(LEGAL)} legal pages, security.txt, footer, policy versions, schema names"
        )
    result.ok = not problems
    result.data.update(problems=problems)
    result.finish()


def _python_licenses() -> list[dict[str, Any]]:
    from importlib import metadata

    out = []
    for d in metadata.distributions():
        name = d.metadata.get("Name") or ""
        if not name or name.startswith("sg-") or name.startswith("sg_"):
            continue
        lic = d.metadata.get("License-Expression") or d.metadata.get("License") or ""
        if not lic or len(lic) > 60:
            classifiers = [
                c.split("::")[-1].strip()
                for c in d.metadata.get_all("Classifier") or []
                if c.startswith("License ::")
            ]
            lic = ", ".join(classifiers) or (lic[:60] if lic else "see package")
        out.append({"name": name, "version": d.version, "license": lic})
    return sorted({o["name"].lower(): o for o in out}.values(), key=lambda o: o["name"].lower())


def _js_licenses(root: Path) -> list[dict[str, Any]]:
    code, out = core.capture(["pnpm", "licenses", "list", "--prod", "--json"], cwd=root)
    if code != 0:
        return []
    data = json.loads(out)
    rows = []
    for lic, pkgs in data.items():
        for p in pkgs:
            versions = p.get("versions") or [p.get("version", "")]
            rows.append({"name": p["name"], "version": ", ".join(versions), "license": lic})
    return sorted(rows, key=lambda r: r["name"].lower())


@app.command("licenses", help="Regenerate the Trust Center open-source licenses page.")
def licenses() -> None:
    root = core.repo_root()
    result = core.Result("compliance", "licenses")
    page = legal_dir(root) / "licenses.md"
    head = page.read_text(encoding="utf-8").split("\n---\n", 1)[0] + "\n---\n"
    py, js = _python_licenses(), _js_licenses(root)

    def table(rows: list[dict[str, Any]]) -> str:
        lines = ["| Package | Version | License |", "| --- | --- | --- |"]
        lines += [
            f"| {r['name']} | {r['version']} | {str(r['license']).replace('|', '/')} |"
            for r in rows
        ]
        return "\n".join(lines)

    body = (
        "Generated by `sg compliance licenses` from the production dependencies. Each package "
        "keeps its own license; this list is for attribution.\n\n"
        f"## Web app (JavaScript, {len(js)} packages)\n\n{table(js)}\n\n"
        f"## API and tools (Python, {len(py)} packages)\n\n{table(py)}\n"
    )
    if core.OPTIONS.dry_run:
        result.add(
            f"would write {page.relative_to(root)} ({len(js)} JS, {len(py)} Python packages)"
        )
    else:
        page.write_text(head + body, encoding="utf-8", newline="\n")
        result.add(f"wrote {page.relative_to(root)} ({len(js)} JS, {len(py)} Python packages)")
    result.finish()
