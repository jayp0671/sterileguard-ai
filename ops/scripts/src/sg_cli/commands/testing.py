"""sg test: one entry point per test layer. Every run writes JUnit XML and a JSON summary
(ops/reports/test/latest.json) that sg memory sync reads."""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from sg_cli import core

app = typer.Typer(no_args_is_help=True)

PY_MEMBERS = {
    "apps/api": "apps/api/tests",
    "packages/data": "packages/data/tests",
    "packages/sim": "packages/sim/tests",
    "packages/ml": "packages/ml/tests",
    "packages/agents": "packages/agents/tests",
    "ops/scripts": "ops/scripts/tests",
}
JS_PACKAGES = {"apps/web": "@sg/web", "packages/contracts": "@sg/contracts"}


def report_dir() -> Path:
    path = core.repo_root() / "ops" / "reports" / "test"
    path.mkdir(parents=True, exist_ok=True)
    return path


def junit_counts(path: Path) -> dict[str, int]:
    """Sum tests, failures+errors and skipped across every <testsuite> in a JUnit file."""
    if not path.exists():
        return {"passed": 0, "failed": 0, "skipped": 0}
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
    tests = failed = skipped = 0
    for s in suites:
        tests += int(s.get("tests", 0))
        failed += int(s.get("failures", 0)) + int(s.get("errors", 0))
        skipped += int(s.get("skipped", 0))
    return {"passed": tests - failed - skipped, "failed": failed, "skipped": skipped}


def record(
    suite: str, counts: dict[str, int], duration_s: float, now: datetime | None = None
) -> None:
    """Upsert one suite's summary into latest.json (keyed by suite name)."""
    path = report_dir() / "latest.json"
    data: dict[str, Any] = {"suites": []}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    code, sha = core.capture(["git", "rev-parse", "--short", "HEAD"])
    entry = {
        "suite": suite,
        **counts,
        "duration_s": round(duration_s, 2),
        "timestamp": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "commit": sha if code == 0 else "unknown",
    }
    suites = [s for s in data.get("suites", []) if s.get("suite") != suite] + [entry]
    data["suites"] = sorted(suites, key=lambda s: str(s["suite"]))
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _run_suite(result: core.Result, suite: str, cmd: list[str], junit: Path) -> bool:
    result.add(f"- {suite}: {' '.join(cmd)}")
    if core.OPTIONS.dry_run:
        core.run(cmd)
        return True
    junit.unlink(missing_ok=True)
    start = time.perf_counter()
    code = core.run(cmd, check=False)
    counts = junit_counts(junit)
    if code != 0 and counts["failed"] == 0:
        counts["failed"] = 1  # runner crashed before writing results
    record(suite, counts, time.perf_counter() - start)
    result.add(
        f"  {counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped"
    )
    return code == 0


def pytest_suite(result: core.Result, suite: str, paths: list[str], extra: list[str]) -> bool:
    junit = report_dir() / f"junit-{suite}.xml"
    cmd = ["uv", "run", "pytest", *paths, f"--junitxml={junit}", *extra]
    return _run_suite(result, suite, cmd, junit)


def vitest_suite(result: core.Result, suite: str, package: str) -> bool:
    junit = report_dir() / f"junit-{suite}.xml"
    cmd = [
        "pnpm",
        "--filter",
        package,
        "exec",
        "vitest",
        "run",
        "--reporter=default",
        "--reporter=junit",
        f"--outputFile.junit={junit}",
    ]
    return _run_suite(result, suite, cmd, junit)


def run_unit(result: core.Result, python: bool, web: bool, cov: bool, fast: bool = False) -> bool:
    ok = True
    if python:
        extra = ["--cov", "--cov-report=xml:ops/reports/test/coverage-py.xml"] if cov else []
        markers = "not e2e and not integration" + (" and not slow" if fast else "")
        extra += ["-m", markers]
        ok &= pytest_suite(result, "python", list(PY_MEMBERS.values()), extra)
    if web:
        for path, package in JS_PACKAGES.items():
            ok &= vitest_suite(result, f"web-{Path(path).name}", package)
    return ok


@app.command("unit", help="Python (pytest) and web (Vitest) unit tests.")
def unit(
    python_only: bool = typer.Option(False, "--python-only"),
    web_only: bool = typer.Option(False, "--web-only"),
    cov: bool = typer.Option(True, "--cov/--no-cov", help="Collect Python coverage."),
    fast: bool = typer.Option(False, "--fast", help="Skip tests marked slow."),
) -> None:
    result = core.Result("test", "unit")
    result.ok = run_unit(result, python=not web_only, web=not python_only, cov=cov, fast=fast)
    result.finish()


@app.command("api", help="API tests (apps/api).")
def api() -> None:
    result = core.Result("test", "api")
    result.ok = pytest_suite(result, "api", [PY_MEMBERS["apps/api"]], [])
    result.finish()


