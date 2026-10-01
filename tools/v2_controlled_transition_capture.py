"""Bounded recorder for ordinary, adjacent force launches and their outcomes.

The default mode is a read-only plan. ``--execute`` permits at most six
operator-selected source/destination pairs in one existing official match.
It uses Playwright page mouse input and the ordinary pinned V2 observer only.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import fields, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kiomet_ai.camera import world_to_page
from kiomet_ai.v2.control import control_readiness_gaps
from kiomet_ai.v2.state import Lifecycle, Relation
from kiomet_ai.observe import TOWER_TYPES, TOWER_TYPE_ZH


ALLOWED_UNITS = frozenset(range(6))  # shields through soldiers; no weapons/Ruler.
UNIT_LABELS = {
    0: ("護盾",), 1: ("戰鬥機",), 2: ("直升機", "直昇機"),
    3: ("轟炸機",), 4: ("坦克",), 5: ("士兵",),
    6: ("砲彈",), 7: ("電磁脈衝",), 8: ("核彈",), 9: ("統治者",),
}
TOWER_LABELS = {**TOWER_TYPE_ZH, "雷達": "Radar", "投射器": "Projector"}
MORALE_TOOLTIP = "你的國王就在附近：產量加倍，出發的單位在途中移動更快、作戰更猛"


def state_json(state):
    if is_dataclass(state):
        return {f.name: getattr(state, f.name) for f in fields(state)}
    raise TypeError(type(state).__name__)


def _counts(fact):
    value = getattr(fact, "value", None)
    return None if value is None else dict(value.counts)


def _typed_deployable(tower):
    counts = _counts(tower.deployable)
    return None if counts is None else tuple(sorted((kind, amount) for kind, amount in counts.items() if amount))


def validate_scenario(state, source_id, destination_id):
    """Return a fail-closed reason or the independently observed scenario."""
    if state.lifecycle.value != Lifecycle.IN_MATCH:
        return "lifecycle_not_in_match"
    if not state.match_id.value or not state.player_id.value:
        return "match_or_player_unknown"
    if state.coverage != "PLAYER_VISIBLE_COMPLETE" or state.forces.value is None:
        return "visible_actor_coverage_incomplete"
    towers = {t.id: t for t in state.towers}
    source, destination = towers.get(source_id), towers.get(destination_id)
    if source is None or destination is None:
        return "endpoint_not_currently_visible"
    if source_id == destination_id or destination_id not in (source.neighbors.value or ()):
        return "destination_not_adjacent"
    if source.owner.value != state.player_id.value or source.relation.value != Relation.SELF:
        return "source_not_own"
    if destination.relation.value not in (Relation.SELF, Relation.NEUTRAL):
        return "destination_not_friendly_or_neutral"
    if destination.relation.value == Relation.SELF and destination.owner.value != state.player_id.value:
        return "friendly_destination_owner_unknown"
    if destination.relation.value == Relation.NEUTRAL and destination.owner.value != 0:
        return "neutral_destination_owner_unknown"
    if _counts(destination.units) is None:
        return "destination_typed_inventory_unknown"
    mobile = _counts(source.deployable)
    inventory = _counts(source.units)
    capacity = _counts(source.capacity)
    if mobile is None or inventory is None or capacity is None:
        return "source_typed_inventory_unknown"
    if any(kind not in ALLOWED_UNITS and amount for kind, amount in mobile.items()):
        return "source_contains_unsupported_deployable"
    if not any(mobile.get(kind, 0) for kind in ALLOWED_UNITS):
        return "source_has_no_supported_deployable"
    if inventory.get(9, 0) or mobile.get(9, 0):
        return "source_contains_ruler"
    if any(inventory.get(kind, 0) > capacity.get(kind, 0) for kind in inventory):
        return "source_capacity_overflow"
    if source.delay_ticks.value is None:
        return "source_delay_unknown"
    if source.delay_ticks.value != 0:
        return "source_has_active_delay"
    effects = source.effects.value
    boost = dict(effects).get("MORALE_BOOST") if effects is not None else None
    if type(boost) is not bool:
        return "source_morale_boost_unknown"
    if destination.relation.value == Relation.NEUTRAL:
        dest_counts = _counts(destination.units)
        if dest_counts is None:
            return "neutral_destination_inventory_unknown"
        if any(dest_counts.values()):
            return "neutral_destination_not_empty"
        scenario = "neutral_capture"
    else:
        scenario = "friendly_reinforcement"
    ineligible = ["future_route_unknown", "fuel_cost_unknown"]
    if boost:
        ineligible.append("morale_boosted_combat_speed_unproven")
    return {"scenario": scenario, "scenario_class": "CAPTURE_ONLY" if ineligible else "ELIGIBLE",
            "scenario_ineligible_reasons": ineligible, "morale_boost": boost,
            "match_id": state.match_id.value,
            "source": source, "destination": destination,
            "typed_deployable": tuple(sorted((k, v) for k, v in mobile.items() if v))}


def validate_fresh_intent(state, source_id, destination_id, typed_deployable,
                          selected_tower, now_ms):
    checked = validate_scenario(state, source_id, destination_id)
    if isinstance(checked, str):
        return checked
    if checked["typed_deployable"] != tuple(typed_deployable):
        return "typed_deployable_changed_before_gesture"
    if selected_tower is not None:
        return "selection_not_none_before_force_gesture"
    if checked["source"].supply_line_present.value is not False:
        return "source_supply_line_guard_failed"
    gaps = control_readiness_gaps(state, now_ms)
    if gaps:
        return "control_readiness_gaps:" + ",".join(gaps)
    return checked


def _ui_quantity_evidence(dom, typed_deployable, tower_type, morale_boost):
    """Read only direct inventory rows under the unique selected tower heading."""
    rows = dom.get("rows") if isinstance(dom, dict) else None
    headings = dom.get("headings") if isinstance(dom, dict) else None
    if not isinstance(rows, list) or not isinstance(headings, list) or type(tower_type) is not int or not 0 <= tower_type < len(TOWER_TYPES):
        return None
    target_type = TOWER_TYPES[tower_type]
    heading_matches = [TOWER_LABELS.get(h, h) for h in headings if isinstance(h, str)
                       and TOWER_LABELS.get(h, h) in TOWER_TYPES]
    if heading_matches != [target_type]:
        return None
    seen, morale_notes = {}, []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            return None
        label = row.get("unit") or row.get("title")
        if label == MORALE_TOOLTIP and row["text"].strip() == "士氣高昂":
            morale_notes.append(row)
            continue
        kind = next((k for k, aliases in UNIT_LABELS.items() if label in aliases), None)
        if kind is None or kind in seen:
            return None
        # The normal panel displays N/M; only N is a usable visible count.
        text = row["text"].strip().replace(" ", "")
        if "/" not in text:
            return None
        left, right = text.split("/", 1)
        if not left.isdecimal() or not right.isdecimal():
            return None
        seen[kind] = int(left)
    if (len(morale_notes) > 1 or type(morale_boost) is not bool or
            bool(morale_notes) != morale_boost):
        return None
    typed = dict(typed_deployable)
    expected = {kind: amount for kind, amount in typed.items() if amount}
    # The pinned mobile-inventory rule excludes ordinary-tower shields. The
    # visible row remains recorded but cannot be mistaken for deployable quantity.
    observed_positive = {kind: amount for kind, amount in seen.items() if amount and
                         not (tower_type != 15 and kind == 0)}
    if observed_positive != expected:
        return None
    return {"visible_deployable_counts": expected, "rows": rows,
            "visible_headings": headings, "matched_tower_type": target_type,
            "morale_note": morale_notes, "nested_requirement_rows": dom.get("nested_rows", []),
            "selector": "h2.parentElement > p[title] (only direct rows); nested upgrade requirements excluded",
            "selection_confirmation": "pinned client selected_tower equals source ID; unique matching official h2"}


def _world_signature(state):
    towers = tuple((t.id, t.owner.value, t.units.value) for t in state.towers)
    forces = tuple((f.id.value, f.owner.value, f.source.value, f.destination.value,
                    f.units.value, f.progress.value) for f in (state.forces.value or ()))
    return towers, forces, state.lifecycle.value


def durable_before(stream, record):
    """Persist and flush the intent before the gesture can begin."""
    stream.write(json.dumps(record, default=state_json, ensure_ascii=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def reserve_writer(path, pid, profile, deadline_monotonic_ms):
    token = uuid4().hex
    payload = {"token": token, "pid": pid, "profile": str(profile),
               "deadline_monotonic_ms": deadline_monotonic_ms}
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as stream:
            stream.write(json.dumps(payload) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return token


def release_writer(path, token):
    try:
        current = json.loads(path.read_text(encoding="utf8"))
        if current.get("token") == token:
            path.unlink(missing_ok=True)
    except FileNotFoundError:
        pass


def is_project_headless_browser_process(name, process_args, profile):
    """Match only Chromium's main browser process, not GPU/render children."""
    user_data_dirs = [arg.split("=", 1)[1] for arg in process_args
                      if arg.startswith("--user-data-dir=")]
    return (name.lower().endswith(("chrome.exe", "chromium.exe")) and
            not any(arg.startswith("--type=") for arg in process_args) and
            len(user_data_dirs) == 1 and Path(user_data_dirs[0]).resolve() == Path(profile).resolve() and
            any(arg == "--headless" or arg.startswith("--headless=") for arg in process_args))


