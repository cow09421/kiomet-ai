"""戰術世界圖後端資料（P1 §7）。

由真實後端資料組出完整 payload：塔所有者、移動部隊、ETA、受威脅塔、
最近／規劃行動、攻擊／增援／擴張路徑。威脅資料必須同局且標為 FRESH；
缺資料保留 UNKNOWN，不猜。

純函式；不觸碰 index.html 或 app.py（皆為外部施工路徑）。
"""
from __future__ import annotations

OWNERS = ("SELF", "NEUTRAL", "ENEMY", "ALLY", "UNKNOWN")
ROUTE_KINDS = ("ATTACK", "REINFORCE", "EXPAND", "UNKNOWN")


def classify_route(source_owner, target_owner) -> str:
    """由來源／目標所有者判斷路徑種類（僅己方發起才是行動）。"""
    src = source_owner if source_owner in OWNERS else "UNKNOWN"
    tgt = target_owner if target_owner in OWNERS else "UNKNOWN"
    if src not in ("SELF", "ALLY"):
        return "UNKNOWN"
    if tgt == "ENEMY":
        return "ATTACK"
    if tgt == "NEUTRAL":
        return "EXPAND"
    if tgt in ("SELF", "ALLY"):
        return "REINFORCE"
    return "UNKNOWN"


def _tower_owner(owner_lookup, tower_id):
    if isinstance(owner_lookup, dict) and tower_id in owner_lookup:
        value = owner_lookup[tower_id]
        return value if value in OWNERS else "UNKNOWN"
    return "UNKNOWN"


def _normalize_towers(towers) -> list:
    out = []
    for t in towers or []:
        if not isinstance(t, dict):
            continue
        x = t.get("x")
        if x is None:
            pos = t.get("position")
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                x, y = pos[0], pos[1]
            else:
                x, y = None, None
        else:
            y = t.get("y")
        owner = t.get("owner")
        owner = owner if owner in OWNERS else "UNKNOWN"
        out.append({"id": t.get("id", t.get("packed_id")), "x": x, "y": y,
                    "owner": owner, "tower_type": t.get("tower_type")})
    return out


def _moving_forces(threat_state, owner_lookup, current_match_id) -> tuple:
    """回傳 (moving_forces, threatened, moving_status)。"""
    threats = []
    threatened: dict = {}
    if not isinstance(threat_state, dict):
        return threats, [], "UNKNOWN"

    threat_match_id = threat_state.get("match_id")
    freshness = threat_state.get("freshness")
    if (current_match_id is None or threat_match_id is None
            or freshness not in ("FRESH", "STALE")):
        return threats, [], "UNKNOWN"
    if threat_match_id != current_match_id or freshness == "STALE":
        return threats, [], "STALE"

    status = threat_state.get("status")
    if status not in ("OBSERVED_CANDIDATE", "CLEAR"):
        return threats, [], "UNKNOWN"
    rows = threat_state.get("threats")
    if (not isinstance(rows, list) or any(not isinstance(row, dict)
                                          for row in rows)
            or (status == "OBSERVED_CANDIDATE" and not rows)
            or (status == "CLEAR" and rows)):
        return threats, [], "UNKNOWN"
    for row in rows:
        src = row.get("source_tower_id")
        tgt = row.get("target_tower_id")
        relation = row.get("owner_relation")
        relation = relation if relation in OWNERS else "UNKNOWN"
        eta_ok = (row.get("eta_status") == "CANDIDATE"
                  and isinstance(row.get("eta_seconds"), (int, float))
                  and row.get("eta_seconds") >= 0)
        eta = row.get("eta_seconds") if eta_ok else None
        forces = [{"source": src, "target": tgt,
                   "owner_relation": relation, "eta_seconds": eta}]
        threats.extend(forces)
        if tgt is not None:
            entry = threatened.setdefault(tgt, {"tower": tgt,
                                               "eta_seconds": eta,
                                               "sources": []})
            if src is not None:
                entry["sources"].append(src)
            if eta is not None and (
                    entry["eta_seconds"] is None
                    or eta < entry["eta_seconds"]):
                entry["eta_seconds"] = eta
    return threats, list(threatened.values()), "KNOWN"


def build_tactical(payload: dict | None) -> dict:
    """組出戰術世界 payload。缺資料一律 UNKNOWN，不補 0。

    所有權數量只有在 ``towers_complete`` 明確為 ``True``，且輸入含塔資料
    清單時才視為完整可信。
    """
    payload = payload if isinstance(payload, dict) else {}
    match_id = payload.get("match_id")
    towers = _normalize_towers(payload.get("towers"))
    owner_lookup = payload.get("owner_lookup")
    if not isinstance(owner_lookup, dict):
        owner_lookup = {t["id"]: t["owner"] for t in towers
                        if t["id"] is not None}
    edges = [e for e in (payload.get("edges") or []) if isinstance(e, list)]
    moving, threatened, moving_status = _moving_forces(
        payload.get("threat_state"), owner_lookup, match_id)

    counts = {o: 0 for o in OWNERS}
    for t in towers:
        counts[t["owner"]] += 1
    # 輸入清單可能不完整；只有明確標示完整時，缺少的陣營才是已知零。
    owner_counts_known = (
        payload.get("towers_complete") is True
        and isinstance(payload.get("towers"), list)
        and all(isinstance(tower, dict) for tower in payload["towers"])
    )
    owners = (counts if owner_counts_known
              else {owner: None for owner in OWNERS})

    routes = {kind: [] for kind in ROUTE_KINDS}
    sources = []
    proposal = payload.get("current_proposal")
    if isinstance(proposal, dict) and proposal.get("source") is not None:
        sources.append(("planned", proposal.get("source"),
                        proposal.get("target")))
    last = payload.get("last_action")
    if isinstance(last, dict) and last.get("source") is not None:
        sources.append(("last", last.get("source"), last.get("target")))
    for label, src, tgt in sources:
        kind = classify_route(_tower_owner(owner_lookup, src),
                              _tower_owner(owner_lookup, tgt))
        routes[kind].append({"origin": label, "source": src, "target": tgt})

    return {
        "match_id": match_id,
        "towers": towers,
        "edges": edges,
        "moving_forces": moving,
        "moving_status": moving_status,
        "threatened": threatened,
        "owners": owners,
        "owner_count_status": ("KNOWN" if owner_counts_known else "UNKNOWN"),
        "routes": routes,
        "planned_action": ({"source": proposal.get("source"),
                            "target": proposal.get("target")}
                           if isinstance(proposal, dict) else None),
        "last_action": ({"source": last.get("source"),
                         "target": last.get("target")}
                        if isinstance(last, dict) else None),
        "fidelity": "REAL_BACKEND_DATA",
    }
