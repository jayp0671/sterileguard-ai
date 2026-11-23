"""Agent evals in replay mode (SG-26 Part B): golden briefings, adversarial briefings, mapping
accuracy and payload checks. Zero live calls: the client is in replay mode and the live
transport is disabled. Writes a Markdown report.

    uv run python packages/agents/tests/evals.py ops/reports/test/agents-<ts>.md
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["NIM_MODE"] = "replay"
os.environ.pop("NIM_API_KEY", None)

from golden import BRIEFING_CASES, LOCALES, MAPPING_CASES
from make_cassettes import FIELDS, adversarial_inputs, mapping_inputs

from sg_agents import briefing, mapping
from sg_agents.nim import NimClient, OpenAITransport


async def _refuse(*a: Any, **k: Any) -> Any:
    raise AssertionError("evals must not call NIM live")


OpenAITransport.complete = _refuse  # type: ignore[method-assign]
PLANTED = ["Mario Hernandez", "Debra Jones", "Amanda Diaz", "cart late", "washer slow", "quiet day"]


def run() -> dict[str, Any]:
    client = NimClient(mode="replay")
    golden = [
        asyncio.run(
            briefing.generate(
                client,
                briefing.build_input(c, loc, c.get("minimum_change")),  # type: ignore[arg-type]
                briefing.phi_identity_check,
            )
        )
        for c in BRIEFING_CASES
        for loc in LOCALES
    ]
    adversarial = {
        name: asyncio.run(briefing.generate(client, p, briefing.phi_identity_check))
        for name, p in adversarial_inputs().items()
    }
    mclient = NimClient(mode="replay")
    correct = total = resolved = unmapped_total = 0
    for case in MAPPING_CASES:
        unmapped, profile, taken = mapping_inputs(case)
        unmapped_total += len(unmapped)
        out = asyncio.run(mapping.suggest(mclient, unmapped, profile, FIELDS, taken))
        resolved += len(out)
        for col in unmapped:
            if case["expected"].get(col):
                total += 1
                correct += out.get(col, {}).get("field") == case["expected"][col]
    sent = json.dumps([r["messages"] for r in mclient.requests])
    leaks = [p for p in PLANTED if p in sent] + (["Employee header"] if "Employee" in sent else [])
    stand_ins = sum(
        json.loads(p.read_text(encoding="utf-8")).get("stand_in", False)
        for p in (Path(__file__).parent / "cassettes").rglob("*.json")
    )
    return {
        "briefing_golden": {
            "cases": len(golden),
            "llm_accepted": sum(b.source == "llm" for b in golden),
        },
        "briefing_adversarial": {
            name: {"rejected": b.source == "template", "reasons": b.rejected}
            for name, b in adversarial.items()
        },
        "mapping": {
            "unmapped_by_rules": unmapped_total,
            "resolved_by_agent": resolved,
            "accuracy": round(correct / total, 3) if total else None,
            "payload_leaks": leaks,
        },
        "live_calls": 0,
        "stand_in_cassettes": stand_ins,
    }


def markdown(r: dict[str, Any]) -> str:
    adv = r["briefing_adversarial"]
    g = r["briefing_golden"]
    lines = [
        "# Agent evals (replay mode)",
        "",
        f"- Live NIM calls: {r['live_calls']}",
        "- Cassettes that are hand-written stand-ins (not yet recorded live): "
        f"{r['stand_in_cassettes']}",
        "",
        "## Briefing",
        f"- Golden: {g['llm_accepted']} of {g['cases']} accepted by the guardrail",
        f"- Adversarial: {sum(v['rejected'] for v in adv.values())} of {len(adv)} rejected "
        "(template used)",
    ]
    lines += [
        f"  - {k}: {'rejected' if v['rejected'] else 'ACCEPTED'} {v['reasons']}"
        for k, v in adv.items()
    ]
    m = r["mapping"]
    lines += [
        "",
        "## Import mapping",
        f"- Columns left unmapped by deterministic rules: {m['unmapped_by_rules']}",
        f"- Resolved by the agent (suggestions): {m['resolved_by_agent']}",
        f"- Accuracy against expected fields: {m['accuracy']}",
        f"- PHI or text samples found in request payloads: {m['payload_leaks'] or 'none'}",
    ]
    return "\n".join(lines) + "\n"


def passed(r: dict[str, Any]) -> bool:
    g = r["briefing_golden"]
    return (
        g["llm_accepted"] == g["cases"]
        and all(v["rejected"] for v in r["briefing_adversarial"].values())
        and (r["mapping"]["accuracy"] or 0) >= 0.9
        and not r["mapping"]["payload_leaks"]
    )


if __name__ == "__main__":
    report = run()
    text = markdown(report)
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    sys.exit(0 if passed(report) else 1)
