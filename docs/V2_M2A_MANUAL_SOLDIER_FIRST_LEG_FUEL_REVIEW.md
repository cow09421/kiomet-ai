# Manual Soldier first-leg fuel boundary

## Before-only lemma

Manual launch initializes Force+23 fuel to 150. During the initial leg, the
inbound loop calls `Force::raw_tick` without a preceding fuel precheck; the
pinned `raw_tick` path advances progress using the force speed and
acceleration flag, and does not read or debit Force+23. Thus the initial fuel
byte is preserved until the first completed leg. This says nothing by itself
about what state or branch will hold at arrival.

If, at a coherent arrival-before state, the certified path is terminal, the
force and destination have the same owner, the destination's
`supply_line_present` is explicitly false, and both incoming and destination
inventories contain only Shield/Tank/Soldier units, the existing ordinary
friendly-merge proof applies. Arrival preserves the fuel byte in its packed
copies, then that merge calls `Units::add_units_to_tower` without passing a
Force or checking fuel. Under those arrival-time predicates, fuel cannot
prevent the first ground merge. The review does not assume these predicates
or inventories persist from launch through a possibly long first leg.

This is a narrow admission fact for an already identified manual launch and
certified before route. It does not infer arbitrary drag classification or
make fuel a general unknown-state default. No formal or empirical event is
added.

## Pinned source basis

- `docs/V2_M2A_LAUNCH_RULE.md`: manual `Tower::deploy_force` construction;
  source Tower+45 is copied to Force+21, progress begins at 0, and fuel at
  Force+23 is 150. The same note documents the `Tower::force_units`
  all-deployables input.
- `docs/V2_M2A_TS_MORALE_TRAVEL_SPEED_REVIEW.md`: the eligible Soldier-only
  force has composition-derived speed 2; known morale true controls the
  accelerated initial-segment threshold.
- `docs/V2_M2A_DIRECT_ROUTE_RULE.md`: the sufficient route certificate
  describes a two-node stored path ending at the certified destination, but
  expressly leaves arrival behavior to separate rules.
- `docs/V2_M2A_FRIENDLY_FUEL_RULE.md`: the inbound loop calls
  `Force::raw_tick` unconditionally (`0x1a9ae`); `raw_tick` has no fuel read
  or debit; completed force fields including fuel are copied at
  `0x1a9f1`, `0x1a9fc`, `0x1aa07`; the same-owner/no-Ruler, absent-line branch
  merges units without a Force parameter at `0x1b428..0x1b458`.

## Preconditions and limits

Launch-time fuel initialization and first-leg preservation require the
caller-qualified own manual `DeployForce`, the source before-state (including
explicit source `supply_line_present == false`), and its certified direct
two-node path. The separate arrival merge conclusion
requires an arrival-before certificate for the terminal route, same-owner
relation, explicit destination `supply_line_present == false`, an incoming
T/S-only vector (here, four Soldiers), and a destination inventory limited to
Shield/Tank/Soldier. The launch-before state does not establish that ownership,
line state, inventories, or terminal status remain the same at arrival.
These claims do not cover combat, capture, relay, air/special/Ruler vectors,
unknown or present destination supply lines, or a route that continues
beyond the certified destination. Future routes, later movement, hidden
actors, and fuel after other transitions remain unknown. No after-state fit,
live inspection, core change, guard change, or WASM execution was used.
