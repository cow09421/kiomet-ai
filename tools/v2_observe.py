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
from kiomet_ai.v2.observe.extractor import ObservationSession, connect_dedicated
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
        extractor = ObservationSession(pages[0])
        latencies, errors, snapshots, upper_ages = [], [], 0, []
        force_snapshots=0
        tracks={}
        progress_changes=0
        lifecycle_states=set()
        visibility_losses=visibility_gains=0
        previous_towers=None
        source_reads=0
        source_latencies=[]
        start = time.perf_counter()
        next_poll = start
        try:
            with (out / f"snapshots-{run}.jsonl").open("w", encoding="utf8") as stream:
                while time.perf_counter() - start < args.seconds:
                    if args.source_hz:
                        while time.perf_counter()<next_poll:
                            await asyncio.sleep(min(1/args.source_hz,max(0,next_poll-time.perf_counter())))
                            if time.perf_counter()>=next_poll:
                                break
                            source_began=time.perf_counter()
                            try:
                                await extractor.metadata()
                                source_reads+=1
                                source_latencies.append((time.perf_counter()-source_began)*1000)
                            except Exception as exc:
                                errors.append('source metadata: '+str(exc)[:260])
                    else:
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
                        lifecycle_states.add(str(state.lifecycle.value))
                        ids={t.id for t in state.towers}
                        if previous_towers is not None:
                            visibility_losses+=len(previous_towers-ids)
                            visibility_gains+=len(ids-previous_towers)
                        previous_towers=ids
                        force_snapshots+=bool(state.forces.value)
                        for f in state.forces.value or ():
                            if f.id.value:
                                prior=tracks.get(f.id.value)
                                if prior and prior['progress']!=f.progress.value:
                                    progress_changes+=1
                                tracks[f.id.value]={'progress':f.progress.value,'tick':state.tick.value,
                                    'observations':(prior['observations']+1 if prior else 1)}
                        stream.write(json.dumps(asdict(state), ensure_ascii=False) + "\n")
                        if snapshots == 1:
                            (out / "first-raw.json").write_text(json.dumps(raw, indent=2), encoding="utf8")
                            print(json.dumps({"towers": len(state.towers), "player": state.player_id.value,
                                "status": "PARTIAL", "age_ms": state.age_ms(state.received_at_ms),
                                "readiness_gaps": state.readiness_gaps(state.received_at_ms)[:15]}), flush=True)
                    except Exception as exc:
                        if extractor.extractor:
                            lifecycle_states.add(str(extractor.extractor.lifecycle.state))
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
            "source_metadata_reads":source_reads,
            "source_metadata_latency_p95_ms":sorted(source_latencies)[max(0,int(len(source_latencies)*.95)-1)] if source_latencies else None,
            "force_snapshots":force_snapshots,"derived_force_tracks":len(tracks),
            "force_progress_changes":progress_changes,
            "force_tracks_multiple_observations":sum(t['observations']>1 for t in tracks.values()),
            "lifecycle_states":sorted(lifecycle_states),
            "visibility_losses":visibility_losses,"visibility_gains":visibility_gains,
            "document_reacquisitions":extractor.document_reacquisitions,
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
    parser.add_argument('--source-hz',type=int,default=0,help='Separate metadata-only source clock reads between world snapshots')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error("seconds must be 1..600")
    if not 0<=args.source_hz<=100:
        parser.error('source-hz must be 0..100')
    asyncio.run(main(args))
