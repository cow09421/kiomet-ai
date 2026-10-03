"""Read-only normal-panel inventory certificate for the pinned Cliff -> Quarry case."""
from __future__ import annotations

import re

from kiomet_ai.observe import TOWER_TYPES, TOWER_TYPE_RAW_CAPACITY, UNIT_NAMES
from kiomet_ai.v2.state import Units
from tools.v2_goal_upgrade_probe import (
    _known, _state_identity, _tower_visible_own, candidate_rows,
    inspect_upgrade_dom,
)


CLIFF = TOWER_TYPES.index("Cliff")
QUARRY = TOWER_TYPES.index("Quarry")
_OVERFLOW = {"Shield": 15, "Fighter": 4, "Chopper": 2, "Bomber": 2,
             "Tank": 5, "Soldier": 10, "Shell": 0, "Emp": 0,
             "Nuke": 0, "Ruler": 0}
_PUBLIC_UNIT_LABELS = ("Shield", "Fighter", "Chopper", "Bomber", "Tank",
                       "Soldier", "Shell", "EMP", "Nuke", "Ruler")
_LABEL_TO_UNIT = {label: UNIT_NAMES[i] for i, label in enumerate(_PUBLIC_UNIT_LABELS)}
_PANEL_COUNT = re.compile(r"^(0|[1-9]\d*)/(0|[1-9]\d*)$")
_MORALE_KEY = "MORALE_BOOST"


def _vector(units):
    if not isinstance(units, Units):
        return None
    pairs = units.counts
    if (len(pairs) != 10 or tuple(unit for unit, _ in pairs) != tuple(range(10)) or
            any(type(unit) is not int or type(count) is not int or
                count < 0 or count > 255 for unit, count in pairs)):
        return None
    return dict(pairs)


def _fact_value(fact, state):
    ok, value = _known(fact, state, coherent=True)
    return value if ok else None


def _public_capacity(type_id):
    table = TOWER_TYPE_RAW_CAPACITY.get(TOWER_TYPES[type_id])
    if not isinstance(table, dict):
        return {}
    # TowerType-level capacity applies to every variant before per-tower rows.
    capacities = {name: table.get(name, 0) for name in UNIT_NAMES}
    capacities["Ruler"] = 1
    return capacities


def _tower_facts(state, tower):
    source_type = _fact_value(tower.tower_type, state)
    counts = _vector(_fact_value(tower.units, state))
    capacities = _vector(_fact_value(tower.capacity, state))
    effects = _fact_value(tower.effects, state)
    effects_map = dict(effects) if isinstance(effects, (tuple, list)) else None
    delay = _fact_value(tower.delay_ticks, state)
    return source_type, counts, capacities, effects_map, delay


def _potential_own_cliff(state, tower, player_id):
    vis_ok, visible = _known(tower.visibility, state, coherent=True)
    if not vis_ok or visible is not True:
        return True
    owner_ok, owner = _known(tower.owner, state, coherent=True)
    type_ok, type_id = _known(tower.tower_type, state, coherent=True)
    if owner_ok and owner != player_id:
        return False
    if type_ok and type_id != CLIFF:
        return False
    return True


def _source_legal_reasons(state, tower):
    reasons = []
    source_type, counts, caps, effects, delay = _tower_facts(state, tower)
    if source_type != CLIFF:
        reasons.append("SOURCE_TYPE_NOT_KNOWN_CLIFF")
    if counts is None:
        reasons.append("SOURCE_UNITS_VECTOR_INCOMPLETE")
    else:
        if counts[9] != 0:
            reasons.append("SOURCE_HAS_RULER")
        source_caps = _public_capacity(CLIFF)
        for unit_id, name in enumerate(UNIT_NAMES):
            if counts[unit_id] > min(255, source_caps[name] + _OVERFLOW[name]):
                reasons.append("SOURCE_UNITS_EXCEED_PUBLIC_CAPACITY_PLUS_OVERFLOW")
                break
        if counts[0] > 45:
            reasons.append("SHIELD_INPUT_EXCEEDS_FROZEN_45_BOUND")
        if any(counts[i] != 0 for i in (6, 7, 8)):
            reasons.append("SHELL_EMP_NUKE_NOT_LEGAL_IN_CLIFF_VECTOR")
        source_caps = _public_capacity(CLIFF)
        target_caps = _public_capacity(QUARRY)
        nonshield_preserved = counts[9] == 0 and all(
            counts[i] <= min(255, target_caps[name] + _OVERFLOW[name]) and
            target_caps[name] + _OVERFLOW[name] >= source_caps[name] + _OVERFLOW[name]
            for i, name in enumerate(UNIT_NAMES) if i != 0
        )
        if not nonshield_preserved:
            reasons.append("NONSHIELD_VECTOR_NOT_PRESERVED_BY_PUBLIC_CAPACITY")
    if caps is None:
        reasons.append("SOURCE_CAPACITY_VECTOR_INCOMPLETE")
    else:
        source_caps = _public_capacity(CLIFF)
        if any(caps[i] != source_caps[name] for i, name in enumerate(UNIT_NAMES)):
            reasons.append("SOURCE_CAPACITY_DIFFERS_FROM_PINNED_PUBLIC_TABLE")
    if effects is None or effects.get(_MORALE_KEY) is not False:
        reasons.append("MORALE_NOT_KNOWN_FALSE")
    if type(delay) is not int or delay != 0:
        reasons.append("SOURCE_DELAY_NOT_KNOWN_ZERO")
    return reasons, counts, caps


