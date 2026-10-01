"""Finite offline inventory of scoped, independent official DOM comparisons.

No game access. Never turns historical diagnostics into a whole-state M1 PASS.
"""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c"


def inventory(paths):
    fields = {}
    excluded = Counter()
    reports = []
    eligible = 0
    selections = set()

    def add(base, family, label, coherent, matched, observed, expected, group):
        if coherent is not True:
            excluded[f"incoherent:{family}"] += 1
            return
        key = (*base, family, label)
        value = json.dumps([observed, expected], sort_keys=True, ensure_ascii=False)
        item = fields.setdefault(key, {"match": True, "values": set(), "groups": set(), "reads": 0})
        # Retain every mismatch and every conflicting repeated observation.
        item["match"] &= matched is True
        item["values"].add(value)
        item["groups"].add(group)
        item["reads"] += 1

    for path in paths:
        blob = path.read_bytes()
        report = json.loads(blob)
        reports.append({"file": path.name, "sha256": hashlib.sha256(blob).hexdigest(),
                        "rows": len(report.get("rows", [])), "errors": report.get("errors", []),
                        "source_manifest_present": bool(report.get("observer_source_manifest"))})
        for row in report.get("rows", []):
            required = ("document_time_origin", "player_id", "client_sha256", "source_mode",
                        "tick_bracket", "match_epoch", "selection_confirmed", "id")
            if any(row.get(k) is None for k in required) or not row.get("match_epoch"):
                excluded["missing_scope_or_epoch"] += 1
                continue
            ticks = row["tick_bracket"]
            if (row["client_sha256"] != PIN or row["source_mode"] != "NETWORK"
                    or row["selection_confirmed"] is not True or not isinstance(ticks, list)
                    or len(ticks) != 2 or not all(isinstance(t, int) for t in ticks)):
                excluded["unverified_source_or_selection"] += 1
                continue
            eligible += 1
            # Epoch tokens are observer-local; use physical document/player/revision
            # to deduplicate across observers. These bounded cohorts do not span a
            # full u16 wrap in the same document; no elapsed time inferred from it.
            base = (row["document_time_origin"], row["player_id"], ticks[-1], row["id"])
            selections.add(base)
            group = f"{row.get('relation')}:{row.get('units_kind')}"
            for c in row.get("comparisons", []):
                add(base, "unit_count", c["unit"], c.get("coherent"), c.get("match"),
                    c.get("ui"), c.get("memory"), group)
                add(base, "capacity", c["unit"], c.get("coherent"), c.get("capacity_match"),
                    c.get("capacity_ui"), c.get("capacity_memory"), group)
            for family, name, ui, expected in (
                    ("relation", "relation_check", "ui_fill", "expected_fill"),
                    ("tower_type", "type_check", "ui_type", "expected_type"),
                    ("delay_progress", "progress_check", "ui_percent", "expected_percent")):
                c = row.get(name, {})
                add(base, family, "tower", c.get("coherent"), c.get("match"),
                    c.get(ui), c.get(expected), group)
            for c in row.get("prerequisite_comparisons", []):
                add(base, "prerequisite_count", str(c["type"]), c.get("coherent"),
                    c.get("count_match"), c.get("ui_have"), c.get("observed_have"), group)
                # Requirement match has a boolean proof, but historical reports
                # omit the rule's expected numeric value. Report this separately.
                add(base, "prerequisite_requirement_flag", str(c["type"]), c.get("coherent"),
                    c.get("requirement_match"), c.get("ui_need"), None, group)
            for c in row.get("upgrade_ui_comparisons", []):
                add(base, "upgrade_disabled", str(c["target_type"]), c.get("coherent"),
                    c.get("disabled_match"), c.get("ui_disabled"),
                    None if c.get("prerequisites_met") is None else not c["prerequisites_met"], group)
                add(base, "upgrade_lock", str(c["target_type"]), c.get("lock_coherent"),
                    c.get("lock_match"), c.get("ui_locked"), c.get("derived_locked"), group)
    families = defaultdict(Counter)
    unit_strata = defaultdict(Counter)
    for key, item in fields.items():
        family = families[key[-2]]
        conflict = len(item["values"]) > 1 or len(item["groups"]) > 1
        family["unique"] += 1
        family["matched"] += int(item["match"])
        family["conflicting_repeats"] += int(conflict)
        family["reads"] += item["reads"]
        if key[-2] == "unit_count":
            group = next(iter(item["groups"])) if len(item["groups"]) == 1 else "CONFLICT"
            unit_strata[group]["unique"] += 1
            unit_strata[group]["matched"] += int(item["match"])
    return {"status": "PARTIAL", "reports": reports, "eligible_rows": eligible,
            "unique_selections": len(selections), "excluded": dict(excluded),
            "families": dict(families), "unit_strata": dict(unit_strata),
            "limits": "Independent DOM field pairs only; no whole-state accuracy, server age, "
                      "fog-cycle, moving-force or lifecycle coverage implied. Single layout strata "
                      "do not prove every Single unit's count; only actual DOM rows count."}


if __name__ == "__main__":
    folder = ROOT / "runtime/research/v2"
    paths = sorted(folder.glob("ui-comparison-????????????.json"))
    result = inventory(paths)
    result["tool_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    path = folder / "validation-inventory.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8")
    print(json.dumps({k: v for k, v in result.items() if k != "reports"}, ensure_ascii=False))
