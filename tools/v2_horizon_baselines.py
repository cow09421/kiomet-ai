"""Pinned offline continuous horizon survival and fixed trivial baselines.

No state resets, action inference, endpoint completion or production changes.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import v2_coverage_denominator as coverage
VERSION = "horizon-baselines-v1"
HORIZONS = (1, 2, 4, 8, 16, 20)
METHOD = ROOT / "docs/V2_M2A_ENDPOINT_AUDIT_METHOD.md"


def git_state():
    cmd = ["git", "-c", "safe.directory=E:/SteamLibrary/kiomet"]
    read = lambda *a: subprocess.check_output(cmd + list(a), cwd=ROOT, text=True).rstrip("\r\n")
    status = read("status", "--porcelain=v1", "--untracked-files=all")
    return {"head": read("rev-parse", "HEAD"), "dirty": bool(status), "status_porcelain": status.splitlines()}


def _slim(raw):
    value = coverage._value
    towers = {t["id"]: {"owner": value(t.get("owner")), "units": coverage._count_vector(t.get("units"))}
              for t in raw.get("towers", []) if isinstance(t, dict) and type(t.get("id")) is int
              and value(t.get("visibility")) is True}
    rows = value(raw.get("forces"))
    force_counts = collections.Counter(value(f.get("id")) for f in rows or [])
    forces = {}
    for f in rows or []:
        ident = value(f.get("id"))
        if not isinstance(ident, str) or force_counts[ident] != 1 or value(f.get("visibility")) is not True:
            continue
        forces[ident] = {k: value(f.get(k)) for k in
                         ("owner", "source", "destination", "progress", "eta_ms", "confidence")}
        forces[ident]["units"] = coverage._count_vector(f.get("units"))
    return {"towers": towers, "forces": forces, "force_count": len(rows) if isinstance(rows, list) else None}


def velocity_prediction(previous, current):
    """Two before-only samples, reliable unchanged current leg, no fallback."""
    names = ("owner", "source", "destination", "units")
    if not previous or not current or current.get("confidence") != "UNIQUE_CONTINUATION":
        return None
    if any(previous.get(k) is None or previous.get(k) != current.get(k) for k in names):
        return None
    p, c = previous.get("progress"), current.get("progress")
    if type(p) is not int or type(c) is not int or c < p:
        return None
    return min(255, c + c - p)


def _continuous(rows, index, step_fn=None, signature_fn=None):
    step_fn = step_fn or coverage.step
    signature_fn = signature_fn or coverage.signature
    predicted = rows[index]["sim"]
    clean = 0
    stop = None
    for offset in range(1, max(HORIZONS) + 1):
        if index + offset >= len(rows):
            stop = {"offset": offset, "kind": "RIGHT_CENSORED_RECORDING_END", "reason": "RECORDING_END"}
            break
        before, after = rows[index + offset - 1], rows[index + offset]
        if (before["scope"] != after["scope"] or type(before["tick"]) is not int
                or type(after["tick"]) is not int or (after["tick"] - before["tick"]) % 65536 != 1):
            stop = {"offset": offset, "kind": "CENSORED_BY_UNKNOWN", "reason": "OBSERVATION_SCOPE_OR_TICK_GAP"}
            break
        try:
            predicted = step_fn(predicted)
        except coverage.UnsupportedState as exc:
            stop = {"offset": offset, "kind": "CENSORED_BY_UNKNOWN", "reason": coverage._error_code(exc)}
            break
        if after["sim"] is None:
            stop = {"offset": offset, "kind": "CENSORED_BY_UNKNOWN", "reason": "OBSERVED_ENDPOINT:" + after["reason"]}
            break
        if signature_fn(predicted) != signature_fn(after["sim"]):
            stop = {"offset": offset, "kind": "MISMATCH", "reason": "EXACT_OBSERVABLE_SIGNATURE_MISMATCH"}
            break
        clean += 1
    return {"clean_ticks": clean, "first_stop": stop,
            "outcomes": {str(h): "EXACT_MATCH" if clean >= h else stop["kind"] for h in HORIZONS}}


def _metric(counter, prefix, prediction, observed):
    if prediction is None or observed is None:
        return
    counter[prefix + ":pairs"] += 1
    counter[prefix + ":exact"] += prediction == observed
    counter[prefix + ":absolute_error"] += abs(prediction - observed)


def _baselines(rows, edge_map):
    c = collections.Counter()
    for i in range(len(rows) - 1):
        before, after = rows[i], rows[i + 1]
        edge = edge_map[i + 1]
        if not edge["same_scope_consecutive"]:
            c["excluded_gap_edges"] += 1
            continue
        c["all_consecutive_edges"] += 1
        shared = edge["comparison_status"] in ("SUCCESS", "MISMATCH")
        b, a = before["slim"], after["slim"]
        prediction = None
        if shared:
            prediction = coverage.step(before["sim"])
            assert prediction is not None and after["sim"] is not None
        pt = {t.id: t for t in prediction.towers} if prediction else {}
        for ident in b["towers"].keys() & a["towers"].keys():
            bo, ao = b["towers"][ident]["owner"], a["towers"][ident]["owner"]
            if type(bo) is not int or type(ao) is not int:
                continue
            _metric(c, "static_owner:broader", bo, ao)
            if bo != ao:
                _metric(c, "static_owner:owner_changed", bo, ao)
            if shared and ident in pt:
                _metric(c, "static_owner:shared", bo, ao)
                _metric(c, "sim_owner:shared", pt[ident].owner, ao)
                if bo != ao:
                    _metric(c, "sim_owner:owner_changed_shared", pt[ident].owner, ao)
        if type(b["force_count"]) is int and type(a["force_count"]) is int:
            _metric(c, "no_new_force_count:broader", b["force_count"], a["force_count"])
            if shared:
                _metric(c, "no_new_force_count:shared", b["force_count"], a["force_count"])
                _metric(c, "sim_force_count:shared", len(prediction.forces), a["force_count"])
        previous = rows[i - 1] if i else None
        continuous_previous = previous and previous["scope"] == before["scope"] and (before["tick"] - previous["tick"]) % 65536 == 1
        predicted_forces = collections.defaultdict(list)
        for f in prediction.forces if prediction else ():
            predicted_forces[(f.owner, f.source, f.destination, f.units)].append(f)
        for ident in b["forces"].keys() & a["forces"].keys():
            bf, af = b["forces"][ident], a["forces"][ident]
            if af["confidence"] != "UNIQUE_CONTINUATION" or any(bf[k] is None or bf[k] != af[k] for k in ("owner", "source", "destination", "units")):
                continue
            if type(af["progress"]) is not int:
                continue
            past = previous["slim"]["forces"].get(ident) if continuous_previous else None
            v = velocity_prediction(past, bf)
            _metric(c, "constant_velocity:broader", v, af["progress"])
            eta = max(0, bf["eta_ms"] - 250) if type(bf["eta_ms"]) is int else None
            _metric(c, "eta_countdown_estimator:broader", eta, af["eta_ms"])
            key = tuple(bf[k] for k in ("owner", "source", "destination", "units"))
            pred = predicted_forces.get(key, ())
            if shared and len(pred) == 1 and v is not None:
                _metric(c, "constant_velocity:shared", v, af["progress"])
                _metric(c, "sim_progress:shared", pred[0].progress, af["progress"])
                if eta is not None and type(af["eta_ms"]) is int and pred[0].accelerated is not None:
                    _metric(c, "eta_countdown_estimator:shared", eta, af["eta_ms"])
                    sp, dp = {t.id: t.position for t in prediction.towers}[pred[0].source], {t.id: t.position for t in prediction.towers}[pred[0].destination]
                    sim_eta = coverage.motion(coverage.Units(tuple(enumerate(pred[0].units))), sp, dp, pred[0].accelerated, pred[0].progress)[2]
                    _metric(c, "sim_eta_estimator:shared", sim_eta, af["eta_ms"])
    return dict(c)


def _load(path):
    result = []
    last = None
    raw_records = 0
    with path.open("rb") as stream:
        h = hashlib.sha256()
        for line_number, line in enumerate(stream, 1):
            h.update(line)
            raw_records += 1
            raw = json.loads(line)
            scope, tick = coverage._scope(raw), coverage._value(raw.get("tick"))
            key = (scope, tick)
            if type(tick) is int and key == last:
                continue
            last = key if type(tick) is int else None
            sim, reason = None, None
            try:
                sim = coverage.from_canonical(coverage.state_from_dict(raw))
            except coverage.UnsupportedState as exc:
                reason = coverage._error_code(exc)
            result.append({"line": line_number, "sequence": raw.get("sequence"), "scope": scope,
                           "tick": tick, "sim": sim, "reason": reason, "slim": _slim(raw)})
    return result, {"raw_records": raw_records, "sha256": h.hexdigest(), "retained": len(result)}


def run(output):
    doc_path = ROOT / "docs/V2_M2A_COVERAGE_DENOMINATOR.json"
    doc = json.loads(doc_path.read_text(encoding="utf8"))
    audit_path = ROOT / doc["edge_audit"]["path"]
    assert coverage._sha256(audit_path) == doc["edge_audit"]["sha256"]
    edges = collections.defaultdict(dict)
    for line in gzip.decompress(audit_path.read_bytes()).splitlines():
        edge = json.loads(line)
        edges[edge["cohort"]][edge["edge_index"]] = edge
    result = {"analysis_version": VERSION, "git": git_state(), "method_sha256": coverage._sha256(METHOD),
              "method": {"start_eligibility": "unchanged from_canonical succeeds; every retained origin inventoried",
                         "forecast": "continuous default no-action step, no resets, no shadow or inferred actions",
                         "horizons": HORIZONS, "baselines": "before-only fixed static owner, unchanged force count, two-sample current-leg velocity, nominal 250ms ETA countdown",
                         "eta_truth": "estimator agreement only; actual arrival error UNKNOWN"},
              "source_hashes": {p.relative_to(ROOT).as_posix(): coverage._sha256(p) for p in sorted((ROOT / "src/kiomet_ai/v2").rglob("*.py"))},
              "tool_sha256": coverage._sha256(Path(__file__)), "cohorts": []}
    detail = []
    for c in doc["cohorts"]:
        cohort = c["cohort"]
        path = ROOT / f"runtime/research/v2/snapshots-{cohort}.jsonl"
        rows, inventory = _load(path)
        expected = next(v["expected_sha256"] for v in doc["inputs"]["raw_files"].values() if v["cohort"] == cohort)
        assert inventory["sha256"] == expected
        assert len(rows) - 1 == len(edges[cohort])
        counts = collections.Counter()
        by_horizon = {str(h): collections.Counter() for h in HORIZONS}
        stops = collections.Counter()
        for i, row in enumerate(rows):
            counts["retained_origins"] += 1
            if row["sim"] is None:
                counts["ineligible:" + row["reason"]] += 1
                continue
            counts["legal_origins"] += 1
            trajectory = _continuous(rows, i)
            for h, outcome in trajectory["outcomes"].items():
                by_horizon[h][outcome] += 1
            if trajectory["first_stop"]:
                stops[trajectory["first_stop"]["kind"] + ":" + trajectory["first_stop"]["reason"]] += 1
            detail.append({"cohort": cohort, "split": c["split"], "origin_line": row["line"], "origin_sequence": row["sequence"],
                           "origin_tick": row["tick"], "first_edge_activity": edges[cohort].get(i + 1, {}).get("active", "NO_FUTURE_EDGE"), **trajectory})
        entry = {"cohort": cohort, "split": c["split"], "inventory": inventory, "counts": dict(counts),
                 "horizons": {h: dict(v) for h, v in by_horizon.items()}, "first_stops": dict(stops), "baselines": _baselines(rows, edges[cohort])}
        result["cohorts"].append(entry)
        print(json.dumps({"cohort": cohort, "counts": entry["counts"]}), flush=True)
    total = collections.Counter()
    bases = collections.Counter()
    horizon = {str(h): collections.Counter() for h in HORIZONS}
    stops = collections.Counter()
    for c in result["cohorts"]:
        total.update(c["counts"]); bases.update(c["baselines"]); stops.update(c["first_stops"])
        for h, v in c["horizons"].items():
            horizon[h].update(v)
    result["totals"] = {"counts": dict(total), "horizons": {h: dict(v) for h, v in horizon.items()}, "first_stops": dict(stops), "baselines": dict(bases)}
    by_activity = {}
    for activity in ("ACTIVE_KNOWN", "ACTIVE_UNKNOWN", "INACTIVE", "NO_FUTURE_EDGE"):
        selected = [r for r in detail if r["first_edge_activity"] == activity]
        by_activity[activity] = {"legal_origins": len(selected), "horizons": {
            str(h): dict(collections.Counter(r["outcomes"][str(h)] for r in selected)) for h in HORIZONS}}
    result["totals"]["by_first_edge_activity"] = by_activity
    audit = output.with_suffix(".starts.jsonl.gz")
    payload = b"".join((json.dumps(v, separators=(",", ":")) + "\n").encode() for v in detail)
    audit.write_bytes(gzip.compress(payload, mtime=0))
    result["start_audit"] = {"path": audit.relative_to(ROOT).as_posix(), "sha256": coverage._sha256(audit), "rows": len(detail)}
    result["git_after"] = git_state()
    result["tool_hash_stable"] = result["tool_sha256"] == coverage._sha256(Path(__file__))
    result["source_hashes_stable"] = all(coverage._sha256(ROOT / p) == h for p, h in result["source_hashes"].items())
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/research/v2/horizon-baselines-candidate.json")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    run(args.output.resolve())


if __name__ == "__main__":
    main()
