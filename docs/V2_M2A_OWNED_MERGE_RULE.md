# M2 owned arrival merge allowance

This is a bounded candidate rule for ordinary Tank and Soldier arrivals. It is
based on the current pinned artifact's before-state code and remains subject to
the project's independent UI validation. It does not establish current server
authority.

## Pinned evidence

The disassembly is `runtime/research/v2/disassembly.json`, aligned `lines[]` and
`offsets[]`, for WASM SHA-256
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c` (the
matching battle artifact). Relevant function starts are `World::tick_before_inputs`
448 at `0x19b86`, `Units::add_units_to_tower` 2195 at `0x10ea28`,
`Units::add_inner` 902 at `0xb3cbb`, and `Units::capacity` 3834 at `0x13d8d1`.

At caller offset `0x1b458`, function 448 supplies the existing Units pointer,
incoming Units pointer, tower type, a boolean derived from the destination
tower's nonzero owner field (`0x1b44d..0x1b453`), and the separate Tower+45
flag before calling function 2195. Function 2195 iterates unit indices and
passes the owner boolean to function 902 as its overflow-permission argument.
Function 902 calls the destination capacity calculation and, on that permission
path, adds the per-unit overflow table entry before subtracting current stock;
negative remaining space becomes zero, and the accepted incoming amount is
clipped to remaining space. It does not truncate stock already above the
resulting limit.

The table at address `1,363,148` begins with six u32 entries
`[15, 4, 2, 2, 5, 10]` for unit indices 0 through 5. Thus Tank (4) has +5 and
Soldier (5) has +10. Function 3834 returns the ordinary capacity tuple used by
this path (with a separate Shield/morale adjustment); the allowances are added
after that tuple. The simulator uses the observed per-tower capacity tuple and
refuses a computed Tank/Soldier limit above 255 because larger packed counts
are not established here.

For an empty neutral capture, function 448 sets the owner before reconciling and
before the arrival merge call. A hostile combat win likewise changes the owner
before surviving attackers are merged. These paths therefore pass the owned
overflow flag. A friendly reinforcement also passes it, but remains guarded by
the separately observed supply-line premise in the simulation.

On the owned 120-phase overflow cleanup, function 448 compares current stock
with capacity and subtracts exactly one per over-cap unit. With a known absent
supply line the candidate permits this for Tank and Soldier only. A present or
unknown line still rejects that cleanup in the simulation; other mobile kinds
remain fail-closed. The pinned absent-line path skips hidden deployment when
the source field is absent, but this note does not infer route or fuel from
that fact.

## Candidate cases and limits

Given a before-state Tank/Soldier capacity of `(2, 4)`, a new owned arrival can
raise those counts to at most `(7, 14)`. If the destination already has 9 Tanks
and 15 Soldiers, a further arrival adds zero and leaves `(9, 15)` intact. An
empty neutral capture uses the same owned merge after the owner change. Any
other unit kind that would exceed its observed capacity continues to reject;
Ruler, special-unit, combat, relation, terminal-path, and fuel guards are
unchanged.

The tests in `tests/test_v2_owned_overflow_merge.py` check these local rules,
including the ordinary-combat candidate path. They verify the implementation
against this static source-derived hypothesis; they are not independent live
correctness evidence.
