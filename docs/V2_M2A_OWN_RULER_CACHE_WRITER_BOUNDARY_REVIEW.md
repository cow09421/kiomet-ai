# Own Ruler cache writer boundary

## Finding

The bounded incoming-player-event path inspected here does **not** identify a
writer for the first `i64` of the 64-byte `World` player slot used by the
aura consumer. `PlayerEventsFromServer::extend_one` only appends an 8-byte
event value to its vector. The subsequent `World::tick_after_inputs` body
iterates `ChunkEvent` records and applies them through `Chunk::index_mut`;
that path does not write player slots. The player-DTO path in `func1242`
calls `func1407`, which copies 56-byte records, but the inspected callsite
does not establish that its destination is a `World` player slot or that a
DTO payload aliases the aura cache field.

Accordingly, the visible own-Ruler marker still cannot be identified as the
cached TowerId read by the aura routine. The exact constructor, deserializer,
or synchronization caller that initializes or updates the slot remains
unresolved. Cache identity, freshness, alive state, lifecycle after Ruler
movement/death/capture, and own-only alias are **UNKNOWN**. This finding does
not imply that no writer exists elsewhere.

## Static path evidence

- At `func1242` callsite `0xcddf4..0xcddf9`,
  `PlayerEventsFromServer::extend_one` receives an `i64` event value. Its
  pinned body (function 2586) reserves vector space, stores that value as one
  8-byte element, and updates the vector length at offset 20. It has no
  `World` slot argument or 64-byte record write.
- `func1242` then calls `World::tick_after_inputs` at `0xcde1c`.
  `World::tick_after_inputs` (function 1393) walks buffered `ChunkEvent`
  items (28-byte records) and applies each to a chunk entry via
  `Chunk::index_mut`; the inspected body contains no player-slot lookup or
  cache-field store.
- The PlayerDto update path in `func1242` clones each DTO and calls
  `func1407` at `0xce3bd`. That helper copies 56-byte records and updates
  associated vector/hash bookkeeping. From this caller, neither the
  destination's relationship to the 64-byte `World` player array nor the
  meaning of any DTO payload copied is established. Equal-looking payload
  or neighboring offsets are not sufficient to infer an alias.
- The existing consumer review establishes that `World::player_inner`
  indexes `(player_id - 1) * 64`, and the aura consumer reads the slot's
  first `i64` at `0x1a51d`. The existing cache and value-invariance reviews
  found no named `PlayerInner` constructor or cache setter in the inspected
  call graph. This note does not repeat or extend those consumer proofs.

## Remaining proof needed

A positive cache-writer result requires a pinned typed initialization or
event-application path that proves all of the following together: the base
pointer is the 64-byte `World` player-slot array; the slot index is tied to a
specific player identity (including the self/own identity if claiming an
own-only alias); the first `i64` is written from the relevant Ruler TowerId
and alive state; and the write ordering/lifecycle covers the aura read at
`0x1a51d`. The inspected event append, chunk event application, and
56-byte DTO-copy paths stop short of that chain. No hidden cache read, foreign
actor inference, live inspection, semantic WASM execution, or formal credit
is used.