def collect_new_force_lineage(states, source_id, destination_id, expected_counts, prior_ids, player_id):
    """Aggregate genuine newly observed tracks across every captured tick."""
    candidates, ambiguous_ids, candidate_ticks, births = {}, set(), {}, {}
    ambiguous_signatures = set()
    for state in states:
        forces = state.forces.value or ()
        signatures = [(f.owner.value, f.source.value, f.destination.value, tuple(f.units.value.counts))
                      for f in forces]
        for signature in signatures:
            if signatures.count(signature) > 1:
                ambiguous_signatures.add(signature)
        for force in forces:
            signature = (force.owner.value, force.source.value, force.destination.value,
                         tuple(force.units.value.counts))
            if force.source.value != source_id or force.destination.value != destination_id:
                continue
            ident = force.id.value
            if force.owner.value != player_id:
                if ident:
                    ambiguous_ids.add(ident)
                continue
            confidence = force.confidence.value
            if (not ident or ident in prior_ids or confidence not in ("NEW_TRACK", "UNIQUE_CONTINUATION")
                    or signature in ambiguous_signatures):
                if ident and (confidence == "AMBIGUOUS" or signature in ambiguous_signatures):
                    ambiguous_ids.add(ident)
                continue
            counts = tuple((kind, amount) for kind, amount in force.units.value.counts if amount)
            if confidence == "NEW_TRACK" and ident not in births:
                births[ident] = {"birth_confidence": confidence,
                    "birth_progress": force.progress.value,
                    "birth_tick": state.tick.value,
                    "birth_quantity_matches_intent": counts == tuple(expected_counts)}
                if counts != tuple(expected_counts):
                    ambiguous_ids.add(ident)
            if counts != tuple(expected_counts):
                continue
            if confidence == "NEW_TRACK" and force.progress.value == 0:
                candidate_ticks.setdefault(ident, state.tick.value)
            candidates[ident] = {"id": ident, "source": source_id, "destination": destination_id,
                "units": force.units.value, "progress": force.progress.value,
                "confidence": confidence, "first_seen_ms": force.first_seen_ms.value,
                "quantity_matches_intent": True,
                **births.get(ident, {}),
                "candidate_application_tick": candidate_ticks.get(ident),
                "candidate_application_tick_basis": (
                    "first post-intent distinct displayed-world tick with unique NEW_TRACK at progress zero; not server application time"
                    if ident in candidate_ticks else None)}
    return [row for ident, row in candidates.items() if ident not in ambiguous_ids]