def _scope_reasons(state):
    reasons = []
    if _state_identity(state) is None:
        reasons.append("CURRENT_EPOCH_OR_NETWORK_IDENTITY_UNKNOWN")
    tick_ok, tick = _known(getattr(state, "tick", None), state, coherent=True)
    if not tick_ok or type(tick) is not int or not 0 <= tick <= 0xFFFF:
        reasons.append("CURRENT_TICK_NOT_COHERENT")
    if getattr(state, "coverage", None) != "PLAYER_VISIBLE_COMPLETE":
        reasons.append("PLAYER_VISIBLE_COVERAGE_NOT_COMPLETE")
    if _fact_value(getattr(state, "coverage_evidence", None), state) is None:
        reasons.append("PLAYER_VISIBLE_COVERAGE_EVIDENCE_UNKNOWN")
    return reasons


def bounded_candidate_rows(state):
    """Narrow the old candidate set to Cliff->Quarry with the frozen clamp rule.

    Only TARGET_SHIELD_CAPACITY_LOWER is removed from the old reasons. All
    other old gates remain; exact source-vector and public overflow guards are
    added for the new, non-Ruler objective.
    """
    rows = []
    for original in candidate_rows(state):
        if original.get("source_type") != CLIFF or original.get("target_type") != QUARRY:
            continue
        row = dict(original)
        reasons = [reason for reason in original.get("reasons", ())
                   if reason != "TARGET_SHIELD_CAPACITY_LOWER"]
        tower = next((t for t in getattr(state, "towers", ())
                      if type(getattr(t, "id", None)) is int and
                      t.id == original.get("tower_id") and
                      _tower_visible_own(state, t)), None)
        if tower is None:
            reasons.append("POSITIVE_OWN_SOURCE_NOT_UNIQUE")
        else:
            extra, counts, _caps = _source_legal_reasons(state, tower)
            reasons.extend(extra)
            if counts is not None:
                after_cap = _public_capacity(QUARRY)["Shield"]
                after_with_overflow = min(255, after_cap + _OVERFLOW["Shield"])
                loss = max(0, counts[0] - after_with_overflow)
                if loss > 20:
                    reasons.append("SHIELD_LOSS_EXCEEDS_FROZEN_20_BOUND")
                row.update({"shield_before": _public_capacity(CLIFF)["Shield"],
                            "shield_after": after_cap,
                            "shield_before_max_with_overflow": 45,
                            "shield_after_max_with_overflow": after_with_overflow,
                            "shield_loss_at_current_inventory": loss,
                            "shield_loss_bound": 20,
                            "nonshield_units_preserved_for_source_legal_vector":
                                "NONSHIELD_VECTOR_NOT_PRESERVED_BY_PUBLIC_CAPACITY" not in reasons})
        reasons.extend(_scope_reasons(state))
        row["reasons"] = list(dict.fromkeys(reasons))
        row["eligible"] = not row["reasons"]
        rows.append(row)

    player_ok, player_id = _known(getattr(state, "player_id", None), state, coherent=True)
    if player_ok:
        row_ids = {r.get("tower_id") for r in rows}
        for tower in getattr(state, "towers", ()):
            if tower.id in row_ids or not _potential_own_cliff(state, tower, player_id):
                continue
            type_ok, type_id = _known(tower.tower_type, state, coherent=True)
            owner_ok, owner = _known(tower.owner, state, coherent=True)
            relation_ok, relation = _known(tower.relation, state, coherent=True)
            reasons = ["POTENTIAL_OWN_CLIFF_CANDIDATE_UNKNOWN"]
            if type_ok and type_id == CLIFF and owner_ok and owner == player_id:
                if not relation_ok or getattr(relation, "value", relation) != "SELF":
                    reasons.append("OWN_RELATION_UNKNOWN_OR_INCOHERENT")
                extra, _counts, _caps = _source_legal_reasons(state, tower)
                reasons.extend(extra)
            rows.append({"tower_id": tower.id, "source_type": type_id if type_ok else None,
                         "target_type": QUARRY, "eligible": False,
                         "reasons": list(dict.fromkeys(reasons))})
    return sorted(rows, key=lambda r: (r.get("tower_id") is None,
                                      r.get("tower_id", -1), r.get("target_type", -1)))


