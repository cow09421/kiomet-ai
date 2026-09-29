"""Build a reviewable static call map from existing WASM metadata."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROD = ROOT / "runtime/research/source-map/production-functions.json"
LOCAL = ROOT / "runtime/research/source-map/local-functions.json"
OUT = Path(__file__).with_name("GPT_BATTLE_FUNCTION_MAP.json")

# Production ID: local ID, source counterpart, role, inputs, outputs, reads, writes, confidence.
ANNOTATIONS = {
    448: (2884, "chunk.rs:Chunk::tick", "arrival, force-tower battle, ownership, merge, collection compaction", "world/chunk/tower collections, players, tick", "updated tower/forces and events", "tower+0/+12 force vectors; tower+36 owner;+45 flag;+46 type", "tower units/owner/type/delay; force vectors", "HIGH entry; PARTIAL full battle"),
    522: (2852, "chunk.rs:force-vs-force closure + combatants.rs:Combatants::fight", "head-on force encounter and inlined fight", "inbound/outbound force, relation context", "survival predicate; units/events", "force path/owner/progress/units", "both force units and retain flag", "HIGH entry; PARTIAL exact winner"),
    788: (2850, "chunk.rs:outbound retain closure", "iterate candidate opposing outbound forces", "outbound vector, inbound force", "retain decision", "tower+12 vector, force owner/progress", "outbound vector compaction", "HIGH"),
    1845: (2977, "force.rs:Force::raw_tick", "arrival detection", "force, optional expected source", "arrived boolean", "Force+0..11 path;+14..20 units;+21 flag;+22 progress", "Force+8 path length;+22 progress", "HIGH"),
    690: (2974, "force.rs:Force::speed", "speed from unit composition and chopper carrying", "Force units", "progress per tick 1/2/3", "Force+14..20 units", "none", "HIGH"),
    2689: (None, "force.rs:Force::progress_required; production extra flag", "road-edge progress required", "Force path, +21 flag", "required progress u8", "Force+4/+8 path;+21 flag", "none", "HIGH"),
    1778: (None, "no counterpart in reference source", "production morale advantage", "Units", "clamped floor(non-single-use count/2), max 3", "Units counts", "none", "HIGH numeric result; PARTIAL activation condition"),
    2022: (None, "combatants.rs:damage_against closure", "unit damage including tower armor and nuclear overflow guard", "unit, fields, opposing tower type, sign, previous accumulated damage", "signed damage increment", "tower type; unit id; previous damage", "none", "HIGH armor/guard; PARTIAL all edge cases"),
    2408: (None, "combatants.rs:next_unit closure", "choose next combatant and field", "combatant units, prior unit, field", "unit/field pair or sentinel", "unit counts, capacity/field", "none", "PARTIAL"),
    2827: (None, "combatants.rs:next_unit_inner plus shield air handling", "special next-unit selection", "combatant, last unit, field", "unit or sentinel", "units and field", "none", "PARTIAL"),
    1347: (2934, "combatants.rs:replace_unit closure", "consume previous/single-use units and emit combat events", "combat context, side, previous/current unit", "updated last unit", "unit category; prior unit", "Units::subtract, event flags", "HIGH"),
    1348: (2936, "combatants.rs:replace_unit closure", "same specialization in head-on fight", "combat context, side, previous/current unit", "updated last unit", "unit category; prior unit", "Units::subtract, event flags", "HIGH"),
    1888: (2904, "units.rs:Units::is_alive", "claim-capable survivor check", "Units", "bool", "unit counts/types", "none", "HIGH"),
    2195: (2902, "units.rs:Units::add_units_to_tower", "merge non-single-use survivors", "tower units, arriving units, type, player/overflow flag", "mutated tower units", "both Units, type", "tower Units", "HIGH"),
    3571: (None, "tower.rs:Tower::set_player_id_inner", "owner transition and supply-line clearing", "owner pointer, supply, new owner", "mutated owner", "old/new owner", "owner and supply line", "HIGH"),
    732: (2999, "tower.rs:TowerType::raw_unit_capacity", "tower capacity lookup", "tower type, unit", "raw capacity", "static memory tables at 1362240..1363119", "none", "HIGH raw rows; PARTIAL dispatch"),
    902: (None, "units.rs:Units::add_inner", "enforce capacity and unit category", "Units, unit, count, type, overflow", "actual added count", "existing units/capacity", "Units", "HIGH role; PARTIAL bitwise details"),
    1448: (None, "units.rs:Units::subtract", "consume units", "Units, unit, count", "actual removed count", "unit count", "Units", "HIGH"),
    2127: (None, "chunk.rs:relationship closure", "classify comrade/ally/enemy", "player A/B and player context", "relationship enum", "owner IDs and alliances", "none", "HIGH"),
    4969: (None, "combatants.rs:hack closure", "remove offensive shield against tower", "tower-type sentinel, enemy Units", "none", "tower type", "enemy Shield count", "HIGH"),
    3757: (None, "combatants.rs:next_unused_unit closure", "find unused survivor", "Units and last selected unit", "unit or sentinel", "unit counts", "none", "PARTIAL"),
}


def by_id(path):
    return {int(row["index"]): row for row in json.loads(path.read_text(encoding="utf-8"))["functions"]}


def main():
    production, local = by_id(PROD), by_id(LOCAL)
    rows = []
    for idx, item in ANNOTATIONS.items():
        lid, source, role, inputs, outputs, reads, writes, confidence = item
        p = production[idx]
        l = local.get(lid) if lid is not None else None
        rows.append({
            "production_func": idx, "production_name": p.get("name"),
            "production_offset_decimal": p.get("offset"), "production_size": p.get("size"),
            "local_func": lid, "local_name": l.get("name") if l else None,
            "local_offset_decimal": l.get("offset") if l else None,
            "source_match": source, "role": role, "inputs": inputs, "outputs": outputs,
            "reads": reads, "writes": writes,
            "callers": p.get("callers", []), "callees": p.get("calls", []),
            "confidence": confidence,
        })
    OUT.write_text(json.dumps({"artifact": "GPT_BATTLE_FUNCTION_MAP", "production_wasm_sha256": "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c", "note": "Local IDs are semantic counterparts, not binary-identical implementations. None means unresolved or inlined.", "functions": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(rows)} functions; {OUT}")


if __name__ == "__main__":
    main()
