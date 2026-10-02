# Production timing around ordinary Tank/Soldier capture

## Finding

The pinned production pass runs before ordinary arrival combat, the ordinary
owner setter, and the later surviving-force addition. A Tank/Soldier capture
cannot cause that same pass to produce for the arriving owner. At the setter,
Tower+45 morale and the already completed production pass are not recomputed.
The next pass can generate for the resulting owner if the Tower remains owned,
its delay is zero, and the selected interval is due. For a stable Tower kind,
known morale, and no Ruler, this ordering agrees with the simulator's phase
ordering: it applies scheduled tower production before resolving arrivals, then
updates the captured Tower's potential production metadata without adding a
unit from that metadata during the current tick.

This is a timing comparison, not proof that every ordinary Tank/Soldier combat
reaches capture or the common merge. It establishes no production mismatch or
before-only counterexample.

Pinned client SHA-256:
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`.
Offsets below come from the matching offline
`runtime/research/v2/disassembly.json`; the module was not executed.

## Pinned pass and timing

`World::tick_before_inputs` is function 448 at `0x19b86`. Its existing-tower
pass refreshes Tower+45 morale at `0x1a561`, then enters the Tower maintenance
and generation section beginning at `0x1a570`. The pass handles periodic
capacity/overflow maintenance at `0x1a570..0x1a5fc`. It then checks Tower+47
delay: a nonzero delay is decremented and branches past generation
(`0x1a617..0x1a62a`). With zero delay, a nonzero Tower+36 owner opens the
generation loop (`0x1a62d..0x1a639`). Thus neutral or upgrading/delayed Towers
do not generate in this section.

For each unit ID, the loop calls `TowerType::unit_generation` at `0x1a65f..0x1a66b`.
If that lookup has no interval, it skips the unit. Otherwise it tests the
current world clock modulo the interval at `0x1a676..0x1a69c`. Tower+45 selects
the normal interval when false and `max(1, interval >> 1)` when true. On a due
unit, the loop adds through `Units::add_inner` at `0x1a69e..0x1a6ae` and applies
the result to the unit vector at `0x1a6b1..0x1a6bc`. This is the actual
production event; `TowerType::unit_generation` is only the interval lookup.

After the tower pass, ordinary nonempty-defender combat reaches the result and
owner-update code. Its ordinary `Tower::set_player_id_inner` call is at
`0x1b21d..0x1b223` (the earlier `0x1ac21` setter is only the separately
documented empty-defender path). For the ordinary branch, the setter call is
after the generation loop. The surviving-force addition follows later at
`0x1b43e..0x1b45b`, as traced in
`V2_M2A_ORDINARY_CAPTURE_AFTERMATH_REVIEW.md` and
`V2_M2A_TS_CAPTURE_CAPACITY_REVIEW.md`. Consequently, on the capture tick,
generation sees the pre-arrival Tower owner, composition, and the morale byte
refreshed earlier in that pass. The setter does not rewrite Tower+45, and the
later Tank/Soldier merge cannot trigger the already-passed generation loop.

For a stable kind and known morale with no Ruler, the newly owned Tower's
future eligible intervals are the same table-based intervals used by the
simulator: `rules.production()` returns potential intervals for an owned,
non-delayed Tower and omits non-Shield unit generation when a Ruler is present;
morale halves intervals with minimum one. The ordinary capture branch in
`step.py` refreshes this potential metadata after changing the owner, but the
tick's actual additions have already been applied in the earlier per-Tower
phase. Its following arrival merge adds only surviving Force units subject to
the separately audited limits. No immediate unit is synthesized from the new
owner's potential production entry.

## Limits

Static facts here establish the local-client pass order and due-production
predicate. They do not establish server generation time, event delivery or
snapshot age; whether an arbitrary ordinary combat result takes this setter and
merge branch; the owner's next-tick morale value if its aura can change; or
production after a kind/delay/owner transition outside the stated stable-kind,
known-morale case. The model's fixed-morale and combat guards remain necessary
for longer trajectories. No core change or formal-corpus addition is proposed.
