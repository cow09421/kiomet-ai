# Terminal friendly arrival: supply-line uncertainty

STATUS: conservative refusal integrated; relay simulation remains unsupported.

Public reference `common/src/chunk.rs:433` drops empty or expired forces, then
calls `Force::try_move_on` before friendly `add_units_to_tower`. In
`common/src/force.rs:201`, an exhausted path at a same-owner destination can be
replaced by that destination's supply line for a Many force at a non-ranged tower.
Progress resets and fuel decreases. Therefore terminal path plus positive fuel
does not prove reinforcement.

Root independently inspected the pinned disassembly, SHA
fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c:

- `0x1b316..0x1b31b`: destination Tower+24 loaded into var20.
- `0x1b34b..0x1b354`: var20 compared with Option sentinel 0x80000000.
- `0x1b35b..0x1b368`: TowerType::ranged_distance plus another condition gates
  the subsequent path-copy branch at `0x1b370..0x1b37d`.
- `Tower::set_player_id_inner`, `0x13b009..0x13b022`, clears the existing owner's
  supply-line Option to the sentinel during an ownership change.
- Normal owner supply-line renderer begins its Option gate at `0xdc967`;
  it checks owner+36 before using the path, with a separate cheats branch.

This is bounded structural corroboration, not complete relay execution proof.
No future route entry, supply-line path content, or hidden opponent fact is read
by the observation adapter. The adapter and canonical contract are unchanged.

The simulator now requires explicit `Scenario.no_supply_line_towers` membership
before merging into an already same-owner destination. Default empty membership
means unknown, not absent. A terminal-force scenario cannot bypass this guard.
The premise must be established independently before using any real case; it is
never inferred from an after-state merge. Newly captured towers follow the
separate ownership-change branch; unsupported ruler/aura/fuel/overflow guards
remain active.

Regression: known terminal/fuel but no premise refuses; terminal_forces alone
also refuses; an explicit no-line synthetic premise permits the complete merge;
unknown tower IDs refuse. Both real ground-defense fixtures still match and do
not require this premise because the attacking force is destroyed first.

Luna arrival review supplied a read-only candidate; Sol checked source ordering,
re-read the pinned offsets, implemented the guard, and ran all 68 v2 tests plus
formal and isolated candidate corpora. No milestone or live-reinforcement PASS.
