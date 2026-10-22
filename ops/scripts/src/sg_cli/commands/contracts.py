"""sg contracts: OpenAPI spec from the API code, TS types from the spec, drift check."""

from __future__ import annotations

import typer

from sg_cli import core

app = typer.Typer(no_args_is_help=True)

SPEC = "packages/contracts/openapi.json"
TYPES = "packages/contracts/src/schema.d.ts"


def generate(result: core.Result) -> None:
    root = core.repo_root()
    result.add(f"- write {SPEC} from sg_api.openapi")
    if not core.OPTIONS.dry_run:
        from subprocess import run

        uv = core.which("uv") or "uv"
        proc = run(
            [uv, "run", "--package", "sg-api", "python", "-m", "sg_api.openapi"],
            cwd=root,
            capture_output=True,
            check=True,
        )
        (root / SPEC).write_bytes(proc.stdout.replace(b"\r\n", b"\n"))
    result.add(f"- write {TYPES} with openapi-typescript")
    core.run(["pnpm", "--filter", "@sg/contracts", "gen:types"])


@app.command("gen", help="Regenerate openapi.json and the TypeScript types.")
def gen() -> None:
    result = core.Result("contracts", "gen")
    generate(result)
    result.finish()


@app.command("check", help="Regenerate, then fail if the committed contract drifted.")
def check() -> None:
    result = core.Result("contracts", "check")
    generate(result)
    code = core.run(["git", "diff", "--exit-code", "--", SPEC, TYPES], check=False)
    result.ok = code == 0
    result.add("contracts up to date" if result.ok else "DRIFT: run `sg contracts gen` and commit")
    result.finish()