def force_lineage_credit(rows, supply_line_guard):
    """Credit only one unambiguous own force with the exact intended vector."""
    return (len(rows) == 1 and supply_line_guard and
            rows[0].get("quantity_matches_intent") is True and
            rows[0].get("birth_quantity_matches_intent") is True and
            rows[0].get("birth_confidence") == "NEW_TRACK")


def supply_line_guard_passed(states, source_id, destination_id, friendly_destination):
    for state in states:
        source = next((t for t in state.towers if t.id == source_id), None)
        if source is None or source.supply_line_present.value is not False:
            return False
        if friendly_destination:
            destination = next((t for t in state.towers if t.id == destination_id), None)
            if destination is None or destination.supply_line_present.value is not False:
                return False
    return True


async def capture_distinct_ticks(metadata, sample, initial_tick, deadline, identity,
                                 arrival, *, now=time.monotonic,
                                 sleep=asyncio.sleep, poll_seconds=.1):
    """Poll metadata at 10 Hz until the bound, capturing every distinct tick.

    The stream runs to its fixed seconds bound even after an arrival cue, so all
    subsequent distinct ticks remain part of the trajectory.
    """
    states, errors, last_tick = [], [], initial_tick
    first_arrival = None
    while now() < deadline:
        try:
            meta = await metadata()
            if (meta.get("derived_lifecycle") != "IN_MATCH" or
                    meta.get("derived_match_id") != identity[1] or
                    meta.get("player_id") != identity[2]):
                return states, errors, first_arrival, "identity_or_lifecycle_changed"
            tick = meta.get("tick")
            if type(tick) is int and tick != last_tick:
                state, _raw = await sample()
                if (state.document_id, state.match_id.value, state.player_id.value) != identity:
                    return states, errors, first_arrival, "identity_changed_during_world_sample"
                if state.tick.value != last_tick:
                    last_tick = state.tick.value
                    states.append((now(), state))
                    if first_arrival is None and arrival(state):
                        first_arrival = {"tick": state.tick.value,
                                         "observed_at_monotonic": now(),
                                         "basis": "visible endpoint change and matching force absent"}
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if len(errors) >= 5:
                return states, errors, first_arrival, "repeated_observation_errors"
        remaining = deadline - now()
        if remaining > 0:
            await sleep(min(poll_seconds, remaining))
    return states, errors, first_arrival, "seconds_bound"


