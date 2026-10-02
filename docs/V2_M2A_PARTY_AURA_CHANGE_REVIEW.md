# Party cohort: tick 22→23 aura change review

## Question and verdict

Can the tick 22→23 morale/capacity/production change be explained by the pinned periodic Tower aura refresh, or does it indicate a decoder freshness error?

The transition is **compatible with a normal periodic refresh**, and its changed fields are mutually consistent with a morale refresh from false to true. The unconditional dense-rank interval does **not** exclude a scheduled refresh. This sample does not establish that the refresh actually ran, because exact present-Tower rank and full chunk occupancy are unknown. It also cannot distinguish a live refresh from a decoder freshness or mixed-read issue: the receipt contains two decoded snapshots, but no before/after raw Tower-byte provenance or independently observed actor generation. No formal event credit follows.

## Evidence from the committed cohort

The committed 21-sample fixture `tests/fixtures/v2/party-route-readiness-20261002/party-readiness-route-supported-2-20261002.json.gz` was restored with `state_from_dict` and converted with `from_canonical`. The exact consecutive pair has world ticks 22 and 23, the same Tower actor ID `16711928`, same owner `1`, same type `17`, same position `(1243,1277)`, and unchanged units. Its visible Tower morale changes `false → true`, capacity for unit 0 changes `10 → 20`, and production interval for unit 0 changes `20 → 10`. The sample’s visible own-Ruler marker is `((1, "tower", 16711928),)` both before and after: the Ruler is observed on the same Tower whose aura fields change.

The host observation times are `1230822781` ms at tick 22 and `1230823031` ms at tick 23. In both canonical states `updated_at_ms` is UNKNOWN; the observed tick value has source “first host observation of current displayed sequence; repeated polls do not refresh.” This establishes distinct sequential displayed ticks in the receipt. It does not provide a raw field read timestamp inside the Tower decode.

## Pinned coordinate and refresh gate

The packed Tower ID `16711928` has raw coordinate words `(id & 0xffff, id >> 16)=(248,255)`. Pinned `TowerId::split` (`runtime/research/v2/TowerId_split.txt`, `0x13f6ef–0x13f718`) returns `(local_slot << 16) | chunk_id`: the upper half is row-major local slot `j=248`, and the lower half is full chunk key `3855` (`0x0f0f`). This is a packed decomposition, not a world-grid `(x,y)` pair. The scheduler uses the chunk key low `u16` as its phase addend. The aura gate is `(dense_present_rank XOR ((world_tick + chunk_key) & 0xffffffff)) & 15 == 0`; the World tick increments before the Tower pass.

For the next pass, the tick is 23 and the gate residue is `(23+3855) mod 16 = 6`. The pure `no_periodic_aura_refresh(22,3855,248,1)` certificate returns false: the unconditional rank bound `[0,248]` includes ranks congruent to 6 (including 6), so it cannot rule out the refresh. This is only a possibility result. The visible cohort does not provide complete all-owner occupancy of that chunk or the target’s dense present-Tower rank, and it does not prove rank continuity through the scheduler pass.

The before state positively observes the player’s Ruler on this target Tower, which is compatible with the refreshed morale becoming true if the periodic check reaches this actor. The cached-Ruler state consumed by the client routine remains UNKNOWN. The visible marker does not expose that cache or certify the exact refresh branch result.

## Boundary and next evidence

The capacity and production changes fit the observed morale transition and normal periodic Tower pass, which separately processes aura, capacity, and production. There is no positive evidence here that the decoder is stale. Still, without source-byte provenance, a matching actor-generation observation, or a coherent raw before/after read tied to each tick, the replay cannot exclude a decoder freshness/mixed-read defect.

To resolve that distinction, evidence must link the same Tower actor and its morale byte to both sequence observations, establish the source clock/layout at those reads, and show the associated capacity/production bytes from that same actor generation. A complete same-chunk Tower slot census or runtime dense-rank observation would be needed to establish whether this scheduled phase actually visited the target. Keep hidden occupancy and cached-Ruler state UNKNOWN until such evidence exists.

This review does not change core code, infer Tower rank from the Tower ID, derive hidden occupancy, fit a cached value from the after state, or award formal credit.
