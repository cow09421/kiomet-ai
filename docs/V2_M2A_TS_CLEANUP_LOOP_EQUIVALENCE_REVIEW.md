# M2A ordinary Tank/Soldier cleanup-loop equivalence

## Scope and finding

This review follows the pinned Tower-fight cleanup iterator at `func3449`, its one immediate callee, and the `World::tick_before_inputs` loop at `0x1afc3..0x1b0ef`. The only supported fighter-entry shape here is a nonempty Force and defended Tower with ten-element byte-count vectors, Shield zero on both sides, only Tank (enum 4) and Soldier (enum 5) counts possibly nonzero, no Ruler, air, or special units, and independently known morale booleans. This review does not relax the ordinary-combat guard.

The pinned cleanup code confirms deferred removal of each side's held selection, cumulative signed damage through cleanup, sign-conditioned cleanup of an additional Tank/Soldier selection, and the terminal-result truth table already documented in `V2_M2A_ORDINARY_TERMINAL_RESULT_REVIEW.md`. I did **not** close exact iterator yield order for the zero-score case within the requested one-callee limit. Both side branches are eligible at score zero, so their queued order can affect terminal vectors and score. The Python `nexts`/`order` choice has not been proven equivalent for that boundary. No before-only counterexample was found or constructed; no empirical event is claimed.

Pinned artifact: WASM SHA-256 `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`. Static disassembly only. No hidden actor read, WASM execution, live action, core edit, or formal event credit.

## Cleanup iterator and participant actions

The block starts at `0x1afc3`; at `0x1afd5`, `World::tick_before_inputs` calls `func3449` with the cleanup iterator state at scratch `+420`. `func3449` delegates one `next` request to `func6761` with terminal code `2`. That immediate adapter returns the iterator's byte payload when a value is present and returns `2` when the iterator is exhausted. The enclosing `br_table` routes payload `0` to the attacker cleanup path, payloads `1` and `3` to the defender cleanup path, and payload `2` to terminal adjudication. This identifies the action tags and end marker; it does not by itself establish which tag is yielded first when both participants have a cleanup candidate.

The attacker path (`0x1b015..0x1b078`) is skipped while damage is positive. If its pending next-unit value is sentinel `10`, it calls `func1347` with the held unit and sentinel, resolving the held casualty without another damage step. Otherwise it calls `func2022` using the selected Tank or Soldier and current cumulative damage, then calls `func1347` with the held and selected units and adds the returned signed damage to the same accumulator. The defender path (`0x1b07b..0x1b0de`) is skipped while damage is negative and applies the symmetric operation. Therefore both paths are eligible when damage is zero. No score reset occurs before the terminal check.

This agrees with the Python `_fight` representation of a held unit in `last[side]`: advancing a selection removes the prior held unit, while `consume(side, None)` removes the last pending unit at exhaustion. Tank and Soldier both use field zero in this restricted case; their surface damage is respectively 3 and 1, signed by side. Morale contributes the capped headcount offset before the fight, and the same accumulator carries it through cleanup. In this Shield-zero, T/S-only scope, `fight_ordinary`'s Tower capacity does not reorder combat selection; its separate arrival/reconciliation use remains governed by the independently stated caller preconditions.

## Terminal vectors and result relation

In the stated scope, `Units::is_alive` treats a side as alive exactly when its terminal vector has at least one Tank or Soldier. Let `A` and `D` denote those two booleans after all held casualties and cleanup selections have been resolved, and let `score` be the final cumulative signed damage. The pinned result mapping and `_fight` winner selection reduce to:

| Attacker T/S alive (`A`) | Defender T/S alive (`D`) | Final score | Pinned result | Python winner |
| --- | --- | --- | --- | --- |
| true | either | any | `0` | `ATTACKER` |
| false | true | any | `1` | `DEFENDER` |
| false | false | `score <= 0` | `1` | `DEFENDER` for a Tower |
| false | false | `score > 0` | `2` | `None` / unsupported destruction downgrade |

Thus every terminal T/S vector is covered by its alive/dead predicate, but only if both implementations produce the same terminal vectors and final score. This table does not prove the contested zero-score cleanup order.

## Zero-score boundary and remaining proof

For `score == 0`, neither side is skipped by its sign guard. Python runs its first cleanup candidate from `order`, chosen as defender-first whenever a defender `nexts` value exists; otherwise it starts with the attacker. In the pinned code, the action order is carried by the `func3449` iterator's yielded payloads. Because the iterator's construction/advance semantics below `func6761` have not been followed, this review cannot show that the first yielded payload follows the same conditional ordering. Treating the terminal table as proof of loop equivalence would skip this gap.

The remaining exact check is a bounded trace of the already-built cleanup iterator state into the first one or two `func3449` yields, for cases where both candidates exist and the score entering cleanup is zero. It must establish the payload order from before-state values and confirm each yielded participant is consumed once before sentinel `2`. Until that trace is accepted, retain the existing `UNVERIFIED_NORMAL_COMBAT` refusal for this ordinary T/S pathway. The prior shield-retaining result is a separate mechanism and does not close this cleanup ordering question.