async def record_before_gesture(stream, record, gesture):
    """Durably establish the experiment intent, then allow the mouse gesture."""
    durable_before(stream, record)
    return await gesture()


async def _sample_ready(extractor):
    deadline = time.monotonic() + 2
    while True:
        try:
            return await extractor.sample()
        except ValueError as exc:
            if str(exc) != "current visibility cache pending" or time.monotonic() >= deadline:
                raise
            await asyncio.sleep(.01)


async def run(args):
    import atexit
    import psutil
    from kiomet_ai.v2.observe.extractor import ClientExtractor, connect_dedicated
    from playwright.async_api import async_playwright

    out = ROOT / "runtime/research/v2"
    out.mkdir(parents=True, exist_ok=True)
    lease_path = out / "headless-host.json"
    if not lease_path.is_file():
        raise ValueError("owned headless browser lease is absent; connect-only runner will not launch a browser")
    lease = json.loads(lease_path.read_text(encoding="utf8"))
    profile = (ROOT / "runtime/browser-profile").resolve()
    remaining = lease.get("deadline_monotonic_ms", 0) - time.monotonic_ns() // 1_000_000
    if (type(lease.get("pid")) is not int or lease.get("pid") <= 0 or
            Path(lease.get("profile", "")).resolve() != profile or remaining < (args.seconds + 15) * 1000):
        raise ValueError("owned browser lease/profile cannot cover bounded cohort and mouse-release margin")
    try:
        process = psutil.Process(lease["pid"])
        host_args = process.cmdline()
        host_script = (ROOT / "tools/v2_headless_research.py").resolve()
        if (not process.name().lower().startswith(("python", "py")) or
                not any(Path(arg).resolve() == host_script for arg in host_args if arg.lower().endswith(".py"))):
            raise ValueError("headless host lease PID is not the project's v2_headless_research.py process")
        chrome_owners = []
        for child in process.children(recursive=True):
            try:
                child_args = child.cmdline()
                if is_project_headless_browser_process(child.name(), child_args, profile):
                    chrome_owners.append(child.pid)
            except psutil.Error:
                continue
        if len(chrome_owners) != 1:
            raise ValueError("headless host does not have exactly one project-profile Chromium child")
    except (psutil.Error, OSError) as exc:
        raise ValueError("headless host lease PID is not a live, verifiable project process") from exc

    writer_path = out / "controlled-transition-writer.json"
    writer_token = reserve_writer(writer_path, os.getpid(), profile,
                                  time.monotonic_ns() // 1_000_000 + args.seconds * 1000)
    atexit.register(release_writer, writer_path, writer_token)
    run_id = uuid4().hex[:12]
    path = out / f"controlled-transition-{run_id}.jsonl"
    started = time.monotonic()
    source_manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted((ROOT / "src/kiomet_ai/v2").rglob("*"))
                       if p.is_file() and p.suffix in (".py", ".js", ".json")}
    source_manifest[str(Path(__file__).resolve().relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ui_rule = ROOT / "docs/V2_M2A_UI_INPUT_RULE.md"
    if ui_rule.is_file():
        source_manifest[str(ui_rule.relative_to(ROOT))] = hashlib.sha256(ui_rule.read_bytes()).hexdigest()
    launch_rule = ROOT / "docs/V2_M2A_LAUNCH_RULE.md"
    if launch_rule.is_file():
        source_manifest[str(launch_rule.relative_to(ROOT))] = hashlib.sha256(launch_rule.read_bytes()).hexdigest()
    events, errors, exclusions = [], [], []
    try:
        async with async_playwright() as pw:
            browser = await connect_dedicated(pw, ROOT)
            pages = [p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/"]
            if len(pages) != 1:
                raise ValueError("dedicated official page absent or ambiguous")
            page = pages[0]
            ex = ClientExtractor(page)
            mouse_down = False
            try:
                await ex.attach()
                initial, initial_raw = await _sample_ready(ex)
                identity = (initial.document_id, initial.match_id.value, initial.player_id.value)
                view = await page.evaluate("""() => {const c=document.querySelector('canvas'),r=c?.getBoundingClientRect();
                  return c&&r?{w:c.width,h:c.height,cw:r.width,ch:r.height,left:r.left,top:r.top,dpr:devicePixelRatio}:null}""")
                if not view or view["dpr"] != 1 or view["left"] != 0 or view["top"] != 0:
                    raise ValueError("unsupported full-canvas projection")
                if args.source is None or args.destination is None:
                    raise ValueError("supply one observed --source and --destination pair; no automatic target search")
                initial_check = validate_scenario(initial, args.source, args.destination)
                if isinstance(initial_check, str):
                    exclusions.append({"source": args.source, "destination": args.destination,
                                       "reason": initial_check})
                    raise ValueError("requested pair excluded: " + initial_check)
                if not args.execute:
                    with path.open("w", encoding="utf8") as stream:
                        plan = {"kind": "PLAN", "scenario": initial_check["scenario"],
                            "scenario_class": initial_check["scenario_class"],
                            "scenario_ineligible_reasons": initial_check["scenario_ineligible_reasons"],
                            "match_id": initial_check["match_id"], "source": args.source,
                            "destination": args.destination,
                            "typed_deployable": initial_check["typed_deployable"], "input_sent": False}
                        stream.write(json.dumps(plan, ensure_ascii=False) + "\n")
                        stream.flush()
                    events.append(plan)
                else:
                    with path.open("w", encoding="utf8") as stream:
                        checked, before = initial_check, initial
                        source, destination = checked["source"], checked["destination"]
                        if source.supply_line_present.value is not False:
                            raise ValueError("source supply-line presence is not positively false")
                        if destination.relation.value == Relation.SELF and destination.supply_line_present.value is not False:
                            raise ValueError("friendly destination supply-line presence is not positively false")
                        now_ms = time.monotonic_ns() // 1_000_000
                        gaps = control_readiness_gaps(before, now_ms)
                        if gaps:
                            raise ValueError("control readiness gaps: " + ",".join(gaps))
                        prior_force_ids = {f.id.value for f in (before.forces.value or ()) if f.id.value}
                        durable_before(stream, {"kind": "BEFORE_SNAPSHOT", "state": before,
                            "raw_selected_tower": initial_raw.get("selected_tower"),
                            "source_sha256": source_manifest})

                        # Existing pinned ordinary UI probes use this same canvas click and
                        # confirm selection through normal client selected_tower readback.
                        coords_view = view
                        def project(state, raw):
                            sx, sy = world_to_page(*state.position.value, *raw["camera_candidate"],
                                coords_view["w"], coords_view["h"], 1)
                            return sx, sy

                        def safe_point(x, y):
                            return (80 < x < view["cw"] - 160 and 90 < y < view["ch"] - 110)

                        sx, sy = project(source, initial_raw)
                        if not safe_point(sx, sy):
                            raise ValueError("source_outside_safe_canvas")
                        selection = initial_raw.get("selected_tower")
                        if selection != source.id:
                            durable_before(stream, {"kind": "SELECTION_INTENT", "source": source.id,
                                "selected_before": selection, "coordinate": [sx, sy],
                                "basis": "ordinary official canvas selection; no force drag"})
                            await page.mouse.click(sx, sy)
                        selected, selected_raw = await _sample_ready(ex)
                        if (selected.document_id, selected.match_id.value, selected.player_id.value) != identity or selected_raw.get("selected_tower") != source.id:
                            exclusions.append({"reason": "official_selection_not_confirmed"})
                            raise ValueError("official_selection_not_confirmed")
                        selected_source = next(t for t in selected.towers if t.id == source.id)
                        if selected_source.supply_line_present.value is not False:
                            raise ValueError("source supply-line flag changed or became unknown during selection")
                        source_type = TOWER_TYPES[selected_source.tower_type.value]
                        expected_heading = next((label for label, value in TOWER_LABELS.items()
                                                  if value == source_type), None)
                        if expected_heading is None:
                            raise ValueError("source_tower_type_has_no_verified_normal_ui_heading")
                        dom = await page.evaluate("""(expected) => {
                          const headings=[...document.querySelectorAll('h2')].filter(e=>e.getClientRects().length)
                            .map(e=>e.innerText.trim());
                          const matches=[...document.querySelectorAll('h2')].filter(e=>e.getClientRects().length &&
                            e.innerText.trim()===expected);
                          if(matches.length!==1) return {headings,rows:[],nested_rows:[],heading_match_count:matches.length};
                          const panel=matches[0].parentElement;
                          const rows=[...panel.querySelectorAll(':scope > p[title]')].filter(e=>e.getClientRects().length)
                            .map(e=>({unit:e.title,text:e.innerText,visible:true}));
                          const nested_rows=[...panel.querySelectorAll('p[title]')]
                            .filter(e=>e.getClientRects().length && !e.parentElement.isSameNode(panel))
                            .map(e=>({unit:e.title,text:e.innerText,visible:true}));
                          return {headings,rows,nested_rows,heading_match_count:matches.length};
                        }""", expected_heading)
                        if dom.get("heading_match_count") != 1:
                            raise ValueError("selected_source_panel_heading_not_unique")
                        ui = _ui_quantity_evidence(dom, checked["typed_deployable"],
                            selected_source.tower_type.value, checked["morale_boost"])
                        if ui is None:
                            exclusions.append({"reason": "selected_ui_quantity_unknown_ambiguous_or_mismatched", "ui_rows": dom})
                            raise ValueError("selected_ui_quantity_unknown_ambiguous_or_mismatched")
                        if _typed_deployable(selected_source) != checked["typed_deployable"]:
                            raise ValueError("typed_deployable_changed_during_selection")
                        durable_before(stream, {"kind": "SELECTION_CONFIRMED", "source": source.id,
                            "selected_tower": selected_raw["selected_tower"], "ui_evidence": ui,
                            "state": selected})
                        # Clicking the selected source again is the pinned ordinary toggle-to-none.
                        # A drag is permitted only after normal readback proves no source is selected.
                        sx, sy = project(selected_source, selected_raw)
                        if not safe_point(sx, sy):
                            raise ValueError("source_projection_changed_outside_safe_canvas")
                        durable_before(stream, {"kind": "DESELECTION_INTENT", "source": source.id,
                            "selected_before": selected_raw["selected_tower"], "coordinate": [sx, sy],
                            "supply_line_before": selected_source.supply_line_present.value})
                        await page.mouse.click(sx, sy)
                        deselected, deselected_raw = await _sample_ready(ex)
                        if deselected_raw.get("selected_tower") is not None:
                            raise ValueError("ordinary deselection was not confirmed; force gesture withheld")
                        source_now = next((t for t in deselected.towers if t.id == source.id), None)
                        if source_now is None or source_now.supply_line_present.value is not False:
                            raise ValueError("source disappeared or supply-line guard failed after deselection")
                        if _typed_deployable(source_now) != checked["typed_deployable"]:
                            raise ValueError("typed_deployable_changed_during_deselection")
                        durable_before(stream, {"kind": "DESELECTION_CONFIRMED", "source": source.id,
                            "selected_tower": deselected_raw.get("selected_tower"),
                            "supply_line_after": source_now.supply_line_present.value, "state": deselected})

                        # Fresh state, fresh camera, both endpoint hit-tests, and readiness are
                        # checked after deselection and immediately before durable command intent.
                        before, before_raw = await _sample_ready(ex)
                        fresh = validate_fresh_intent(before, source.id, destination.id,
                            checked["typed_deployable"], before_raw.get("selected_tower"),
                            time.monotonic_ns() // 1_000_000)
                        if isinstance(fresh, str):
                            raise ValueError("fresh scenario rejected: " + fresh)
                        if time.monotonic() + 5 >= started + args.seconds:
                            raise ValueError("insufficient bounded time remains for 5-second observation window")
                        view = await page.evaluate("""() => {const c=document.querySelector('canvas'),r=c?.getBoundingClientRect();
                          return c&&r?{w:c.width,h:c.height,cw:r.width,ch:r.height,left:r.left,top:r.top,dpr:devicePixelRatio}:null}""")
                        if not view or view["dpr"] != 1 or view["left"] != 0 or view["top"] != 0:
                            raise ValueError("canvas projection changed immediately before gesture")
                        sx, sy = world_to_page(*fresh["source"].position.value, *before_raw["camera_candidate"],
                            view["w"], view["h"], 1)
                        dx, dy = world_to_page(*fresh["destination"].position.value, *before_raw["camera_candidate"],
                            view["w"], view["h"], 1)
                        if not (safe_point(sx, sy) and safe_point(dx, dy)):
                            raise ValueError("fresh_endpoint_outside_safe_canvas")
                        hit_tests = await page.evaluate("""([[sx,sy],[dx,dy]]) => {
                          const c=document.querySelector('canvas');
                          return {source:document.elementFromPoint(sx,sy)===c,
                            destination:document.elementFromPoint(dx,dy)===c};}""", [[sx, sy], [dx, dy]])
                        if hit_tests != {"source": True, "destination": True}:
                            raise ValueError("fresh_endpoint_canvas_hit_test_failed")
                        before_ids = {f.id.value for f in (before.forces.value or ()) if f.id.value}
                        intent = {"kind": "BEFORE_INTENT", "run_id": run_id, "command_index": 1,
                            "time_monotonic": time.monotonic(), "scenario": fresh["scenario"],
                            "scenario_class": fresh["scenario_class"],
                            "scenario_ineligible_reasons": fresh["scenario_ineligible_reasons"],
                            "QUESTION": ("Does an ordinary manual deploy from this recorded own source create one uniquely observed new force, "
                                "then capture the empty neutral destination or reinforce the friendly destination?"),
                            "BEFORE": {"displayed_tick": before.tick.value,
                                "exact_server_application_tick": "UNKNOWN",
                                "document_id": before.document_id, "match_id": before.match_id.value,
                                "lifecycle": before.lifecycle.value, "source": source.id,
                                "destination": destination.id,
                                "source_owner": fresh["source"].owner.value,
                                "destination_owner": fresh["destination"].owner.value,
                                "typed_deployable": fresh["typed_deployable"],
                                "selected_tower_none_confirmed": True,
                                "source_supply_line_present": fresh["source"].supply_line_present.value,
                                "destination_supply_line_present": fresh["destination"].supply_line_present.value},
                            "ACTION": {"operation": "ordinary_official_ui_manual_deploy_force",
                                "source": source.id, "destination": destination.id,
                                "typed_deployable": fresh["typed_deployable"],
                                "gesture": "canvas mouse drag with source deselected; pinned DeployForce UI branch"},
                            "EXPECTED": {"manual_newborn": {"progress": 0,
                                    "accelerated": fresh["morale_boost"], "fuel": 150,
                                    "basis": "pinned manual DeployForce constructor; acceleration copies source morale"},
                                "first_application_tick": "first post-intent distinct displayed-world tick with unique matching NEW_TRACK at progress zero; server application tick remains UNKNOWN",
                                "endpoint_transition": "neutral capture means destination becomes self-owned after force disappears; friendly reinforcement means force disappears and a destination unit count increases",
                                "future_route": "UNKNOWN", "future_fuel_cost": "UNKNOWN",
                                "terminal_path_contents": "UNKNOWN",
                                "evidence_note": "docs/V2_M2A_LAUNCH_RULE.md"},
                            "document_id": before.document_id, "match_id": before.match_id.value,
                            "tick": before.tick.value, "source": source.id, "destination": destination.id,
                            "projected_source": [sx, sy], "projected_destination": [dx, dy],
                            "endpoint_hit_tests": hit_tests, "source_sha256": source_manifest,
                            "source_lifecycle": before.lifecycle.value,
                            "source_supply_line_present": fresh["source"].supply_line_present.value,
                            "destination_supply_line_present": fresh["destination"].supply_line_present.value,
                            "selected_tower_none_confirmed": True,
                            "ui_command_branch_proof": "docs/V2_M2A_UI_INPUT_RULE.md; normal selected Option absent selects deploy_force_from_path branch",
                            "typed_deployable": fresh["typed_deployable"], "ui_quantity_evidence": ui,
                            "state": before, "input_sent": False,
                            "intent_quantity_basis": "typed deployable confirmed in pinned official selected panel before deselection; fresh typed vector revalidated"}
                        mouse_down = False
                        async def ordinary_drag():
                            nonlocal mouse_down
                            try:
                                await page.mouse.move(sx, sy)
                                await page.mouse.down()
                                mouse_down = True
                                await page.mouse.move(dx, dy, steps=6)
                                await asyncio.sleep(.15)
                                await page.mouse.up()
                                mouse_down = False
                            finally:
                                if mouse_down:
                                    try:
                                        await page.mouse.up()
                                    finally:
                                        mouse_down = False
                        await record_before_gesture(stream, intent, ordinary_drag)
                        released_at = time.monotonic()
                        prior_destination_counts = _counts(fresh["destination"].units) or {}
                        launched_pair = (source.id, destination.id)
                        def arrived(state):
                            tower_now = next((t for t in state.towers if t.id == destination.id), None)
                            if tower_now is None:
                                return False
                            matching_force = any(f.source.value == launched_pair[0] and
                                f.destination.value == launched_pair[1] for f in (state.forces.value or ()))
                            if matching_force:
                                return False
                            if fresh["scenario"] == "neutral_capture":
                                return tower_now.owner.value == before.player_id.value
                            now_counts = _counts(tower_now.units) or {}
                            return tower_now.owner.value == before.player_id.value and any(
                                now_counts.get(k, 0) > prior_destination_counts.get(k, 0)
                                for k in now_counts)
                        capture_deadline = min(started + args.seconds, released_at + 10)
                        tick_states, poll_errors, arrival_cue, completion = await capture_distinct_ticks(
                            ex.metadata, ex.sample, before.tick.value, capture_deadline, identity, arrived)
                        states = []
                        for observed_at, state in tick_states:
                            state_row = {"offset_s": round(observed_at - released_at, 3),
                                "tick": state.tick.value, "document_id": state.document_id,
                                "match_id": state.match_id.value, "lifecycle": state.lifecycle.value,
                                "state": state, "raw_visible_flags": {"coverage": state.coverage,
                                    "supply_line_flags": {t.id: t.supply_line_present.value for t in state.towers},
                                    "visible_tower_count": len(state.towers),
                                    "visible_force_count": len(state.forces.value or ()),
                                    "forces_known": state.forces.value is not None}}
                            states.append(state_row)
                            durable_before(stream, {"kind": "AFTER_DISTINCT_TICK", "command_index": 1,
                                "observation": state_row})
                        for poll_error in poll_errors:
                            errors.append(poll_error)
                        observed_states = [state for _, state in tick_states]
                        lineage_rows = collect_new_force_lineage(observed_states, source.id, destination.id,
                            fresh["typed_deployable"], before_ids, before.player_id.value)
                        line_guard = supply_line_guard_passed(observed_states, source.id, destination.id,
                            fresh["scenario"] == "friendly_reinforcement")
                        credited = force_lineage_credit(lineage_rows, line_guard)
                        first_change = next((row for row in states
                            if _world_signature(row["state"]) != _world_signature(before)), None)
                        result = {"kind": "COMMAND_RESULT", "command_index": 1,
                            "OBSERVED": {"lineage": lineage_rows, "arrival_cue": arrival_cue,
                                "distinct_world_ticks": [s["tick"] for s in states],
                                "completion_reason": completion},
                            "SIMULATED": "UNKNOWN; no eligible simulation comparison was performed",
                            "DIFF": "UNKNOWN; no observed-versus-simulated comparison was performed",
                            "VERDICT": "PARTIAL_NO_FORMAL_CREDIT",
                            "formal_credit": False,
                            "first_observed_change": ({"offset_s": first_change["offset_s"],
                                "tick": first_change["tick"]} if first_change else None),
                            "first_simulation_divergence": "UNKNOWN",
                            "simulation_divergence_reason": "scenario is capture-only or route/fuel rules are not proved",
                            "observed_force_lineage": lineage_rows,
                            "supply_line_guard_passed": line_guard,
                            "arrival_cue": arrival_cue, "completion_reason": completion,
                            "distinct_world_ticks_captured": [s["tick"] for s in states],
                            "acceptance": "FORCE_LINEAGE_AND_QUANTITY_OBSERVED" if credited else "NO_FORCE_LINEAGE_CREDIT",
                            "source_quantity_alone_is_not_acceptance": True}
                        durable_before(stream, result)
                        events.append(result)
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                if mouse_down and not page.is_closed():
                    try:
                        await asyncio.wait_for(page.mouse.up(), timeout=2)
                    except Exception as exc:
                        errors.append(f"mouse release: {exc}")
                try:
                    await asyncio.wait_for(ex.close(), timeout=3)
                except Exception as exc:
                    errors.append(f"extractor close: {exc}")
                if not page.is_closed():
                    try:
                        await page.mouse.move(20, 20)
                    except Exception:
                        pass
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    report = {"status": "PARTIAL", "run_id": run_id, "mode": "EXECUTE" if args.execute else "PLAN",
        "commands_limit": min(args.max_commands, 6), "seconds_limit": min(args.seconds, 180),
        "events": events, "exclusions": exclusions, "errors": errors,
        "source_manifest": source_manifest, "event_file": str(path.relative_to(ROOT)),
        "first_observed_change": "first canonical visible tower/force/lifecycle signature change; not a simulation divergence",
        "first_simulation_divergence": "UNKNOWN until scenario eligibility and route/fuel rules are proved",
        "unknowns": ["server application tick", "future route after current adjacent leg", "fuel cost", "supply-line path contents"],
        "input_policy": "official Playwright page mouse only; no global input, packets, semantic WASM calls, upgrades, weapons, enemies, allies, or supply-line configuration"}
    report_path = out / f"controlled-transition-{run_id}.json"
    report_path.write_text(json.dumps(report, indent=2, default=state_json, ensure_ascii=False) + "\n", encoding="utf8")
    release_writer(writer_path, writer_token)
    print(json.dumps({"report": str(report_path.relative_to(ROOT)), "events": len(events),
                      "exclusions": exclusions, "errors": errors}, ensure_ascii=False), flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="explicitly permit bounded ordinary UI commands")
    parser.add_argument("--source", type=int, help="operator-selected positively visible own source")
    parser.add_argument("--destination", type=int, help="operator-selected adjacent own or empty neutral destination")
    parser.add_argument("--max-commands", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=30, help="total bound, at most 180 seconds")
    args = parser.parse_args(argv)
    if not 1 <= args.max_commands <= 6:
        parser.error("--max-commands must be 1..6")
    if not 5 <= args.seconds <= 180:
        parser.error("--seconds must be 5..180")
    if args.execute and (args.source is None or args.destination is None):
        parser.error("--execute requires explicit --source and --destination")
    return args


async def bounded_main(args):
    try:
        # Fifteen seconds beyond the cohort bound are reserved for mouse-up,
        # CDP object release, and writer-lease cleanup.
        await asyncio.wait_for(run(args), timeout=args.seconds + 15)
    except asyncio.TimeoutError:
        print(json.dumps({"status": "BOUNDED_TIMEOUT", "seconds": args.seconds,
                          "cleanup_margin_seconds": 15}), flush=True)


if __name__ == "__main__":
    asyncio.run(bounded_main(parse_args()))
