"""sg agents: NVIDIA NIM checks and cassette recording (SG-23).

The key is read from NIM_API_KEY in .env and is never printed. `ping` sends one tiny request
per configured model, so it costs 4 of the free tier's ~40 requests a minute.
"""

from __future__ import annotations

import asyncio
import os

import typer

from sg_cli import core

app = typer.Typer(no_args_is_help=True)


@app.command("ping", help="Confirm each model in ops/prompts/models.yaml answers on our key.")
def ping() -> None:
    from sg_agents.nim import NimClient, NimError, load_config

    result = core.Result("agents", "ping")
    cfg = load_config()
    key = os.environ.get("NIM_API_KEY") or core.env_value("NIM_API_KEY")
    if core.OPTIONS.dry_run:
        for agent, model in cfg.models.items():
            result.add(f"would ping {agent}: {model}")
        result.finish()
        return
    if not key:
        result.ok = False
        result.add("NIM_API_KEY is not set (add it to .env; see ops/runbooks/nim.md)")
        result.finish()
        return
    client = NimClient(cfg, mode="live", api_key=key)

    async def one(agent: str) -> str:
        try:
            out = await client.chat(
                agent,
                "ping",
                [{"role": "user", "content": "Reply with the single word OK."}],
                input_hash="0" * 64,
                max_tokens=5,
            )
        except NimError as exc:
            return f"FAIL ({exc})"
        return f"ok ({out.latency_ms} ms)"

    for agent, model in cfg.models.items():
        status = asyncio.run(one(agent))
        result.ok &= status.startswith("ok")
        result.add(f"- {agent}: {model} -> {status}")
        result.data[agent] = {"model": model, "status": status}
    result.finish()


@app.command("record", help="Re-record the golden cassettes with live NIM answers.")
def record() -> None:
    result = core.Result("agents", "record")
    script = "packages/agents/tests/make_cassettes.py"
    args = ["uv", "run", "python", script, "--live"]
    if not (os.environ.get("NIM_API_KEY") or core.env_value("NIM_API_KEY")):
        result.ok = False
        result.add("NIM_API_KEY is not set; stand-in cassettes stay in place")
        result.finish()
        return
    result.ok = core.run(args, check=False) == 0
    result.add("review the diff of packages/agents/tests/cassettes before committing")
    result.finish()
