# M2A pinned own-ruler aura-cache review

## Question and conclusion

Can a visible, stationary own Ruler plus a known set of ordinary arrivals and no-Ruler actions establish that every currently visible own Tower will read refreshed morale on the next pass?

**Not from the pinned static evidence inspected here.** The aura code consumes a cached optional TowerId in the owner's player slot, while the reviewed WASM bodies do not establish when that slot is written from Ruler movement, launch, death, or capture. A visible Tower that contains a Ruler is therefore useful evidence about the world, but it is not a proven substitute for the field the aura code reads. Hidden foreign King/cache state remains unknown and is not read.

This is an evidence limit, not proof that the cache is stale or that no writer exists elsewhere in the client. It blocks a positive refreshed-morale certificate for all visible own Towers based only on visible Ruler position and action classification.

## Pinned layout and consumer

The reviewed artifact is pinned WASM `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`; offsets below are byte offsets in `runtime/research/v2/disassembly.json`.

`World::player_inner` (function 2071, `0x10ac88`) receives a player-slot base, slot count, and player id. It computes `(id - 1) * 64` (`i32.const 6; i32.shl` at `0x10acb2..0x10acb5`), checks the slot tag, and returns that slot pointer. In `World::tick_before_inputs` (function 448), the aura consumer calls it at `0x1a51a`, reads the slot's first `i64` at `0x1a51d`, and treats its low bit as the `Option` tag. The remaining packed TowerId data is compared against the current Tower identity and neighboring coordinates; the resulting Boolean is stored to Tower offset 45 at `0x1a561`.

The inspected caller access pattern is consistent with a first-slot-field read at the aura site. Other `World::player_inner` call sites in the inspected function bodies read offset 36 or pass offset 8 to alliance helpers; they do not show a ruler-cache setter. The function itself is a checked slot lookup, not a constructor or setter.

## Writer and lifecycle trace

No named `PlayerInner` constructor or cache setter appears in the pinned function-name inventory. `PlayerDto::clone` (`0x108677`) copies DTO fields, including a tagged optional payload at DTO offsets 24/28/36, but the only call sites found are inside `func1242`; those copies do not establish a write into the 64-byte `World` player slot or identify the optional payload as the aura cache. `PlayerEventsFromServer::extend_one` appends an event value and does not write the player slot. `World::tick_after_inputs` dispatches buffered chunk events. `World::extend` merges chunk-map content. These reviewed routines do not establish player-slot cache semantics.

Ordering in `World::tick_before_inputs` is clearer for Towers than for the player cache: the Tower aura/capacity/production pass occurs before the arriving-force branch. An attacking capture later calls `Tower::set_player_id_inner` at `0x1ac21`, then reconciles units at `0x1ac38`. The setter's reviewed body updates the Tower owner/prior-owner bookkeeping; it does not update the aura byte or a player-slot ruler field. Thus a capture changes ownership after that tick's aura/production pass, but the next-pass cache value for either owner is not proven by this path.

The same gap applies to launching or moving a Ruler: the reviewed aura and ordinary arrival paths show the consumer and Tower ownership transition, but no proved writer that synchronizes the owner's cached TowerId on the relevant side of input processing. A claim that the cache always equals the currently observed stationary own-Ruler Tower, or that it clears on death/capture, would exceed these offsets.

## Admission consequence

A visible own Ruler position and a complete list of known ordinary arrivals with no Ruler action are **insufficient** to infer refreshed morale for all currently visible own Towers. That inference additionally needs an independently established cache value and lifecycle rule at the next aura pass. The pinned evidence here supplies neither. Do not turn an unknown cache into “no Ruler” or treat visible foreign state as a proxy for a hidden foreign player's cache.

For a later full-world capacity/production comparison, keep the current observed morale/capacity/production fields as the before baseline and require the actual next-pass result to match the prediction over the complete visible state. If the admission proof relies on aura stability, use the no-periodic-refresh predicate only when its exact actor/chunk/slot inputs and same-actor/chunk/slot stability are independently established; the predicate only excludes scheduled aura stores. It does not certify that morale is currently correct, that no other morale write occurs, or that a long trajectory preserves the aura. It also does not repair the missing ruler-cache writer proof.

## Scope and uncertainty

This note uses static evidence from the pinned WASM and disassembly only. It makes no runtime memory reads, reads no hidden own/foreign cache, and does not rely on the public vendored source as proof of the pinned client writer. A constructor, deserializer, or synchronization routine outside the inspected named paths could still populate the slot. Until such a pinned writer and its ordering are located, the safe result for next-pass own-Ruler cache continuity is **UNKNOWN**.

## UI/render visibility check (own-only entitlement)

The render/UI path does not close the cache gap. `func1242` iterates a two-byte player-id list: it loads the current id at `0xcd619`, advances the list cursor, checks the corresponding indexed player entry, and stores that loop id into render state at offset 13336 (`0xcd652`). Later it passes that state field as the third argument to `World::player_inner` at `0xd2ed4`. The path contains no comparison between that loop id and a separately established local/self player id before this lookup. It is therefore a per-player render lookup, not a proved self-only accessor.

More importantly, the returned slot pointer is used at `+8` for alliance checks (`0xd3172`) and retained in render state; before the local is reassigned, this path does not load slot offset 0. The other render `player_inner` calls in `func1242` use `+8` alliance data. The inspected render callers therefore do not present the cached optional ruler TowerId, and they do not prove that this field is player-entitled own-only metadata under M0.

I found no normal own-King locating, centering, or minimap consumer of the slot's word 0 with an exact self-identity guard in the inspected pinned call graph. The only proved word-0 consumption remains the simulation aura check at `0x1a51d`. This review consequently cannot authorize exposing an own cachedRulerTowerId through the structured-memory decoder. That conclusion is limited to the inspected static path; it is not evidence that no such consumer exists elsewhere in code outside the pinned artifact or in an untraced path.
