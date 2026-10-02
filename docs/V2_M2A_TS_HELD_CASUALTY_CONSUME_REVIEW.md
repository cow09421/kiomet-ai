# Tank/Soldier held-casualty consumption

## Finding and scope

For the restricted Shield-zero, Tank/Soldier-only (enums 4 and 5), no-Ruler ordinary Tower fight with known morale, the cleanup `func1347` calls update the paired unit vector and pending-byte cursor the same way as Python `_fight.consume(last, unit)`: remove the prior held Tank/Soldier once, leave a newly selected Tank/Soldier in the vector and store its enum, or remove the prior held unit on sentinel `10` without consuming a new one. The sentinel path leaves the pending byte stale, but the cleanup iterator visits each participant only once before terminal adjudication; it performs no further same-side candidate selection after that sentinel. Python also leaves its held cursor unchanged on a no-candidate call. Both implementations therefore retain the same stale marker, which is not selected again in this bounded cleanup pass.

This proves the held-unit vector effect for the identified caller pairing and ordinary T/S categories. It does not establish full fighter-loop or world-transition equivalence, Ruler/single-use handling, air/special classes, or ordinary arrival admission. No empirical or formal case is added.

## Caller-to-vector wiring

The cleanup attacker branch passes `scratch+388` as `func1347`'s unit-vector pointer and `scratch+406` as its pending-byte pointer (`0x1b023..0x1b039` when the new candidate is sentinel 10; `0x1b058..0x1b071` when a candidate exists). The cleanup defender branch pairs `scratch+396` with `scratch+407` (`0x1b089..0x1b0a2` and `0x1b0a5..0x1b0d4`). Those same per-side pairs are used by the preceding `func3757` candidate calls at `0x1af53..0x1af6e`; `func3757` consults the matching unit vector and held-byte while finding the next pending-aware unit. The per-side pairing makes the held marker refer to the same T/S vector that is updated at cleanup.

The cleanup's fourth `func1347` parameter (zero-based `var3`) is wired across the opposing participant through the `var20` / `var8` selection at `0x1afa7..0x1afc1`. In `func1347`'s body (`0xe46dd..0xe47ec`), that cross-participant value is consulted only in the held Ruler enum-9 branch. Since both Ruler counts and held Ruler markers are excluded here, it cannot alter the T/S unit-vector update. This conclusion is limited to those categories; it does not cover the cross-enemy Ruler branch.

## `func1347` selection semantics

`func1347` receives `(combat_context, units_pointer, held_byte_pointer, opposing_context, new_unit)`. For a nonsentinel new unit it calls `Unit::is_single_use`; the `is_single_use == false` path branches out before the new-unit subtraction. Tank and Soldier are nonsingle-use in the already pinned unit classification, so a newly held T/S unit is **not** removed by this first block. For sentinel `10`, the same block also exits without subtracting or storing a new unit.

The following block reads the old held byte. Sentinel `10` skips it. A held nonsingle-use Tank or Soldier reaches `Units::subtract(units_pointer, old_unit, 1)`, removing the prior held unit exactly once. The later store writes `new_unit` into the held byte only when it is not sentinel `10`. Therefore:

| New candidate | Old held byte | Vector effect | Pending-byte effect |
| --- | --- | --- | --- |
| Tank or Soldier | Tank or Soldier | subtract old held count once; new candidate remains | overwrite with new enum |
| Tank or Soldier | `10` | no subtraction | write new enum |
| `10` | Tank or Soldier | subtract old held count once | leave old byte stale |
| `10` | `10` | no subtraction | leave sentinel |

Python `consume` performs the same vector operations for these categories: decrement `last[side]` when present, then set `last[side]` to the new candidate when one exists. On the no-candidate terminal cleanup call, Python leaves `last[side]` unchanged, exactly as the client leaves the old byte; the assignment is conditional on a new candidate being present. The participant is not selected again in this two-slot cleanup pass, and both paths have the same terminal vector. The next turn initializes a new fight scratch state, so this local stale byte is not a cross-turn assertion.

## Limits

The two-byte queue order and its zero-score correspondence are documented in `V2_M2A_TS_ZERO_SCORE_ITERATOR_ORDER_REVIEW.md`. This note checks only how the paired vector/pending cursor changes after each yielded cleanup action. It does not prove equivalence for earlier fighter selection, the single-use or Ruler branches, hidden world actors, or caller conditions outside this before-state T/S scope. Keep the broader ordinary-combat guard and all formal-credit boundaries unchanged.