def changed_paths(base: str) -> list[str]:
    code, out = core.capture(["git", "diff", "--name-only", f"{base}...HEAD"])
    if code != 0:
        code, out = core.capture(["git", "diff", "--name-only", base])
    _, staged = core.capture(["git", "diff", "--name-only", "HEAD"])
    return sorted({*out.splitlines(), *staged.splitlines()} - {""})


def affected_members(paths: list[str]) -> tuple[list[str], bool]:
    """Python members touched by `paths`, and whether shared config forces running everything."""
    shared = {"pyproject.toml", "uv.lock"}
    if any(p in shared for p in paths):
        return list(PY_MEMBERS), True
    return [m for m in PY_MEMBERS if any(p.startswith(m + "/") for p in paths)], False


@app.command("affected", help="Only tests for packages changed since origin/main.")
def affected(base: str = typer.Option("origin/main", "--base")) -> None:
    result = core.Result("test", "affected")
    paths = changed_paths(base)
    members, everything = affected_members(paths)
    result.data["python_members"] = members
    ok = True
    if members:
        reason = " (shared config changed)" if everything else ""
        result.add(f"python members{reason}: {', '.join(members)}")
        ok &= pytest_suite(result, "affected-python", [PY_MEMBERS[m] for m in members], [])
    else:
        result.add("no python members changed")
    ok &= (
        core.run(["pnpm", "exec", "turbo", "run", "test", f"--filter=...[{base}]"], check=False)
        == 0
    )
    result.ok = ok
    result.finish()


def playwright_suite(result: core.Result, suite: str, args: list[str]) -> bool:
    junit = report_dir() / "junit-e2e.xml"
    cmd = ["pnpm", "--filter", "@sg/web", "exec", "playwright", "test", *args]
    ok = _run_suite(result, suite, cmd, junit)
    return ok


@app.command("e2e", help="Playwright end-to-end tests (chromium, firefox, webkit, tablet).")
def e2e(
    project: list[str] = typer.Option([], "--project", help="Repeatable; default all projects."),
    headed: bool = typer.Option(False, "--headed"),
    grep: str = typer.Option("", "--grep"),
) -> None:
    result = core.Result("test", "e2e")
    args = [f"--project={p}" for p in project]
    args += ["--headed"] if headed else []
    args += [f"--grep={grep}"] if grep else []
    result.ok = playwright_suite(result, "e2e", args)
    result.finish()


@app.command("a11y", help="Accessibility checks: Playwright specs tagged @a11y (axe in SG-28).")
def a11y() -> None:
    result = core.Result("test", "a11y")
    result.ok = playwright_suite(
        result, "a11y", ["--project=chromium", "--grep=@a11y", "--pass-with-no-tests"]
    )
    result.finish()


@app.command("visual", help="Visual regression: Playwright specs tagged @visual (SG-31).")
def visual(update: bool = typer.Option(False, "--update", help="Update snapshots.")) -> None:
    result = core.Result("test", "visual")
    args = ["--grep=@visual", "--pass-with-no-tests"] + (["--update-snapshots"] if update else [])
    result.ok = playwright_suite(result, "visual", args)
    result.finish()


@app.command("db", help="pgTAP database tests (supabase/tests); full RLS matrix in SG-12.")
def db() -> None:
    result = core.Result("test", "db")
    start = time.perf_counter()
    code = core.run(["pnpm", "exec", "supabase", "test", "db"], check=False)
    if not core.OPTIONS.dry_run:
        record(
            "db",
            {"passed": int(code == 0), "failed": int(code != 0), "skipped": 0},
            time.perf_counter() - start,
        )
    result.ok = code == 0
    result.finish()


LATER = {
    "load": ("SG-31", "k6 load tests"),
    "security": ("SG-28", "ZAP, gitleaks, Semgrep and audits"),
    "i18n": ("SG-27", "missing keys and pseudo-locale"),
    "agents": ("SG-26", "agent evals with recorded NIM responses"),
}


def _later(name: str, ticket: str, what: str) -> None:
    result = core.Result("test", name)
    result.data.update(implemented=False, ticket=ticket)
    result.add(f"sg test {name} ({what}): not implemented yet, see {ticket}")
    result.finish()


for _name, (_ticket, _what) in LATER.items():
    app.command(_name, help=f"{_what} (built by {_ticket}).")(
        lambda n=_name, t=_ticket, w=_what: _later(n, t, w)
    )


@app.command("all", help="unit + api + db + e2e (chromium). What CI runs on a release.")
def all_() -> None:
    result = core.Result("test", "all")
    ok = run_unit(result, python=True, web=True, cov=True)
    code = core.run(["pnpm", "exec", "supabase", "status"], check=False)
    if code == 0:
        ok &= core.run(["pnpm", "exec", "supabase", "test", "db"], check=False) == 0
    else:
        result.add("- db: skipped (local Supabase not running)")
    ok &= playwright_suite(result, "e2e", ["--project=chromium"])
    result.ok = ok
    result.finish()