def _parse_rows(rows):
    if not isinstance(rows, list):
        return None, ["UNIT_ROWS_UNKNOWN"]
    parsed, reasons = {}, []
    for row in rows:
        if not isinstance(row, dict):
            reasons.append("UNIT_ROW_MALFORMED")
            continue
        name = row.get("title")
        text = row.get("text")
        match = _PANEL_COUNT.fullmatch(text) if isinstance(text, str) else None
        if name not in _LABEL_TO_UNIT:
            reasons.append("UNIT_ROW_LABEL_UNKNOWN_OR_NOT_ENGLISH")
            continue
        unit_name = _LABEL_TO_UNIT[name]
        if unit_name in parsed:
            reasons.append("UNIT_ROW_DUPLICATE")
            continue
        if match is None:
            reasons.append("UNIT_ROW_COUNT_CAPACITY_MALFORMED")
            continue
        parsed[unit_name] = (int(match.group(1)), int(match.group(2)))
        if any(v > 255 for v in parsed[unit_name]):
            reasons.append("UNIT_ROW_COUNT_OR_CAPACITY_OUT_OF_RANGE")
    return parsed, reasons


def _panel_matches_tower(panel_rows, tower, state):
    source_type, counts, caps, _effects, _delay = _tower_facts(state, tower)
    if source_type != CLIFF or counts is None or caps is None:
        return False, ["CANONICAL_SOURCE_FACTS_UNKNOWN"]
    parsed, reasons = _parse_rows(panel_rows)
    if parsed is None:
        return False, reasons
    expected_names = {"Shield"}
    expected_names.update(UNIT_NAMES[i] for i, count in counts.items() if count > 0)
    if set(parsed) != expected_names:
        reasons.append("PANEL_UNIT_ROWS_DO_NOT_MATCH_GENERATION_AND_POSITIVE_INVENTORY")
    source_caps = _public_capacity(CLIFF)
    for unit_id, name in enumerate(UNIT_NAMES):
        if name in expected_names and parsed.get(name) != (counts[unit_id], source_caps[name]):
            reasons.append("PANEL_COUNT_OR_CAPACITY_DIFFERS_FROM_CANONICAL_SOURCE")
    return not reasons, reasons


def certify_inventory_panel(state, dom, tower_id=None):
    """Match one scoped normal panel to one current own Cliff by typed inventory.

    No selected-ID/camera input is read. Freshness is checked per fact; this
    does not claim the DOM and canonical snapshot were captured atomically.
    """
    reasons = _scope_reasons(state)
    if tower_id is not None and (type(tower_id) is not int or tower_id < 0):
        reasons.append("REQUESTED_TOWER_ID_INVALID")
    panels = dom.get("panels") if isinstance(dom, dict) else None
    if not isinstance(panels, list) or not panels:
        reasons.append("SCOPED_PANEL_SET_UNKNOWN_OR_EMPTY")
        panels = []
    if isinstance(dom, dict) and dom.get("errors"):
        reasons.append("DOM_SNAPSHOT_ERRORS")
    if len(panels) != 1:
        reasons.append("SCOPED_PANEL_ROOT_NOT_UNIQUE")
    panel = panels[0] if len(panels) == 1 and isinstance(panels[0], dict) else {}
    headings = panel.get("headings")
    if not isinstance(headings, list) or len(headings) != 1 or headings[0] != "Cliff":
        reasons.append("SCOPED_SOURCE_HEADING_NOT_EXACT_CLIFF")
        headings = headings if isinstance(headings, list) else []
    button_check = inspect_upgrade_dom(
        {"headings": headings, "buttons": panel.get("buttons")}, CLIFF, QUARRY)
    if not button_check.get("eligible"):
        reasons.extend(button_check.get("reasons", ()))
    panel_rows = panel.get("unit_rows")
    parsed, parse_reasons = _parse_rows(panel_rows)
    reasons.extend(parse_reasons)

    matches, unresolved = [], []
    player_ok, player_id = _known(getattr(state, "player_id", None), state, coherent=True)
    if not player_ok:
        reasons.append("PLAYER_ID_UNKNOWN")
    else:
        bounded_rows = bounded_candidate_rows(state)
        for tower in getattr(state, "towers", ()):
            if not _potential_own_cliff(state, tower, player_id):
                continue
            owner_ok, owner = _known(tower.owner, state, coherent=True)
            type_ok, type_id = _known(tower.tower_type, state, coherent=True)
            relation_ok, relation = _known(tower.relation, state, coherent=True)
            if (not owner_ok or owner != player_id or not type_ok or type_id != CLIFF or
                    not relation_ok or getattr(relation, "value", relation) != "SELF"):
                unresolved.append(tower.id)
                continue
            candidate_match, candidate_reasons = _panel_matches_tower(panel_rows, tower, state)
            if candidate_match:
                row = next((r for r in bounded_rows if r.get("tower_id") == tower.id and
                            r.get("target_type") == QUARRY), None)
                if row is not None and row.get("eligible") is True:
                    matches.append(tower)
                else:
                    reasons.append("MATCHING_SOURCE_NOT_UPGRADE_ELIGIBLE")
            elif "CANONICAL_SOURCE_FACTS_UNKNOWN" in candidate_reasons:
                unresolved.append(tower.id)
    if unresolved:
        reasons.append("POTENTIAL_OWN_CLIFF_MATCH_NOT_EXCLUDABLE")
    if len(matches) != 1:
        reasons.append("CANONICAL_INVENTORY_MATCH_NOT_UNIQUE")
    matched_id = matches[0].id if len(matches) == 1 else None
    if tower_id is not None and matched_id != tower_id:
        reasons.append("REQUESTED_TOWER_ID_DOES_NOT_MATCH_PANEL_INVENTORY")
    reasons = list(dict.fromkeys(reasons))
    return {
        "eligible": not reasons,
        "tower_id": matched_id,
        "requested_tower_id": tower_id,
        "source_type": CLIFF,
        "target_type": QUARRY,
        "reasons": reasons,
        "panel_heading": headings[0] if len(headings) == 1 else None,
        "unit_rows": parsed,
        "upgrade_title": button_check.get("exact_title"),
        "upgrade_bbox": button_check.get("bbox"),
        "atomicity_note": "Fact freshness is per-field; panel and canonical snapshot are not atomic.",
    }


