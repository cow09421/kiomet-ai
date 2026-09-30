"""Bounded, read-only M1 sampling of the project's already isolated official page."""
import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kiomet_ai.v2.observe.extractor import ClientExtractor, connect_dedicated
from playwright.async_api import async_playwright


async def main(args):
    out = ROOT / "runtime/research/v2"
    out.mkdir(parents=True, exist_ok=True)
    run = uuid4().hex[:12]
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        pages = [p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/"]
        if len(pages) != 1:
            raise ValueError("dedicated official page absent or ambiguous")
        if args.join:
            button = pages[0].locator("#play_button")
            if await button.is_visible():
                await button.click()
                await button.wait_for(state="hidden", timeout=60000)
                await asyncio.sleep(2)
        extractor = ClientExtractor(pages[0])
        latencies, errors, snapshots, upper_ages = [], [], 0, []
        start = time.perf_counter()
        next_poll = start
        try:
            await extractor.attach()
            with (out / f"snapshots-{run}.jsonl").open("w", encoding="utf8") as stream:
                while time.perf_counter() - start < args.seconds:
                    await asyncio.sleep(max(0, next_poll - time.perf_counter()))
                    began = time.perf_counter()
                    try:
                        state, raw = await extractor.sample()
                        elapsed = (time.perf_counter() - began) * 1000
                        latencies.append(elapsed)
                        snapshots += 1
                        bounds = state.age_bounds_ms(state.received_at_ms)
                        if bounds is not None:
                            upper_ages.append(bounds[1])
                        stream.write(json.dumps(asdict(state), ensure_ascii=False) + "\n")
                        if snapshots == 1:
                            (out / "first-raw.json").write_text(json.dumps(raw, indent=2), encoding="utf8")
                            print(json.dumps({"towers": len(state.towers), "player": state.player_id.value,
                                "status": "PARTIAL", "age_ms": state.age_ms(state.received_at_ms),
                                "readiness_gaps": state.readiness_gaps(state.received_at_ms)[:15]}), flush=True)
                    except Exception as exc:
                        errors.append(str(exc)[:300])
                        if len(errors) == 1:
                            print(json.dumps({"decode_error": errors[-1]}), flush=True)
                    next_poll += 0.2
                    if next_poll < time.perf_counter():
                        next_poll = time.perf_counter()
        finally:
            await extractor.close()
        duration = time.perf_counter() - start
        p95 = sorted(latencies)[max(0, int(len(latencies) * .95) - 1)] if latencies else None
        report = {"status": "PARTIAL", "seconds": duration, "snapshots": snapshots,
            "accepted_poll_hz": snapshots / duration, "poll_latency_p95_ms": p95,
            "authoritative_update_age_p95_ms": None, "independent_ui_comparisons": 0,
            "derived_update_age_upper_p95_ms": sorted(upper_ages)[max(0,int(len(upper_ages)*.95)-1)] if upper_ages else None,
            "bounded_age_snapshots":len(upper_ages),
            "error_count": len(errors), "errors": errors[:5],
            "snapshot_file": f"snapshots-{run}.jsonl",
            "note": "Poll latency is not game-state age. Root adapter is research candidate."}
        (out / "sampling-report.json").write_text(json.dumps(report, indent=2), encoding="utf8")
        (out / f"sampling-{run}.json").write_text(json.dumps(report, indent=2), encoding="utf8")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--join", action="store_true", help="Use only official Play/Play Again UI")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error("seconds must be 1..600")
    asyncio.run(main(args))
