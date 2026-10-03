"""Bounded ordinary-UI own-tower upgrade probe; defaults to read-only."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
import json
import math
import os
from pathlib import Path
import sys
import time
from uuid import uuid4
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "runtime/browsers"))

from kiomet_ai.camera import world_to_page
from kiomet_ai.observe import TOWER_TYPES, TOWER_TYPE_ZH
from kiomet_ai.v2.observe import rules
from kiomet_ai.v2.observe.extractor import (
    CLIENT_SHA256, ClientExtractor, connect_dedicated, is_official_client_url,
)
from kiomet_ai.v2.state import Units
from tools.v2_controlled_transition_capture import (
    is_project_headless_browser_process, release_writer, reserve_writer,
)
from playwright.async_api import async_playwright


ALLOWED_TARGETS = frozenset({1, 3, 4, 9, 10, 12, 14, 16, 17, 18, 22, 25, 26})
TARGET_NAMES_ZH = {english: chinese for chinese, english in TOWER_TYPE_ZH.items()}
MAX_FACT_AGE_MS = 5_000
MAX_SOURCE_TICK_STALL_MS = 1_000


def _known(fact, state=None, *, coherent=False):
    if fact is None:
        return False, None
    value = getattr(fact, "value", None)
    knowledge = getattr(getattr(fact, "knowledge", None), "value", getattr(fact, "knowledge", None))
    known = knowledge in {"OBSERVED", "DERIVED"} and value is not None
    if known and state is not None:
        at = getattr(fact, "observed_at_ms", None)
        received = getattr(state, "received_at_ms", None)
        known = (type(at) is int and type(received) is int and
                 0 <= received - at <= MAX_FACT_AGE_MS)
        if known and coherent:
            sampled = getattr(state, "sampled_at_ms", None)
            known = type(sampled) is int and at == sampled
    return known, value if known else None


def _state_identity(state):
    values = []
    for name in ("match_id", "player_id", "lifecycle", "source_mode"):
        known, value = _known(getattr(state, name, None), state, coherent=True)
        if not known:
            return None
        values.append(value)
    if not state.document_id or state.client_sha256 != CLIENT_SHA256:
        return None
    if getattr(values[2], "value", values[2]) != "IN_MATCH" or getattr(values[3], "value", values[3]) != "NETWORK":
        return None
    tick_at_ok, tick_at = _known(getattr(state, "world_sequence_observed_at_ms", None), state)
    if (not tick_at_ok or type(tick_at) is not int or
            not 0 <= state.received_at_ms - tick_at <= MAX_SOURCE_TICK_STALL_MS):
        return None
    return (state.document_id, *values, state.client_sha256)


def _tower_visible_own(state, tower):
    vis_ok, vis = _known(getattr(tower, "visibility", None), state, coherent=True)
    owner_ok, owner = _known(getattr(tower, "owner", None), state, coherent=True)
    player_ok, player = _known(getattr(state, "player_id", None), state, coherent=True)
    relation_ok, relation = _known(getattr(tower, "relation", None), state, coherent=True)
    return (vis_ok and vis is True and owner_ok and player_ok and owner == player and
            relation_ok and getattr(relation, "value", relation) == "SELF")


def candidate_rows(state) -> list[dict]:
    """Return pure own-visible direct-upgrade candidates and explicit exclusions."""
    rows = []
    own_towers = [t for t in getattr(state, "towers", ()) if _tower_visible_own(state, t)]
    for tower in sorted(own_towers, key=lambda t: t.id):
        type_ok, source_type = _known(tower.tower_type, state, coherent=True)
        units_ok, source_units = _known(getattr(tower, "units", None), state, coherent=True)
        delay_ok, delay = _known(tower.delay_ticks, state, coherent=True)
        candidates_ok, candidates = _known(tower.upgrade_candidates, state, coherent=True)
        locks_ok, locks = _known(tower.upgrade_locks, state, coherent=True)
        capacity_ok, cap_units = _known(tower.capacity, state, coherent=True)
        effects_ok, effects = _known(tower.effects, state, coherent=True)
        resources_ok, resources = _known(getattr(state, "upgrade_resources", None), state, coherent=True)
        resource_counts = None
        if resources_ok and isinstance(resources, (tuple, list)):
            pairs = list(resources)
            if (len(pairs) == 27 and all(isinstance(p, (tuple, list)) and len(p) == 2 and
                    type(p[0]) is int and type(p[1]) is int and p[1] >= 0 for p in pairs) and
                    [p[0] for p in pairs] == list(range(27))):
                resource_counts = [p[1] for p in pairs]
        morale = dict(effects).get("MORALE_BOOST") if effects_ok and isinstance(effects, (tuple, list)) else None
        prereq_by_target = {}
        if candidates_ok and isinstance(candidates, (tuple, list)):
            for entry in candidates:
                if isinstance(entry, (tuple, list)) and len(entry) == 3 and type(entry[0]) is int:
                    prereq_by_target[entry[0]] = (entry[1], entry[2])
        lock_by_target = {}
        if locks_ok and isinstance(locks, (tuple, list)):
            for entry in locks:
                if isinstance(entry, (tuple, list)) and len(entry) == 2 and type(entry[0]) is int:
                    lock_by_target[entry[0]] = entry[1]
        for target_type in sorted(ALLOWED_TARGETS):
            direct = prereq_by_target.get(target_type)
            reasons = []
            if not type_ok or type(source_type) is not int:
                reasons.append("SOURCE_TYPE_UNKNOWN")
            elif rules.DOWNGRADE[target_type] != source_type:
                reasons.append("TARGET_NOT_DIRECT_UPGRADE")
            if not units_ok or not isinstance(source_units, Units):
                reasons.append("SOURCE_UNITS_UNKNOWN")
            else:
                unit_pairs = source_units.counts
                if (len(unit_pairs) != 10 or tuple(unit for unit, _ in unit_pairs) != tuple(range(10)) or
                        any(type(unit) is not int or type(count) is not int or count < 0
                            for unit, count in unit_pairs)):
                    reasons.append("SOURCE_UNITS_VECTOR_INCOMPLETE")
                elif dict(unit_pairs)[9] != 0:
                    reasons.append("SOURCE_HAS_RULER")
            if not delay_ok or delay != 0:
                reasons.append("SOURCE_DELAY_NOT_KNOWN_ZERO")
            if direct is None:
                reasons.append("DIRECT_PREREQUISITE_ROW_MISSING" if candidates_ok else "DIRECT_PREREQUISITE_UNKNOWN")
            expected_prerequisites = tuple((kind, resource_counts[kind], need)
                for kind, need in enumerate(rules.PREREQUISITES[target_type]) if need) if resource_counts is not None else None
            if direct is not None and expected_prerequisites is None:
                reasons.append("OWN_PREREQUISITE_COUNTS_UNKNOWN")
            elif direct is not None and (direct[0] != expected_prerequisites or direct[1] is not True or
                  any(have < need for _kind, have, need in expected_prerequisites)):
                reasons.append("DIRECT_PREREQUISITE_DOES_NOT_MATCH_PINNED_COUNTS")
            if not locks_ok or target_type not in lock_by_target or lock_by_target[target_type] is not False:
                reasons.append("TARGET_LOCK_NOT_KNOWN_FALSE")
            shield_before = None
            shield_after = None
            if capacity_ok and cap_units is not None and morale is not None:
                try:
                    shield_before = dict(cap_units.counts)[0]
                    shield_after = dict(rules.capacity(target_type, morale).counts)[0]
                except (TypeError, ValueError, KeyError):
                    pass
            if shield_before is None or shield_after is None:
                reasons.append("SHIELD_CAPACITY_UNKNOWN")
            elif shield_after < shield_before:
                reasons.append("TARGET_SHIELD_CAPACITY_LOWER")
            nominal = rules.UPGRADE_DELAY[target_type] if target_type in range(len(rules.UPGRADE_DELAY)) else None
            if type(nominal) is not int or nominal <= 0:
                reasons.append("NOMINAL_UPGRADE_DELAY_UNKNOWN")
            rows.append({"tower_id": tower.id, "source_type": source_type if type_ok else None,
                         "target_type": target_type, "nominal_delay": nominal,
                         "shield_before": shield_before, "shield_after": shield_after,
                         "eligible": not reasons, "reasons": reasons})
    return rows


def _names(type_id: int) -> set[str]:
    if type(type_id) is not int or type_id not in range(len(TOWER_TYPES)):
        return set()
    result = {TOWER_TYPES[type_id]}
    chinese = TARGET_NAMES_ZH.get(TOWER_TYPES[type_id])
    if chinese:
        result.add(chinese)
    return result


def _target_names(type_id: int) -> set[str]:
    """Exact target labels currently pinned to the public English client catalog."""
    if type(type_id) is not int or type_id not in range(len(TOWER_TYPES)):
        return set()
    return {TOWER_TYPES[type_id]}


def inspect_upgrade_dom(dom_snapshot: dict, source_type: int, target_type: int) -> dict:
    """Pure fail-closed check of exact heading and one visible normal upgrade title."""
    reasons = []
    source_names = _names(source_type)
    headings = dom_snapshot.get("headings") if isinstance(dom_snapshot, dict) else None
    heading_matches = ([str(h).strip() for h in headings if str(h).strip() in source_names]
                       if isinstance(headings, list) else [])
    if len(heading_matches) != 1:
        reasons.append("SOURCE_HEADING_NOT_EXACT")
    titles = {f"Upgrade to {name}" for name in _target_names(target_type)}
    buttons = dom_snapshot.get("buttons") if isinstance(dom_snapshot, dict) else None
    if not isinstance(buttons, list):
        reasons.append("UPGRADE_BUTTONS_UNKNOWN")
        buttons = []
    matches = [b for b in buttons if isinstance(b, dict) and b.get("title") in titles and b.get("visible") is True]
    if len(matches) != 1:
        reasons.append("EXACT_VISIBLE_UPGRADE_TITLE_NOT_UNIQUE")
    selected = matches[0] if len(matches) == 1 else None
    if selected is not None:
        if (selected.get("enabled") is not True or selected.get("pointer_events") is not True or
                selected.get("locked_glyph") is not False or
                selected.get("hidden_lock_icon") is not False):
            reasons.append("UPGRADE_BUTTON_DISABLED_LOCKED_OR_UNSAFE")
        bbox = selected.get("bbox")
        if (not isinstance(bbox, list) or len(bbox) != 4 or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in bbox) or
                bbox[2] <= 0 or bbox[3] <= 0):
            reasons.append("UPGRADE_BUTTON_BOUNDS_UNKNOWN")
    return {"eligible": not reasons, "reasons": reasons,
            "exact_title": selected.get("title") if selected else None,
            "bbox": selected.get("bbox") if selected else None}


def _get_tower(state, tower_id):
    found = [t for t in getattr(state, "towers", ()) if t.id == tower_id and _tower_visible_own(state, t)]
    return found[0] if len(found) == 1 else None


def verify_upgrade(before_state, ui_result: dict, after_states: list, target_type: int) -> dict:
    """Verify a direct upgrade on consecutive positive own-tower observations."""
    reasons = []
    if type(target_type) is not int or target_type not in ALLOWED_TARGETS:
        return {"status": "UNKNOWN", "reasons": ["TARGET_TYPE_OUTSIDE_FROZEN_ALLOWLIST"]}
    identity = _state_identity(before_state)
    if identity is None:
        return {"status": "UNKNOWN", "reasons": ["BEFORE_EPOCH_OR_NETWORK_IDENTITY_UNKNOWN"]}
    if ui_result.get("click_status") != "SUCCESS":
        reasons.append("OFFICIAL_UI_CLICK_NOT_CONFIRMED")
    if ui_result.get("dom_guard_passed") is not True:
        reasons.append("NORMAL_UPGRADE_DOM_GUARD_NOT_CONFIRMED")
    expected_titles = {f"Upgrade to {name}" for name in _target_names(target_type)}
    if ui_result.get("upgrade_title") not in expected_titles:
        reasons.append("UPGRADE_TITLE_NOT_EXACT_FOR_TARGET")
    if any(ui_result.get(key) is not True for key in
           ("button_visible", "button_enabled", "pointer_events")) or any(
            ui_result.get(key) is not False for key in ("locked_glyph", "hidden_lock_icon")):
        reasons.append("NORMAL_BUTTON_STATE_FIELDS_MISSING_OR_UNSAFE")
    tower_id = ui_result.get("selected_tower_id")
    if type(tower_id) is not int or ui_result.get("target_type") != target_type:
        reasons.append("SELECTED_TOWER_OR_TARGET_UNKNOWN")
    target_rows = [r for r in candidate_rows(before_state)
                   if r["tower_id"] == tower_id and r["target_type"] == target_type]
    if len(target_rows) != 1 or not target_rows[0]["eligible"]:
        reasons.append("BEFORE_PREREQUISITE_LOCK_OR_CAPACITY_NOT_ELIGIBLE")
    tower = _get_tower(before_state, tower_id)
    if tower is None:
        reasons.append("BEFORE_OWN_TOWER_NOT_POSITIVELY_VISIBLE")
    else:
        type_ok, source_type = _known(tower.tower_type, before_state)
        delay_ok, delay = _known(tower.delay_ticks, before_state)
        if not type_ok or not delay_ok:
            reasons.append("BEFORE_TYPE_OR_DELAY_UNKNOWN")
        if type_ok and ui_result.get("source_heading") not in _names(source_type):
            reasons.append("UI_HEADING_DOES_NOT_MATCH_SOURCE_TYPE")
    if len(after_states) != 2:
        reasons.append("TWO_CONSECUTIVE_AFTER_TICKS_REQUIRED")
    ticks = []
    before_tick_ok, before_tick = _known(before_state.tick, before_state)
    previous = before_tick if before_tick_ok else None
    contradictory = False
    for index, state in enumerate(after_states[:2], 1):
        current_identity = _state_identity(state)
        tick_ok, tick = _known(getattr(state, "tick", None), state)
        ticks.append(tick if tick_ok else None)
        if current_identity != identity:
            reasons.append("EPOCH_PLAYER_OR_CLIENT_CHANGED")
            continue
        if not tick_ok or previous is None or tick != ((previous + 1) & 0xFFFF):
            reasons.append("TICK_NOT_CONSECUTIVE")
        previous = tick if tick_ok else None
        observed = _get_tower(state, tower_id)
        if observed is None:
            reasons.append("OWN_TOWER_NOT_VISIBLE_AFTER_ACTION")
            continue
        type_ok, observed_type = _known(observed.tower_type, state)
        delay_ok, observed_delay = _known(observed.delay_ticks, state)
        if not type_ok or not delay_ok:
            reasons.append("AFTER_TYPE_OR_DELAY_UNKNOWN")
            continue
        nominal = rules.UPGRADE_DELAY[target_type]
        expected_type = target_type
        expected_delay = nominal if index == 1 else nominal - 1
        if observed_type != expected_type or observed_delay != expected_delay:
            contradictory = True
            reasons.append("KNOWN_TYPE_OR_DELAY_DIFFERS_FROM_FROZEN_EXPECTATION")
    reasons = list(dict.fromkeys(reasons))
    if not reasons:
        status = "SUCCESS"
    elif contradictory and all(r == "KNOWN_TYPE_OR_DELAY_DIFFERS_FROM_FROZEN_EXPECTATION" for r in reasons):
        status = "CONTRADICTED_SINGLE_OBSERVATION_NOT_FALSIFICATION"
    else:
        status = "UNKNOWN"
    return {"status": status, "reasons": reasons, "tower_id": tower_id,
            "source_type": _known(tower.tower_type, before_state)[1] if tower else None,
            "target_type": target_type, "expected_nominal_delay": rules.UPGRADE_DELAY[target_type],
            "ticks": ticks}


def _serialize(value):
    if is_dataclass(value):
        return {f.name: getattr(value, f.name) for f in fields(value)}
    raise TypeError(type(value).__name__)


def _append(stream, row):
    stream.write(json.dumps(row, ensure_ascii=False, default=_serialize) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


async def _page_click(page, x: float, y: float):
    """Use only official page mouse input and always release within a short bound."""
    try:
        await page.mouse.click(x, y)
    finally:
        try:
            await asyncio.wait_for(page.mouse.up(), timeout=2)
        except Exception:
            pass


async def _dom_snapshot(page):
    return await page.evaluate("""() => {
      const vis=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();
        return !!(r.width&&r.height&&s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0');};
      const headings=[...document.querySelectorAll('h2')].filter(vis).map(e=>e.innerText.trim());
      const visible_titles=[...document.querySelectorAll('[title]')].filter(vis).slice(0,80).map(e=>({
        tag:e.tagName,title:(e.getAttribute('title')||'').slice(0,160),
        text:(e.innerText||'').trim().slice(0,100)}));
      const buttons=[...document.querySelectorAll('[title^=\\"Upgrade to \\"]')].map(e=>{
        const r=e.getBoundingClientRect(),s=getComputedStyle(e),text=(e.innerText||'').trim();
        const descendants=[...e.querySelectorAll('*')];
        const lockMarker=descendants.some(n=>/[🔒🔐]/.test(n.innerText||'')||
          /lock/i.test((n.getAttribute('title')||'')+' '+String(n.className||'')));
        const lockGlyph=/[🔒🔐]/.test(text)||descendants.some(n=>vis(n)&&/[🔒🔐]/.test(n.innerText||''));
        const classes=String(e.className||'');
        return {title:e.getAttribute('title'),visible:vis(e),
          enabled:!e.disabled&&e.getAttribute('aria-disabled')!=='true'&&!/disabled/i.test(classes)&&s.cursor==='pointer',
          cursor:s.cursor,
          pointer_events:s.pointerEvents!=='none',locked_glyph:lockGlyph,hidden_lock_icon:lockMarker,
          bbox:[r.x,r.y,r.width,r.height]};
      });
      return {headings,buttons,visible_titles};
    }""")


async def _read_candidate_state(ex, tower_id, target_type):
    state, raw = await ex.sample()
    row = next((r for r in candidate_rows(state)
                if r["tower_id"] == tower_id and r["target_type"] == target_type), None)
    return state, raw, row


async def _selection_roundtrip(ex, page, stream, tower_id, source_type, identity, deadline):
    """Poll one ordinary selection for at most two seconds and durably record each witness."""
    local_deadline = min(deadline, time.monotonic() + 2.0)
    attempts = 0
    last = {"matched": False, "state": None, "raw": None, "dom": None,
            "source_heading": None, "attempts": attempts,
            "witness": {"tower_id": tower_id, "expected_source_type": source_type,
                        "matched": False, "reasons": ["NO_CURRENT_SAMPLE_WITHIN_SELECTION_WINDOW"]}}
    while time.monotonic() < local_deadline:
        attempts += 1
        try:
            remaining = max(0.01, local_deadline - time.monotonic())
            state, raw = await asyncio.wait_for(ex.sample(), timeout=remaining)
            current_identity = _state_identity(state)
            remaining = max(0.01, local_deadline - time.monotonic())
            dom = await asyncio.wait_for(_dom_snapshot(page), timeout=remaining)
            remaining = max(0.01, local_deadline - time.monotonic())
            after_state, after_raw = await asyncio.wait_for(ex.sample(), timeout=remaining)
            after_identity = _state_identity(after_state)
            heading_matches = [str(h).strip() for h in dom.get("headings", [])
                               if str(h).strip() in _names(source_type)]
            heading = heading_matches[0] if len(heading_matches) == 1 else None
            heading_reason = ("SOURCE_HEADING_NOT_EXACT" if not heading_matches else
                              "SOURCE_HEADING_NOT_UNIQUE" if len(heading_matches) != 1 else None)
            rows = [r for r in candidate_rows(state)
                    if r["tower_id"] == tower_id and r["source_type"] == source_type]
            titles = sorted({b.get("title") for b in dom.get("buttons", [])
                             if isinstance(b, dict) and b.get("visible") is True and
                             isinstance(b.get("title"), str)})
            guards = [{"target_type": r["target_type"],
                       **inspect_upgrade_dom(dom, source_type, r["target_type"])}
                      for r in rows]
            selected_id = raw.get("selected_tower")
            selected_after_id = after_raw.get("selected_tower")
            own_visible = _get_tower(state, tower_id) is not None
            own_after_visible = _get_tower(after_state, tower_id) is not None
            before_tower = _get_tower(state, tower_id)
            after_tower = _get_tower(after_state, tower_id)
            before_type_ok, before_type = (_known(before_tower.tower_type, state, coherent=True)
                                           if before_tower else (False, None))
            after_type_ok, after_type = (_known(after_tower.tower_type, after_state, coherent=True)
                                         if after_tower else (False, None))
            actor_stable = (before_type_ok and after_type_ok and
                            before_type == source_type and after_type == source_type)
            matched = (current_identity == identity and after_identity == identity and
                       selected_id == tower_id and selected_after_id == tower_id and
                       own_visible and own_after_visible and actor_stable and heading is not None)
            row = {"kind": "SELECTION_WITNESS_ATTEMPT", "tower_id": tower_id,
                   "expected_source_type": source_type, "attempt": attempts,
                   "tick": getattr(getattr(state, "tick", None), "value", None),
                   "sampled_at_ms": getattr(state, "sampled_at_ms", None),
                   "received_at_ms": getattr(state, "received_at_ms", None),
                   "identity_current": current_identity == identity,
                   "after_tick": getattr(getattr(after_state, "tick", None), "value", None),
                   "after_sampled_at_ms": getattr(after_state, "sampled_at_ms", None),
                   "after_received_at_ms": getattr(after_state, "received_at_ms", None),
                   "after_identity_current": after_identity == identity,
                   "observed_selected_tower_id": selected_id,
                   "after_selected_tower_id": selected_after_id,
                   "own_tower_positively_visible": own_visible,
                   "own_tower_positively_visible_after_dom": own_after_visible,
                   "observed_source_type": before_type if before_type_ok else None,
                   "observed_source_type_after_dom": after_type if after_type_ok else None,
                   "source_heading": heading, "headings": dom.get("headings", []),
                   "all_visible_titles": dom.get("visible_titles", []),
                   "visible_upgrade_titles": titles, "candidate_title_guards": guards,
                   "matched": matched,
                   "reasons": (["EPOCH_OR_NETWORK_IDENTITY_MISMATCH"] if current_identity != identity else []) +
                              (["EPOCH_OR_NETWORK_IDENTITY_CHANGED_DURING_DOM_READ"] if after_identity != identity else []) +
                              (["SELECTED_TOWER_ID_MISMATCH"] if selected_id != tower_id else []) +
                              (["SELECTED_TOWER_ID_CHANGED_DURING_DOM_READ"] if selected_after_id != tower_id else []) +
                              (["OWN_TOWER_NOT_POSITIVELY_VISIBLE"] if not own_visible else []) +
                              (["OWN_TOWER_NOT_POSITIVELY_VISIBLE_AFTER_DOM"] if not own_after_visible else []) +
                              (["SOURCE_TYPE_NOT_STABLE_AROUND_DOM_READ"] if not actor_stable else []) +
                              ([heading_reason] if heading_reason else [])}
            _append(stream, row)
            last = {"matched": matched, "state": state, "raw": raw, "dom": dom,
                    "source_heading": heading, "attempts": attempts, "witness": row}
            if matched:
                _append(stream, {**row, "kind": "SELECTION_WITNESS_SUMMARY", "attempts": attempts})
                return last
        except (ValueError, RuntimeError, asyncio.TimeoutError) as exc:
            _append(stream, {"kind": "SELECTION_WITNESS_ATTEMPT", "tower_id": tower_id,
                             "expected_source_type": source_type, "attempt": attempts,
                             "matched": False, "reasons": ["CURRENT_SAMPLE_OR_DOM_UNKNOWN"],
                             "error": f"{type(exc).__name__}:{str(exc)[:120]}"})
        await asyncio.sleep(.08)
    last["attempts"] = attempts
    _append(stream, {**last["witness"], "kind": "SELECTION_WITNESS_SUMMARY",
                     "attempts": attempts, "matched": False})
    return last


async def _next_distinct(ex, prior_tick, deadline):
    while time.monotonic() < deadline:
        state, raw = await ex.sample()
        tick_ok, tick = _known(state.tick, state)
        if tick_ok and tick != prior_tick:
            return state, raw
        await asyncio.sleep(.08)
    return None, None


def _lease_guard(seconds: int):
    lease = ROOT / "runtime/research/v2/headless-host.json"
    if not lease.is_file():
        raise RuntimeError("owned headless lease is missing")
    data = json.loads(lease.read_text(encoding="utf-8"))
    profile = Path(data.get("profile", "")).resolve()
    expected = (ROOT / "runtime/browser-profile").resolve()
    if profile != expected:
        raise RuntimeError("headless lease profile is not the project profile")
    remaining = data.get("deadline_monotonic_ms", 0) - time.monotonic_ns() // 1_000_000
    if type(data.get("pid")) is not int or data.get("pid") <= 0 or remaining < (seconds + 15) * 1000:
        raise RuntimeError("headless lease cannot cover the bounded probe")
    try:
        process = psutil.Process(data["pid"])
        host_script = (ROOT / "tools/v2_headless_research.py").resolve()
        if (not process.name().lower().startswith(("python", "py")) or
                not any(Path(arg).resolve() == host_script for arg in process.cmdline() if arg.lower().endswith(".py"))):
            raise RuntimeError("lease PID is not the project's headless research host")
        chrome = []
        for child in process.children(recursive=True):
            try:
                if is_project_headless_browser_process(child.name(), child.cmdline(), expected):
                    chrome.append(child.pid)
            except psutil.Error:
                continue
        if len(chrome) != 1:
            raise RuntimeError("lease host does not own exactly one project-profile Chromium process")
    except (KeyError, TypeError, ValueError, OSError, psutil.Error) as exc:
        raise RuntimeError("headless lease owner identity is invalid") from exc
    return data


@contextmanager
def _writer_lease(seconds: int):
    _lease_guard(seconds)
    root = ROOT / "runtime/research/v2"
    path = root / "controlled-transition-writer.json"
    profile = (ROOT / "runtime/browser-profile").resolve()
    token = reserve_writer(path, os.getpid(), profile,
                          time.monotonic_ns() // 1_000_000 + seconds * 1000)
    try:
        yield
    finally:
        release_writer(path, token)


async def run_probe(args):
    started = time.monotonic()
    deadline = started + args.seconds
    run_id = uuid4().hex
    out = args.out or (ROOT / "runtime/research/v2/goal" / f"own-upgrade-probe-{run_id}.jsonl")
    out = Path(out).resolve()
    allowed_out = (ROOT / "runtime/research/v2/goal").resolve()
    if not out.is_relative_to(allowed_out):
        raise ValueError("evidence output must stay under runtime/research/v2/goal")
    out.parent.mkdir(parents=True, exist_ok=True)
    events = []
    with out.open("x", encoding="utf-8") as stream:
        lease_cm = _writer_lease(args.seconds)
        try:
            lease_cm.__enter__()
        except Exception as exc:
            reason = f"{type(exc).__name__}: {str(exc)[:180]}"
            _append(stream, {"kind": "PROBE_ABORTED", "status": "UNKNOWN", "reason": reason})
            return {"status": "UNKNOWN", "reasons": [reason], "out": str(out)}
        pw_context = None
        pw = None
        ex = None
        try:
            pw_context = async_playwright()
            pw = await asyncio.wait_for(pw_context.start(), timeout=5)
            browser = await connect_dedicated(pw, ROOT)
            official = [p for ctx in browser.contexts for p in ctx.pages if is_official_client_url(p.url)]
            if len(official) != 1:
                raise RuntimeError("expected exactly one owned official-client page")
            page = official[0]
            ex = ClientExtractor(page)
            await ex.attach()
            try:
                state = raw = None
                ident = None
                rows = []
                sample_count = 0
                sample_errors = []
                sample_attempts = 0
                sample_deadline = deadline if args.execute else min(deadline, time.monotonic() + 2)
                while time.monotonic() < sample_deadline:
                    sample_attempts += 1
                    try:
                        state, raw = await ex.sample()
                        sample_count += 1
                        ident = _state_identity(state)
                        rows = candidate_rows(state)
                        _append(stream, {"kind": "SAMPLE_ATTEMPT", "attempt": sample_attempts,
                                         "status": "SNAPSHOT", "tick": state.tick.value,
                                         "coverage": state.coverage,
                                         "visible_tower_count": len(state.towers),
                                         "positively_own_tower_count": sum(
                                             1 for t in state.towers if _tower_visible_own(state, t)),
                                         "eligible_count": sum(r["eligible"] for r in rows),
                                         "identity_current": ident is not None})
                        if ident is not None and any(r["eligible"] for r in rows):
                            break
                        if not args.execute:
                            break
                    except (ValueError, RuntimeError) as exc:
                        sample_errors.append(f"{type(exc).__name__}:{str(exc)[:100]}")
                        _append(stream, {"kind": "SAMPLE_ATTEMPT", "attempt": sample_attempts,
                                         "status": "ERROR", "error": sample_errors[-1]})
                        if not args.execute and "current visibility cache pending" not in str(exc):
                            break
                    await asyncio.sleep(.1)
                if state is None:
                    _append(stream, {"kind": "INITIAL_LOCAL_CANDIDATES", "sample_count": sample_count,
                                     "rows": [], "errors": sample_errors,
                                     "coverage": "UNKNOWN", "visible_tower_count": 0,
                                     "positively_own_tower_count": 0})
                    raise RuntimeError("no current canonical snapshot was available")
                own_visible_count = sum(1 for t in state.towers if _tower_visible_own(state, t))
                _append(stream, {"kind": "INITIAL_LOCAL_CANDIDATES", "sample_count": sample_count,
                                 "rows": rows, "eligible_count": sum(r["eligible"] for r in rows),
                                 "visible_tower_count": len(state.towers),
                                 "positively_own_tower_count": own_visible_count,
                                 "coverage": state.coverage, "tick": state.tick.value,
                                 "errors": sample_errors})
                available = [r for r in rows if r["eligible"]]
                if ident is None or getattr(state.lifecycle.value, "value", state.lifecycle.value) != "IN_MATCH":
                    if args.execute:
                        _append(stream, {"kind": "PROBE_RESULT", "status": "UNKNOWN",
                                         "reason": "CURRENT_NETWORK_MATCH_OR_TICK_NOT_FRESH"})
                        return {"status": "UNKNOWN", "reasons": ["CURRENT_NETWORK_MATCH_OR_TICK_NOT_FRESH"],
                                "out": str(out)}
                if not args.execute:
                    _append(stream, {"kind": "READ_ONLY_PLAN", "run_id": run_id,
                                     "client_sha256": CLIENT_SHA256,
                                     "meaning": "no page input was sent"})
                    return {"status": "READ_ONLY", "eligible_targets": len(available), "out": str(out)}
                if not available:
                    _append(stream, {"kind": "PROBE_RESULT", "status": "UNKNOWN",
                                     "reason": "NO_KNOWN_ELIGIBLE_DIRECT_OWN_UPGRADE"})
                    return {"status": "UNKNOWN", "reasons": ["NO_KNOWN_ELIGIBLE_DIRECT_OWN_UPGRADE"],
                            "out": str(out)}

                # One ordinary page click per selected own tower, up to six; one upgrade click total.
                own_ids = sorted({r["tower_id"] for r in available})
                view = await page.evaluate("""() => {const c=document.querySelector('canvas');
                  if(!c)return null;const r=c.getBoundingClientRect();return {w:c.width,h:c.height,dpr:devicePixelRatio,
                    left:r.left,top:r.top,rw:r.width,rh:r.height,tag:c.tagName};}""")
                if not view or view["dpr"] != 1 or view["tag"] != "CANVAS":
                    raise RuntimeError("normal canvas projection unavailable")
                tries = 0
                for tower_id in own_ids:
                    if tries >= 6 or time.monotonic() >= deadline:
                        break
                    pre = next((t for t in state.towers if t.id == tower_id and _tower_visible_own(state, t)), None)
                    if pre is None:
                        continue
                    pos_ok, pos = _known(pre.position, state)
                    camera = raw.get("camera_candidate")
                    if not pos_ok or not isinstance(camera, list) or len(camera) != 3:
                        continue
                    x, y = world_to_page(*pos, *camera, view["w"], view["h"], 1, view["left"], view["top"])
                    if not (view["left"] < x < view["left"] + view["rw"] and
                            view["top"] < y < view["top"] + view["rh"]):
                        continue
                    canvas_hit = await page.evaluate("([x,y])=>document.elementFromPoint(x,y)?.tagName==='CANVAS'", [x, y])
                    if not canvas_hit:
                        continue
                    tries += 1
                    source_type = next(r["source_type"] for r in available if r["tower_id"] == tower_id)
                    click_error = None
                    try:
                        await _page_click(page, x, y)
                    except Exception as exc:
                        click_error = f"{type(exc).__name__}:{str(exc)[:120]}"
                    _append(stream, {"kind": "OWN_SELECTION_CLICK", "attempt": tries,
                                     "clicked_tower_id": tower_id, "expected_source_type": source_type,
                                     "before_tick": state.tick.value, "page_xy": [x, y],
                                     "camera_candidate": camera, "time_monotonic": time.monotonic(),
                                     "click_error": click_error,
                                     "click_status": "SUCCESS" if click_error is None else "UNKNOWN"})
                    witness = await _selection_roundtrip(ex, page, stream, tower_id,
                                                         source_type, ident, deadline)
                    if not witness["matched"]:
                        continue
                    fresh, fresh_raw, dom = witness["state"], witness["raw"], witness["dom"]
                    choices = [r for r in candidate_rows(fresh)
                               if r["tower_id"] == tower_id and r["eligible"] and
                               r["source_type"] == source_type]
                    for row in choices:
                        if time.monotonic() >= deadline:
                            break
                        title_check = inspect_upgrade_dom(dom, row["source_type"], row["target_type"])
                        if not title_check["eligible"]:
                            continue
                        # Recheck selected identity and exact visible button immediately before fsync.
                        fresh2, fresh_raw2, fresh_row = await _read_candidate_state(ex, tower_id, row["target_type"])
                        if (_state_identity(fresh2) != ident or fresh_raw2.get("selected_tower") != tower_id or
                                fresh_row is None or not fresh_row["eligible"] or
                                fresh_row["source_type"] != row["source_type"]):
                            continue
                        current_dom = await _dom_snapshot(page)
                        guard = inspect_upgrade_dom(current_dom, row["source_type"], row["target_type"])
                        if not guard["eligible"]:
                            continue
                        bbox = guard["bbox"]
                        click_x, click_y = bbox[0] + bbox[2] / 2, bbox[1] + bbox[3] / 2
                        target_element = await page.evaluate("""([x,y,title])=>{const e=document.elementFromPoint(x,y);
                          return !!e&&(e.getAttribute('title')===title||!!e.closest('[title]')&&e.closest('[title]').getAttribute('title')===title)}""",
                          [click_x, click_y, guard["exact_title"]])
                        heading_name = next((n for n in _names(row["source_type"])
                                             if n in set(current_dom["headings"])), None)
                        if not target_element or heading_name is None:
                            continue
                        if time.monotonic() >= deadline:
                            break
                        intent = {"kind": "BEFORE_INTENT", "run_id": run_id,
                                  "document_id": fresh2.document_id, "match_id": fresh2.match_id.value,
                                  "player_id": fresh2.player_id.value, "lifecycle": fresh2.lifecycle.value,
                                  "tick": fresh2.tick.value, "sequence": fresh2.sequence,
                                  "client_sha256": fresh2.client_sha256,
                                  "tower_id": tower_id, "source_type": row["source_type"],
                                  "target_type": row["target_type"],
                                  "expected_nominal_delay": row["nominal_delay"],
                                  "source_shield_capacity": row["shield_before"],
                                  "target_shield_capacity": row["shield_after"],
                                  "selected_tower_id": fresh_raw2.get("selected_tower"),
                                  "source_heading": heading_name,
                                  "dom_guard": guard, "candidate": fresh_row,
                                  "state": fresh2, "coverage_preserved": fresh2.coverage}
                        _append(stream, intent)
                        try:
                            await _page_click(page, click_x, click_y)
                            ui_result = {"kind": "UI_RESULT", "click_status": "SUCCESS",
                                         "selected_tower_id": tower_id, "source_heading": heading_name,
                                         "target_type": row["target_type"], "upgrade_title": guard["exact_title"],
                                         "dom_guard_passed": True, "button_visible": True,
                                         "button_enabled": True, "pointer_events": True,
                                         "locked_glyph": False, "hidden_lock_icon": False,
                                         "click_xy": [click_x, click_y]}
                        except Exception as exc:
                            ui_result = {"kind": "UI_RESULT", "click_status": "UNKNOWN",
                                         "selected_tower_id": tower_id, "target_type": row["target_type"],
                                         "dom_guard_passed": True, "error": type(exc).__name__}
                        _append(stream, ui_result)
                        after = []
                        first, _ = await _next_distinct(ex, fresh2.tick.value, deadline)
                        if first is not None:
                            after.append(first)
                            _append(stream, {"kind": "AFTER_TICK", "offset": 1,
                                             "tick": first.tick.value, "state": first})
                            second, _ = await _next_distinct(ex, first.tick.value, deadline)
                            if second is not None:
                                after.append(second)
                                _append(stream, {"kind": "AFTER_TICK", "offset": 2,
                                                 "tick": second.tick.value, "state": second})
                        ui_norm = {**ui_result, "source_heading": heading_name,
                                   "dom_guard_passed": guard["eligible"]}
                        verdict = verify_upgrade(fresh2, ui_norm, after, row["target_type"])
                        _append(stream, {"kind": "VERDICT", **verdict})
                        return {**verdict, "out": str(out), "selection_clicks": tries}
                _append(stream, {"kind": "PROBE_RESULT", "status": "UNKNOWN",
                                 "reason": "NO_UNAMBIGUOUS_NORMAL_UPGRADE_BUTTON_WITHIN_SELECTION_BOUND",
                                 "selection_clicks": tries})
                return {"status": "UNKNOWN", "reasons": ["NO_UNAMBIGUOUS_NORMAL_UPGRADE_BUTTON"],
                        "selection_clicks": tries, "out": str(out)}
            finally:
                if ex is not None:
                    try:
                        await asyncio.wait_for(ex.close(), timeout=6)
                    except Exception:
                        pass
        except Exception as exc:
            reason = f"{type(exc).__name__}: {str(exc)[:180]}"
            _append(stream, {"kind": "PROBE_ABORTED", "status": "UNKNOWN", "reason": reason})
            return {"status": "UNKNOWN", "reasons": [reason], "out": str(out)}
        finally:
            try:
                if pw is not None:
                    await asyncio.wait_for(pw.stop(), timeout=6)
            except Exception:
                pass
            finally:
                lease_cm.__exit__(None, None, None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="permit one explicit normal UI upgrade click")
    parser.add_argument("--seconds", type=int, default=60, help="hard wall-time bound, 1..60 seconds")
    parser.add_argument("--out", type=Path, help="new JSONL evidence path; must not already exist")
    args = parser.parse_args(argv)
    if not 1 <= args.seconds <= 60:
        parser.error("--seconds must be between 1 and 60")
    try:
        result = asyncio.run(asyncio.wait_for(run_probe(args), timeout=args.seconds + 15))
    except asyncio.TimeoutError:
        result = {"status": "UNKNOWN", "reasons": ["PROBE_WALL_TIME_BOUND_EXPIRED"]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"READ_ONLY", "SUCCESS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
