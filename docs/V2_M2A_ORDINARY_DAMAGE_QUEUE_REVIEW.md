# M2A pinned ordinary Tank/Soldier combat review

## Scope and result

This review compares `src/kiomet_ai/v2/sim/combat.py`'s ground-fight loop with the pinned client combat path. The bounded fighter-entry vector contains Tank and Soldier only: Shield is already exhausted (`unit 0 == 0` on both sides), and Fighter/Chopper/Bomber, air, special, and Ruler counts are zero. Attacker and defender morale booleans are known. If the defender is a Tower, `fight_ordinary` also receives a capacity vector, but its equivalence to any separate postfight Tower capacity inputs is **UNKNOWN**.

Within that narrowed fighter loop, I found no specific divergence in Tank/Soldier enum order, damage, or pending-casualty handling. The static path supports Tank enum 4 before Soldier enum 5, Tank's +3 signed damage and Soldier's +1, and a cumulative score carried through the surface loop. This is a partial fight-loop result only; it does not establish ordinary attacker-winning capture or a complete arrival transition.

Artifact pin: WASM SHA-256 `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`; offsets below are WASM byte offsets. No WASM execution, host action, or hidden-state read was used.

## Fighter selection and damage

`World::tick_before_inputs` builds the fight context at `0x1ac56..0x1ad06`: it stores the two unit-vector pointers, current Tower morale/field inputs, and initializes the signed running damage value. For the bounded T/S-only case, the normal selector uses `func2408` (`0x114146`) and `func1185` (`0xc811a`). `func1185` iterates the unit vector from its start, asks for each enum's available count, and returns the first available unit that meets the requested field. `Units::iter_with_zeros` initializes that iterator at zero (`0x14e724`); the iterator advances by enum (`UnitIter::next`, `0x13b9f9`). Thus, with only enums 4 and 5 available and both on the surface, selection is Tank 4 first, then Soldier 5. `Unit::field` (`0x14178d`) gives both units field 0 independent of overflow/air flags, so capacity does not reorder these two categories in this phase.

The pinned scalar values agree with the simulator: `Unit::damage` (`0x126c57`) returns 3 for Tank 4 and 1 for Soldier 5 in the surface case; `func2022` (`0x1091da`) obtains this damage and applies it to the signed fight score. The fight initializes the score from the morale difference at `0x1acda..0x1ad06`, then carries it forward through selection and damage. In particular, the loop adds the field-phase result back to the same score at `0x1af4a..0x1af4b`; there is no score reset before the subsequent cleanup loop. The simulator likewise carries one `damage` value through its field loops. `Combatants::morale_advantage` (`0xffab8`) counts available non-single-use units and applies the capped half-count bonus; for the restricted T/S-only vectors that is the Tank/Soldier headcount used by `_fight`.

## Pending casualties

The combat scratch state initializes two pending-unit bytes to enum sentinel 10 (`0x1ad08..0x1ad30`). Selection accounts for a pending unit before treating it as available: `func3758` (`0x13cec9`) adjusts the available count when the queried enum matches the held enum, and returns sentinel 10 when that leaves no unit. `func1347` (`0xe46dd..0xe47ec`) processes the selected combat step, uses `Units::subtract` (`0xedecc`) for casualty removal, and stores the current enum back to the pending byte at `0xe47e4..0xe47e8`. For T/S, this is the held-selection/deferred-removal pattern represented by `_fight.consume`'s `last[side]`: the prior held selection is excluded from availability, then resolved as selection advances. Classification is pinned: `Unit::range` (`0x14510e`) returns 3 for enums 4/5, `Unit::ranged_distance` (`0x14145d`) maps range 3 to the non-ranged flag, and `Unit::is_single_use` (`0x14170f`) tests that flag. Tank/Soldier take the ordinary non-single-use path here.

These findings support only the bounded fighter mechanics, not every branch in `_fight`. They require Shield already zero at fighter entry and do not extend to air/special categories, Ruler elimination, or unknown morale inputs.

## Empty-defender versus ordinary outcome control flow

The earlier draft incorrectly treated `Tower::set_player_id_inner` at `0x1ac21` and `Units::reconcile` at `0x1ac38` as universal ordinary-fight aftermath. The pinned structured control flow shows this is the **empty-defender transfer branch**: it tests the defender vector with `Units::is_empty` at `0x1abaf..0x1abb5` and, on that path, transfers ownership and reconciles the defender vector before leaving the branch at `0x1ac3b`. That call does not establish behavior for a nonempty defended Tower that reaches the ordinary fighter loop. The missing-reconcile bug claim is withdrawn.

The ordinary fight's owner setter is later at `0x1b21d..0x1b223`, after the combat result and event branches (`0x1afee..0x1b20d`). The nearby logic then repairs Tower type metadata (`0x1b22d..0x1b25a`); there is no `Units::reconcile` call in this ordinary owner-setter path. A later common postlude can call `Units::add_units_to_tower` (`0x1b43e..0x1b45b`) for the arriving force. That addition is capacity-aware, but the present review has not established that `fight_ordinary`'s `dst.capacity` exactly matches its inputs or that the complete ordinary capture/postlude transition matches `step.py`.

Consequently, no core fix is proposed from this review. Ordinary attacker-winning aftermath, including the transfer branch's exact result vector and all effective capacity behavior, remains **UNKNOWN** pending a separate structured trace or before-only counterexample. Do not infer that `dst.capacity` is a valid substitute for the Tower parameters consumed by the empty-defender reconciliation call.

## Admission limits

For a future local fighter-loop use, require valid known vectors with only Tank/Soldier nonzero, Shield already zero at fighter entry, and known attacker/defender morale booleans. A Tower capacity vector may be needed by `fight_ordinary`; this review does not validate its mapping into all pinned postfight inputs. These conditions do not establish force arrival timing, route/fuel validity, absence of unrelated world changes, capture admissibility, or the next Tower's production/capacity result. The existing shield-retaining proof is a separate case and does not validate the post-Shield-exhaustion T/S loop or attacker-winning aftermath.
