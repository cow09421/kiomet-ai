# Friendly no-line arrival admission review

This review proposes a narrow before-only gate for a genuine ordinary friendly
terminal reinforcement. It adds no simulator behavior or formal credit. The
evidence pin is client WASM
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c` and its
aligned `runtime/research/v2/disassembly.json`.

## What the friendly merge reads

The inbound force is advanced and Tower maintenance runs before arrivals in
`World::tick_before_inputs`. At completion, the destination's same-owner,
no-Ruler branch reaches `Units::add_units_to_tower` (`0x1b3ca–0x1b458`); it does
not run combat or change destination ownership. The call receives the cached
Tower+45 aura flag as a capacity input (`V2_M2A_OWNED_MERGE_RULE.md`). The
capacity function adds the morale bonus only to Shield capacity; Tank and
Soldier capacities are unchanged (`Units::capacity`, `0x13d8d1`). Therefore a
Tank/Soldier-only friendly merge does not use defender morale to calculate its
Tank/Soldier result. It does not call `production` or recalculate owner
production intervals in this branch.

Morale still matters earlier in the same tick. Tower maintenance recalculates
capacity, including the Shield bonus, and uses the aura flag when choosing
production intervals (`0x1a57e–0x1a69c`). The pinned rule table halves eligible
intervals when morale is true (`observe.rules.production`); `capacity` adds ten
only to Shields (`observe.rules.capacity`). The current `step` model processes
this Tower pass before arrival using the observed capacity and production
facts. If the destination aura refreshes during that pass, a fixed-morale step
can miss a destination production or Shield-capacity change even though the
subsequent Tank/Soldier merge itself is morale-independent.

The no-refresh helper should therefore be used as a narrow destination
precondition for a one-tick friendly arrival prediction, not as a general
morale or world-continuity certificate. Require the destination's cached
`MORALE_BOOST` value and production/capacity facts to be explicitly known in the
before snapshot, then evaluate the scheduler gate for that destination only.
No global King-location certificate is needed to prove this gate miss. Other
towers may refresh; any resulting visible difference is handled by the full
prediction comparison below.

## Concrete before-only helper inputs

For an arrival during the next `tick_before_inputs`, call
`no_periodic_aura_refresh(before_tick, chunk_key, slot, passes=1)` from the
actual pre-arrival canonical state. Use the exact observed `state.world_sequence`
as `before_tick`. The helper advances the u16 clock itself. Derive `chunk_key`
and row-major `slot` from the destination TowerId using the pinned
`RelativeTowerId::upgrade` and `ChunkId::bottom_left` representation:

```text
chunk_key = (((tower_id >> 20) & 0xff) << 8) | ((tower_id >> 4) & 0xff)
slot      = (((tower_id >> 16) & 0x0f) << 4) | (tower_id & 0x0f)
```

The coordinate conversion at `0x142448–0x14246f` places the ordinal’s upper
nibble in the local row and its lower nibble in the local column. The chunk base
conversion at `0x14b55e–0x14b575` places the 16-bit chunk key into the matching
TowerId bits. The per-chunk scheduler passes that same iterator key to the slot
converter and uses its low u16 in the phase calculation (`0x1a449–0x1a4a2`).
Do not substitute `phase_offset(tower_id)` or the displayed world position for
these fields.

Require the helper to return true. That means the next phase residue is above
the destination's local slot, so every possible present-Tower rank in `[0,
slot]` misses the periodic gate. This conservative interval already permits
unknown earlier-slot occupancy; it does not require a complete all-owner chunk
census. It is valid only if the destination remains the same actor at the same
chunk and slot until the scheduler examines it. For a prediction covering more
than one future scheduler pass, each pass must be covered by the helper’s
requested horizon (maximum 16) and target identity/location stability must be
established independently. The current task is a one-tick arrival rule, so the
relevant horizon is one.

The result proves exclusion from the periodic Tower+45 store only. It does not
prove that another function or exogenous event cannot change morale, that the
cached aura value is correct, or that any other tower's aura remains fixed.
Unknown target aura/capacity/production remains a readiness failure. A false
helper result means the scheduled write may occur and the current fixed-morale
step cannot claim destination continuity from this certificate.

## Arrival branch and before-only admission

For the existing fuel exception, admit only a force whose independently
qualified route is terminal at this destination, whose owner already equals
the destination owner before arrival, and whose destination supply-line fact
is directly observed `False` at the pre-arrival snapshot. The pinned branch
checks the exact absent-Option sentinel at `0x1b349–0x1b354`, then takes the
same-owner merge at `0x1b3ca–0x1b458`. That call has no Force or fuel parameter.
Unknown and zero fuel are harmless only on this branch; negative fuel remains
invalid. Positive fuel and `terminal=True` do not establish line absence.
`Scenario.no_supply_line_towers` alone does not bypass the fuel guard: the
exception specifically requires the destination field to be explicit false.

The supported static merge boundary remains the one in
`V2_M2A_FRIENDLY_FUEL_RULE.md`: incoming inventory contains Tank or Soldier,
and incoming plus destination contain only Shield, Tank, and Soldier. Ruler,
Air, special units, combat, capture, unknown or present destination lines, and
relay retain their guards. For a first genuine live case, the prepared
candidate contract is narrower: a positively visible own source with zero
delay, cached aura explicitly false, own supply line explicitly false, no
Ruler, and exactly Soldier-only current deployable inventory; plus an own
non-Ruler destination with line explicitly false, known capacity, no Shield
overcapacity, and no inbound force at candidate selection. The destination's
supply line must be positively false again in the actual pre-arrival state; do
not carry the preview fact forward as current truth.

Terminality must come from the original recorded before-input route, not from
the post-arrival force or a successful simulator fit. The existing direct-route
certificate proves a two-node stored path only for its coherent gesture
snapshot, with all valid source-neighbor cells visible, explicit deselection,
and route predicates from before facts. Its gesture continuity remains unknown
unless the same-document input-entry bridge is independently qualified. A
currently observed force exposes its current segment, not its remaining Path;
without unique lineage from a separately qualified route and newborn, retain
`UNKNOWN_POST_ARRIVAL_PATH`.

For manual-launch lineage, use the actual before source inventory and a unique
progress-zero NEW_TRACK birth matched by owner and endpoints. The observed
quantity is compared with the prediction; it must not select the force or be
fed backward as an inferred command quantity. Source line absence through the
qualified input interval helps rule out periodic supply deployment. Do not
infer terminality or fuel from a later segment. Once this force is in flight,
its stored acceleration is the launch-time source aura copy; current source
aura continuity is not a requirement for this arrival branch.

## Whole-visible comparison and unknown events

A genuine formal one-tick arrival still needs an original recorded BEFORE
state, qualified input or force lineage, and a fresh complete visible-world
comparison. Keep match/document/player identity and tick chronology coherent;
require `PLAYER_VISIBLE_COMPLETE` evidence for both snapshots, compare the
whole visible result including Tower owner/type/units/capacity/production/morale,
force fields and inbound order, and retain the first mismatch. Classify the
event from before facts and input evidence before looking at the after state.
Never tune route, fuel, quantity, or scenario premises to make the output fit.

Complete visible coverage defines the compared player-visible state; it is not
proof of the entire server world. The aura helper itself does not need exact
chunk occupancy because `[0, slot]` bounds every possible target rank. Other
visible towers may refresh or other known forces may act; compare their actual
predicted effects and let the first visible mismatch exclude the candidate.
There is no separate blanket requirement that no foreign action exists
anywhere. An existing force with an unknown endpoint is a concrete exogenous
modeling failure, however: control readiness must reject it because its
movement, arrival, or effect cannot be predicted. Likewise, partial visible
coverage, stale/currentness gaps, or unknown required fields prevent formal
comparison. Do not convert these specific unknowns into absent events.

The latest bounded 180-second friendly preflight was `NOT_READY` because an
existing force had an unknown source endpoint (`force:5:source`); the observer
was not armed and no troop input was sent. Preserve this as a readiness
exclusion, not as friendly-arrival evidence.

The retained formal total is 1053/1053: 1052 production/current-leg movement
cases plus one independently qualified empty-neutral capture. Friendly
reinforcement remains at zero formal cases. The separate ordinary-event target
is 100 genuine transitions; do not pad it with movement rows. A qualifying
friendly arrival contributes at most its own independently recorded one-tick
event. Any 5–10 second trajectory must run continuously from its original
before state, compare each distinct observed tick, preserve the first mismatch,
and take no per-tick canonical reset. The one-pass aura helper does not certify
a longer trajectory or a future morale value.
