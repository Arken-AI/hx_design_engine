"""
Run 10 diverse HX design test cases against the running engine.
Polls each to completion and writes a markdown report.

Usage:
    cd /Users/akashnikam/workspace/hx_design_engine
    python test_10_designs.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

ENGINE = "http://localhost:8100"
POLL_INTERVAL = 2       # seconds between status polls
MAX_WAIT = 120          # seconds before giving up
TIMEOUT = 30

# ---------------------------------------------------------------------------
# 10 test cases — diverse fluids, configs, edge cases
# ---------------------------------------------------------------------------

DESIGNS = [
    {
        "id": 1,
        "label": "Crude Oil / Water (baseline)",
        "payload": {
            "raw_request": (
                "Cool crude oil from 180°C to 80°C using cooling water "
                "(25°C to 50°C). Hot side flow 15 kg/s, pressure 8 bar shell, 4 bar tube."
            ),
            "user_id": "test-runner",
        },
    },
    {
        "id": 2,
        "label": "Steam Condenser (steam → water)",
        "payload": {
            "raw_request": (
                "Condense saturated steam at 120°C (outlet 119°C, 5% subcooling) "
                "using cooling water 20°C to 45°C. Steam flow 3 kg/s, 2 bar steam side, 3 bar water side."
            ),
            "user_id": "test-runner",
        },
    },
    {
        "id": 3,
        "label": "Gas Cooler (air → cooling water)",
        "payload": {
            "raw_request": (
                "Cool compressed air from 200°C to 60°C with cooling water 30°C to 55°C. "
                "Air flow 8 kg/s at 10 bar. Water pressure 4 bar."
            ),
            "user_id": "test-runner",
        },
    },
    {
        "id": 4,
        "label": "Lube Oil / Water",
        "payload": {
            "raw_request": (
                "Cool lube oil from 90°C to 55°C using cooling water 20°C to 40°C. "
                "Oil flow 6 kg/s at 6 bar, water flow 12 kg/s at 4 bar."
            ),
            "user_id": "test-runner",
        },
    },
    {
        "id": 5,
        "label": "Ammonia / Brine Refrigerant",
        "payload": {
            "raw_request": (
                "Cool ammonia vapour from 60°C to 30°C using brine (-5°C to 10°C). "
                "Ammonia flow 2 kg/s at 15 bar, brine flow 10 kg/s at 5 bar."
            ),
            "user_id": "test-runner",
        },
    },
    {
        "id": 6,
        "label": "High-Temp Heat Recovery (flue gas → steam)",
        "payload": {
            "raw_request": (
                "Recover heat from flue gas (400°C to 200°C) to generate steam "
                "(feed water 100°C to 180°C). Gas flow 20 kg/s at 1.05 bar, water 5 kg/s at 15 bar."
            ),
            "user_id": "test-runner",
        },
    },
    {
        "id": 7,
        "label": "Glycol / Water (cold climate)",
        "payload": {
            "raw_request": (
                "Heat ethylene glycol from -10°C to 40°C using hot water 80°C to 55°C. "
                "Glycol flow 4 kg/s at 3 bar, water flow 5 kg/s at 4 bar."
            ),
            "user_id": "test-runner",
        },
    },
    {
        "id": 8,
        "label": "Diesel Fuel / Water",
        "payload": {
            "raw_request": (
                "Cool diesel fuel from 120°C to 60°C with cooling water 25°C to 48°C. "
                "Diesel flow 7 kg/s at 5 bar, water flow 14 kg/s at 3.5 bar."
            ),
            "user_id": "test-runner",
        },
    },
    {
        "id": 9,
        "label": "Hydrogen / Nitrogen (gas-gas)",
        "payload": {
            "raw_request": (
                "Cool hydrogen gas from 250°C to 80°C using nitrogen 30°C to 100°C. "
                "Hydrogen 1 kg/s at 50 bar, nitrogen 3 kg/s at 45 bar."
            ),
            "user_id": "test-runner",
        },
    },
    {
        "id": 10,
        "label": "Heavy Fuel Oil / Water (high fouling)",
        "payload": {
            "raw_request": (
                "Cool heavy fuel oil from 150°C to 80°C using seawater 20°C to 40°C. "
                "HFO flow 10 kg/s at 8 bar, seawater flow 20 kg/s at 4 bar."
            ),
            "user_id": "test-runner",
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    design_id: int
    label: str
    session_id: str = ""
    steps_completed: list[int] = field(default_factory=list)
    step_decisions: dict[int, str] = field(default_factory=dict)
    escalated_steps: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    timed_out: bool = False
    final_state: dict = field(default_factory=dict)
    duration_s: float = 0.0

    @property
    def passed(self) -> bool:
        return (
            not self.error
            and not self.timed_out
            and 5 in self.steps_completed
            and not self.escalated_steps
        )


async def start_design(client: httpx.AsyncClient, payload: dict) -> str:
    resp = await client.post(f"{ENGINE}/api/v1/hx/design", json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()["session_id"]


async def poll_status(client: httpx.AsyncClient, session_id: str) -> dict:
    resp = await client.get(
        f"{ENGINE}/api/v1/hx/design/{session_id}/status", timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


async def run_one(design: dict) -> TestResult:
    result = TestResult(design_id=design["id"], label=design["label"])
    t0 = time.monotonic()

    async with httpx.AsyncClient() as client:
        # Start
        try:
            result.session_id = await start_design(client, design["payload"])
        except Exception as e:
            result.error = f"Start failed: {e}"
            result.duration_s = time.monotonic() - t0
            return result

        print(f"  [{design['id']:02d}] Started → {result.session_id}")

        # Poll until done or timeout
        deadline = time.monotonic() + MAX_WAIT
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                status = await poll_status(client, result.session_id)
            except Exception as e:
                result.error = f"Poll failed: {e}"
                break

            current_step = status.get("current_step", 0)
            records = status.get("step_records", []) or []
            waiting = status.get("waiting_for_user", False)
            result.warnings = status.get("warnings", []) or []

            # Extract per-step decisions
            for r in records:
                sid = r.get("step_id")
                dec = r.get("ai_decision", "—")
                if sid:
                    result.step_decisions[sid] = dec
                    if dec == "ESCALATE" and sid not in result.escalated_steps:
                        result.escalated_steps.append(sid)

            result.steps_completed = sorted(result.step_decisions.keys())

            print(
                f"  [{design['id']:02d}] step={current_step}/5  "
                f"completed={result.steps_completed}  waiting={waiting}"
            )

            # Done when step 5 completed and not waiting
            if 5 in result.steps_completed and not waiting:
                result.final_state = status
                break

            # ESCALATED and waiting → treat as failure (no human to respond)
            if waiting and result.escalated_steps:
                result.error = f"Pipeline escalated at step(s) {result.escalated_steps} — waiting for user"
                break

        else:
            result.timed_out = True
            result.error = f"Timed out after {MAX_WAIT}s (completed steps: {result.steps_completed})"

    result.duration_s = time.monotonic() - t0
    return result


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(results: list[TestResult]) -> str:
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]

    lines = [
        "# HX Engine — 10-Design Smoke Test Report",
        f"\n**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Engine:** {ENGINE}",
        f"\n## Summary\n",
        f"| Result | Count |",
        f"|--------|-------|",
        f"| ✅ Passed | {len(passed)} |",
        f"| ❌ Failed | {len(failed)} |",
        f"| Total  | {len(results)} |",
        "",
    ]

    lines += ["\n## Results\n"]
    lines += [
        "| # | Label | Steps Done | Decisions | Warnings | Escalated | Error | Duration |",
        "|---|-------|-----------|-----------|----------|-----------|-------|----------|",
    ]
    for r in results:
        icon = "✅" if r.passed else "❌"
        decisions = ", ".join(
            f"{k}:{v}" for k, v in sorted(r.step_decisions.items())
        ) or "—"
        warnings = f"{len(r.warnings)} warning(s)" if r.warnings else "—"
        escalated = ", ".join(str(s) for s in r.escalated_steps) or "—"
        err = r.error[:60] + "…" if len(r.error) > 60 else (r.error or "—")
        steps_done = "/".join(str(s) for s in r.steps_completed) or "—"
        lines.append(
            f"| {icon} {r.design_id} | {r.label} | {steps_done} | "
            f"{decisions} | {warnings} | {escalated} | {err} | {r.duration_s:.1f}s |"
        )

    # Per-design detail for failures
    if failed:
        lines += ["\n## Failure Details\n"]
        for r in failed:
            lines += [
                f"### Design {r.design_id} — {r.label}",
                f"- **Session:** `{r.session_id}`",
                f"- **Error:** {r.error or '(none)'}",
                f"- **Timed out:** {r.timed_out}",
                f"- **Steps completed:** {r.steps_completed}",
                f"- **Escalated steps:** {r.escalated_steps}",
                f"- **Warnings:** {r.warnings}",
                "",
            ]

    # Warnings summary across all
    all_warnings = [(r.design_id, r.label, w) for r in results for w in r.warnings]
    if all_warnings:
        lines += ["\n## All Warnings\n"]
        for did, label, w in all_warnings:
            lines += [f"- **Design {did}** ({label}): {w}"]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    print(f"Running {len(DESIGNS)} HX designs against {ENGINE}\n")

    results: list[TestResult] = []

    # Run sequentially to avoid overwhelming the engine / Redis
    for design in DESIGNS:
        print(f"\n{'='*60}")
        print(f"Design {design['id']:02d}: {design['label']}")
        print(f"{'='*60}")
        result = await run_one(design)
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"  → {status} in {result.duration_s:.1f}s")

    report = build_report(results)

    report_path = "HX_SMOKE_TEST_REPORT.md"
    with open(report_path, "w") as f:
        f.write(report)

    print(f"\n{'='*60}")
    print(f"Report written to: {report_path}")
    print(f"Passed: {sum(1 for r in results if r.passed)}/{len(results)}")
    print(f"{'='*60}")

    # Also print the table inline
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