async def async_dom_snapshot(page):
    """Collect only visible ordinary panel text and affordances, scoped by DOM root."""
    try:
        return await page.evaluate("""() => {
      const visible=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();
        return !!(r.width>0&&r.height>0&&r.right>0&&r.bottom>0&&
          r.left<innerWidth&&r.top<innerHeight&&s.display!=='none'&&
          s.visibility!=='hidden'&&s.opacity!=='0');};
      const seen=new Set(),panels=[];
      for(const h of [...document.querySelectorAll('h2')].filter(visible)){
        const content=h.parentElement;
        let e=content&&content.parentElement,root=null;
        while(e&&e!==document.body){
          const directRows=content?[...content.children].filter(n=>n.tagName==='P'&&n.hasAttribute('title')&&visible(n)):[];
          const buttons=[...e.querySelectorAll('[title^="Upgrade to "]')];
          if(getComputedStyle(e).position==='absolute'&&content&&e.contains(content)&&
             content.querySelectorAll('h2').length===1&&directRows.length&&buttons.length){root=e;break;}
          e=e.parentElement;
        }
        if(!root||seen.has(root))continue;
        seen.add(root);
        const headings=[...content.querySelectorAll('h2')].filter(visible).map(n=>(n.innerText||'').trim());
        const unitRows=[...content.children].filter(n=>n.tagName==='P'&&n.hasAttribute('title')&&visible(n)).map(n=>({
          title:(n.getAttribute('title')||'').trim(),text:(n.innerText||'').trim()
        }));
        const scopedButtons=[...root.querySelectorAll('[title^="Upgrade to "]')].map(n=>{
          const r=n.getBoundingClientRect(),s=getComputedStyle(n),text=(n.innerText||'').trim();
          const descendants=[...n.querySelectorAll('*')];
          const lockMarker=descendants.some(x=>/[🔒🔐]/.test(x.innerText||'')||
            /lock/i.test((x.getAttribute('title')||'')+' '+String(x.className||'')));
          const lockGlyph=/[🔒🔐]/.test(text)||descendants.some(x=>visible(x)&&/[🔒🔐]/.test(x.innerText||''));
          const classes=String(n.className||'');
          return {title:n.getAttribute('title'),visible:visible(n),
            enabled:!n.disabled&&n.getAttribute('aria-disabled')!=='true'&&
              !/disabled/i.test(classes)&&s.cursor==='pointer',cursor:s.cursor,
            pointer_events:s.pointerEvents!=='none',locked_glyph:lockGlyph,
            hidden_lock_icon:lockMarker,bbox:[r.x,r.y,r.width,r.height]};
        });
        const rect=root.getBoundingClientRect();
        panels.push({headings,unit_rows:unitRows,buttons:scopedButtons,
          root_position:getComputedStyle(root).position,
          root_bbox:[rect.x,rect.y,rect.width,rect.height]});
      }
      return {headings:panels.flatMap(p=>p.headings),
        buttons:panels.flatMap(p=>p.buttons),panels};
        }""")
    except Exception as exc:
        return {"headings": [], "buttons": [], "panels": [],
                "errors": [type(exc).__name__]}


dom_snapshot = async_dom_snapshot
