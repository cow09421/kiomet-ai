# M2A ordinary terminal friendly merge and fuel

The pinned binary does not consult remaining fuel when a completed ordinary ground force merges into a tower that already has the same owner and has no supply line. The simulator previously applied its capture/continuation fuel guard to this branch too. This checkpoint removes that unnecessary dependency for a narrowly proven branch; it does not estimate an unknown fuel value.

Binary SHA: `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`. Offsets are aligned entries in `runtime/research/v2/disassembly.json`. A Luna traced the complete arrival path, a second Luna implemented the bounded correction, and root independently inspected the arrival loop, packed copies, movement callees and merge branch.

## Concrete branch

The inbound loop calls `Force::raw_tick` unconditionally at `0x1a9ae`; there is no earlier fuel precheck in that loop. `raw_tick` (`0x102bbe..0x102c95`) advances progress at Force+22, calls speed and progress-required, decrements path length at +8 and checks the current endpoint. `Force::speed` (`0x9896a..0x98b9a`) reads the unit vector, and `Force::progress_required` (`0x11ccbd..0x11cd17`) reads the path and acceleration at +21. None reads fuel at +23.

On completion, the caller copies the packed force fields, including its fuel byte, at `0x1a9f1`, `0x1a9fc` and `0x1aa07`. These copies preserve storage; they are not fuel comparisons. Arrival extraction/compaction removes the force from the inbound vector (`0x1aa3e..0x1aa64`). The packed tail is staged at `0x1ab46..0x1ab4e`. Same-owner relation is dispatched at `0x1ab86`. The destination's exact absent supply-line Option is checked at `0x1b349..0x1b354`. The same-owner/no-Ruler branch at `0x1b3ca..0x1b3d4` goes to the merge at `0x1b428..0x1b458`, passing units and tower parameters to `Units::add_units_to_tower`, without a Force or fuel parameter. Clipped incoming remainder is discarded rather than retained as an onward force.

The vendored `common/src/chunk.rs:437` fuel-zero expiry rule belongs to a different source pin and contradicts this concrete binary branch. It is not imported as the pinned rule.

## Implemented boundary

The exception requires an independently established terminal path, same owner before arrival, destination `supply_line_present is False`, incoming Tank or Soldier, and only Shield/Tank/Soldier counts in both incoming and destination inventories. An observed explicit false flag is necessary: `Scenario.no_supply_line_towers` alone cannot remove the fuel guard. A Shield-only vector does not establish a Many force. Unknown fuel stays unknown; zero fuel is harmless on this branch; negative invalid fuel remains rejected.

Unknown or true destination supply line, unknown terminal path, air/special/Ruler vectors, newly captured destinations, combat and relay retain their existing guards. This conservative ground boundary does not claim that all other binary friendly branches depend on fuel; those branches still require separate proof.

Regression cases compare None/zero/positive fuel under clipping and preserved existing overflow, establish ground-vector and terminal-certificate boundaries, and exercise the capture/combat/line/air/Single exclusions. These synthetic cases earn zero genuine transition or trajectory credit. A live independently qualified friendly reinforcement is still pending.
