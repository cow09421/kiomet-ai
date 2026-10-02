# Tank/Soldier capacity and owned-arrival clipping

## Result

For a Tank/Soldier-only ordinary arrival that reaches the pinned
`Units::add_units_to_tower` call, the current Tower type determines base
capacity, the current nonzero owner flag enables the per-unit overflow
allowance, and Tower+45 does not change either Tank or Soldier capacity. The
owned limits are raw capacity plus 5 for Tank (unit 4) and plus 10 for Soldier
(unit 5). The merge clips only incoming counts to remaining room and leaves
any already over-limit stock intact. `step.py::_merge_arriving_units` uses the
same formula for IDs 4 and 5 and preserves existing overflow.

This compares the bounded merge calculation only. It does not establish which
ordinary combat outcomes reach the merge call, all capture owner semantics,
production equivalence, or arbitrary tower-type transitions.

Pinned client SHA-256:
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`.
Offsets are from the matching offline `runtime/research/v2/disassembly.json`;
static WASM data was read without instantiating or executing the module.

## Actual arguments and formulas

At `0x1b43e..0x1b458`, `World::tick_before_inputs` passes the destination Units
pointer, a packed copy of the arriving Force units, `Tower+46` as tower type,
`Tower+36 != 0` as a Boolean, and `Tower+45` as the separate morale Boolean.
`Units::add_units_to_tower` function 2195 (`0x10ea28..0x10eaa1`) iterates unit
IDs 0 through 9, skips zero counts and single-use units, and calls
`Units::add_inner` for the remaining entries. Tank and Soldier are nonzero,
non-single-use Many entries, IDs 4 and 5.

Function 902, `Units::add_inner` (`0xb3cbb..0xb3e3d`), calls
`Units::capacity(unit, tower_type, morale)` at `0xb3d13..0xb3d1c`. Function
3834 (`0x13d8d1..0x13d901`) returns 255 for tower type 27; otherwise it returns
`TowerType::raw_unit_capacity(tower_type, unit)` plus 10 only when both the
unit is 0 (Shield) and the morale argument is true (`0x13d8df..0x13d8fb`).
Therefore, for ordinary tower kinds 0 through 26:

```text
C_Tank     = raw_unit_capacity(Tower+46, 4)
C_Soldier  = raw_unit_capacity(Tower+46, 5)
```

Tower+45 does not enter either T/S expression. This matches the observer's
version-bound `rules_fae13.json` capacity table, whose `capacity()` helper adds
morale capacity only to unit 0. Shield's +10 is not included in the T/S limits
below.

The owner Boolean is a separate input. At `0xb3d20..0xb3d45`, false selects an
overflow bonus of zero; true selects the u32 entry at address 1,363,148 plus
four times the unit ID. The matching WASM's static data at that exact decimal
address starts `[15, 4, 2, 2, 5, 10]` for IDs 0 through 5, so Tank's entry is 5
and Soldier's is 10. When the current Tower owner is nonzero, their limits are
therefore:

```text
L_Tank     = C_Tank + 5
L_Soldier  = C_Soldier + 10
```

The type-27 sentinel path yields `capacity = 255`; this report scopes its
ordinary-Tower formula to types 0–26. The observer/simulator also rejects an
overflow limit above 255 rather than infer packed-byte wrap behavior.

For either unit, `add_inner` computes remaining room by subtracting the
destination's current count from `capacity + owned_bonus`, flooring a negative
result at zero, then caps the incoming count at that room
(`0xb3d43..0xb3d66`). The Many storage branches add only that accepted amount to
the existing byte (`0xb3d91..0xb3e1b`). There is no branch that removes existing
Tank/Soldier stock in this call. In symbols, for current count `E` and incoming
count `I`:

```text
added  = min(I, max(0, L - E))
after  = E + added
```

Thus `E > L` yields `added = 0` and preserves `E`; `C < E <= L` can still
accept arrivals up to `L`; and any clipped remainder is discarded. The caller
drops the returned per-unit added count (`0x10ea91..0x10ea94`) and does not
reinsert clipped units as a force.

## Ownership, capture timing, and maintenance

The overflow allowance is controlled by the owner field at the time of the
addition call, not by the source or prior owner. If an earlier combat result
has changed Tower+36 to nonzero before reaching `0x1b458`, the add path uses the
owned +5/+10 allowance. If Tower+36 is still zero, it uses no allowance. The
call recomputes `Units::capacity` from the current Tower+46 and Tower+45
arguments; ownership itself is not a base-capacity input. For a stable type,
the T/S capacity is unchanged by morale and by an owner flip. The normal tower
maintenance/capacity pass runs before arrivals (`0x1a570..0x1a5c7`), while the
capture setter is later; the setter does not write Tower+45. The postfight add
still evaluates its capacity function with the Tower fields present at that
later call.

The add call is not the Tower's periodic overflow cleanup. Earlier scheduled
maintenance uses `Units::subtract` at `0x1a5cb..0x1a5d4`; any cleanup there
precedes the arrival and follows a separate schedule/guard. It does not make
`add_inner` trim preexisting overflow when the arrival merge runs. The Python
step models its own pre-arrival cleanup only under its explicit phase and
supply-line guards; those guards remain separate from this merge equation.

The ordinary postfight call is branch-gated. This report does not claim every
attacker win reaches it, nor does it map every setter outcome to attacker
capture. `V2_M2A_ORDINARY_CAPTURE_AFTERMATH_REVIEW.md` contains the current
control-flow boundary. The empty-defender early capture path with
`Units::reconcile` is separate and is not used as proof of this ordinary merge.

## Simulator comparison and limits

`step.py::_merge_arriving_units` (`src/kiomet_ai/v2/sim/step.py:64-79`) uses
`capacity[4] + 5` and `capacity[5] + 10`, computes `max(0, limit-existing)`,
clips incoming counts, and preserves preexisting overflow. Those are the
client's T/S owned-add semantics when `capacity` describes the same current
Tower type. The `capacity` decoder already uses the raw type table and applies
morale only to Shields, so T/S do not require a separate aura adjustment.

The simulator's `limit > 255` guard fails closed for the exceptional type-27
sentinel; ordinary kinds in the current table do not reach that limit for T/S.
Other guards, including Ruler/Single composition, terminal route, external
actions, supply line, production, and the exact combat winner/result branch,
are not certified by this formula. No before-only counterexample to the T/S
merge calculation is established here, so no core change or formal-corpus
addition is proposed.
