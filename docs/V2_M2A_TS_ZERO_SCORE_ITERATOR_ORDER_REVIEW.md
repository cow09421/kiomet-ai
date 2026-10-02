# Tank/Soldier zero-score cleanup iterator order

## Finding

The previously open zero-score cleanup-order question is resolved for the restricted ordinary Tower fight described below. `World::tick_before_inputs` builds a two-byte participant queue and reverses it exactly when the defender has a cleanup candidate. `func3449` visits those two bytes in order, then returns end marker `2`. This is the same condition and order as Python `_fight`'s `order=(1,0) if nexts[1] is not None else (0,1)`. At score zero, both side branches are eligible, so this queue order proves the Python ordering at the tie boundary.

This closes only cleanup iterator ordering for a Shield-zero, Tank/Soldier-only ordinary Tower fight with no Ruler, air, or special units and known morale. It does not extend to other fighter classes, Shield-retaining combat, unknown morale, complete force arrival, unrelated world actions, or all ordinary combat. No before-only counterexample was found; no empirical case or formal credit was created.

Pinned WASM SHA-256: `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`. Static disassembly only. The inspection stayed within three additional function bodies: `func4062`, `func5202`, and `func3757`.

## Queue state before the first yield

In `World::tick_before_inputs`, the two `func3757` calls immediately before cleanup produce the attacker's and defender's first cleanup candidates, with sentinel `10` meaning no candidate. `func3757` is called for the attacker at `0x1af61` and defender at `0x1af6e` and constructs `Units::iter_with_zeros`; `UnitIter::next` visits unit enums in ascending order. Its pending-aware availability call is already covered by the preceding damage-queue review. Under the present preconditions, its first non-sentinel result is Tank enum 4 if any Tank remains unused, otherwise Soldier enum 5 if any Soldier remains unused, otherwise 10. The defender result becomes local `var4` at `0x1af7a..0x1af7e`.

At `0x1af71..0x1af76`, the routine writes `0x0100` (little-endian bytes `[0,1]`) at scratch `+416`. If the defender's candidate is not sentinel 10, the conditional at `0x1af80..0x1af83` calls `func5202`. That function swaps the two bytes at its pointer (`runtime/research/v2/disassembly.json`, function body `func5202`), making the queue `[1,0]`. If the defender has no candidate, no swap occurs and the queue remains `[0,1]`. The copied queue at scratch `+428` is therefore:

| Defender's pending-aware candidate | Queue before iteration | First cleanup participant |
| --- | --- | --- |
| Tank or Soldier | `[1,0]` after the swap | defender |
| sentinel `10` | `[0,1]` unchanged | attacker |

At `0x1af9b..0x1afa7`, the routine initializes the iterator state at scratch `+420` with `i64.const 8589934592`: current index 0 and end index 2. Thus its first two reads address queue bytes at `+428` and `+429`; the third read is exhausted.

## Yield sequence and Python correspondence

`func3449` is called for the first cleanup read at `0x1afd5`. It passes terminal code `2` to `func6761`. That adapter calls `func4062`, which compares current and end indices, returns the old index when an item exists, and increments the state index. When present, `func6761` reads the queue byte at base `+428` plus that index; when exhausted it returns the supplied sentinel `2`.

The enclosing `br_table` at `0x1afc3..0x1afdc` maps queue tag `0` to the attacker cleanup path and tag `1` to the defender path; tag `2` reaches terminal adjudication. Tag `3` has a defender-path mapping but cannot occur in this constructed two-byte queue. The second `func3449` read returns the other queue byte, and the third returns `2`.

Python computes `nexts` from each side's `unused` units after excluding its held `last[side]` selection. Its `order` is defender-first precisely when the defender candidate exists; otherwise it is attacker-first. The pinned queue uses the defender candidate's sentinel test to make exactly that choice. When damage is zero, the attacker's `damage > 0` skip and defender's `damage < 0` skip are both false, so both queued participant branches are eligible in the same order Python selects. The fighter callsites invoke `func1347` with held and selected unit values, but this iterator-order review does not prove all of those caller-argument and cross-enemy consumption effects equal Python's `consume`/`last` update.

The end-marker result check and all terminal T/S-vector cases remain as mapped in `V2_M2A_ORDINARY_TERMINAL_RESULT_REVIEW.md`. This review closes the iterator-order gap noted in `V2_M2A_TS_CLEANUP_LOOP_EQUIVALENCE_REVIEW.md`; it does not independently prove the earlier fighter-selection phase or the world-level ordinary-combat admission conditions.
