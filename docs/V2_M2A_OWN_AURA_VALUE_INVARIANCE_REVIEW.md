# Own Ruler facts and conditional aura-value invariance

## Question and result

Can the observed stationary own Ruler and canonical `king` marker establish that the client's cached-Ruler input already equals the aura value, making the unknown dense rank irrelevant?

No. The canonical `king` field is derived from visible unit counts, not aliased to the client's private `World::player_inner` cache. The cohort proves a visible own Ruler on Tower `16711928` both before and after tick 22→23; it does not prove the cached Ruler identity, cached alive bit, or cache freshness consumed by `tick_before_inputs`. The before morale is false, while the visible Ruler remains on this same Tower. If a refresh reaches this Tower and the private cache resolves to this observed Ruler, the pinned branch would set morale true. That makes the observed false→true change consistent with a refresh; it cannot make the before value invariant or remove the rank uncertainty for this transition.

A conditional lemma remains useful: for a fixed target Tower, if its owner and identity, the player's actual cached Ruler alive state and packed position, and neighbor relation remain stable, then each periodic aura write has a stable Boolean result. Under those conditions, after the target has been shown to equal that result, a fixed-morale premise can hold for the periodic aura store through a bounded horizon, regardless of when the dense-rank gate fires. This requires independently established cache identity and stability plus same-actor observations; the current Party canonical marker does not establish those premises.

## What the canonical fact establishes

`GameState.king` is constructed in `src/kiomet_ai/v2/observe/extractor.py` from exactly one positively observed own Ruler marker. The marker is emitted for a visible SELF-owned Tower with observed Ruler count above zero, or a visible own Force carrying a Ruler. Its recorded source is “currently visible self Ruler units; absence never implies death.” It is not a raw read of a private player cache. The tick-22 and tick-23 values are both `((1, "tower", 16711928),)`, while the target's visible morale changes false→true. This shows that the visible unit stays on the Tower across the pair; it does not prove an alias to the aura routine's cache.

The pinned refresh branch in `runtime/research/v2/World__tick_before_inputs.txt` initializes the write value to false, checks the Tower owner, calls `World::player_inner`, tests the returned alive bit, and compares the cached packed location against the current Tower ID. On a non-exact match it calls `TowerId::is_neighbor`; the result is stored at Tower byte `+45`. Thus an exact cached own Ruler identity and alive state at the target itself would imply a true refresh value; a stable cached neighboring Tower would also imply true. The Party receipt exposes neither the cache record nor its full alias/layout provenance. It also does not establish that no unobserved or foreign Ruler actors exist elsewhere.

## Rank and transition implications

The corrected pinned mapping is in `docs/V2_M2A_PARTY_AURA_CHANGE_REVIEW.md`: Tower ID `16711928` splits to chunk key `3855` (`0x0f0f`) and local slot `248`. For tick 22's next scheduler pass, `(23 + 3855) mod 16 = 6`. The admissible rank interval `[0,248]` contains ranks with residue 6, and the pure no-refresh helper returns false. Exact rank remains UNKNOWN. A stationary visible Ruler marker does not change that gate result; only an independently justified equivalence between the visible marker and the actual cache could establish the refresh value independently of rank.

For this recorded transition, fixed morale is observably false before and true after, so a cross-transition fixed-morale premise is contradicted by the displayed snapshots. The cache-conditioned lemma can support a future bounded fixed-morale assumption only after the target's current morale matches an independently established stable cache-derived outcome and owner, actor, and cache stability are established for the horizon. It does not justify fitting the cache from the after state.

## Evidence needed to use the lemma

A future review would need the pinned layout tying the player-private cache record to a particular Ruler identity and alive bit, source-clock and actor-generation provenance for the cache and target Tower, and evidence that the cached position and target owner/neighbor relationship persist through the intended horizon. If using the public canonical marker instead, a separately verified alias from that marker to `player_inner` is required. Complete all-owner slot occupancy is still needed to know whether a given rank gate runs, though it is unnecessary for a cache-conditioned value that is already independently proven invariant under either gate outcome.

Hidden actor occupancy, private cached-Ruler state, and foreign Ruler presence remain UNKNOWN. This note makes no core change and awards no formal credit.
