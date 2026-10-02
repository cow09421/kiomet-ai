# M2A present-chunk currentness proof

The fixed client contains the concrete synchronous actor-update path that was missing from the earlier public-macro comparison. Two Luna reviews and the main agent checked the call chain and storage aliases. This establishes a basis for a future present-chunk absence certificate; the canonical coverage gate is unchanged in this checkpoint.

The binary pin is `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`; offsets below come from its aligned `runtime/research/v2/disassembly.json`. The cached `actor_model_macros.rs` has Git blob `d7ae73af5f9f37120bd2c672658ba5dcd52930fb` in Kodiak tree `83f62d2aacd94647dbc97d1bd4764fbfc17cdf55`. The binary correspondence relies on concrete operations and aliases, as well as the macro-specific assertions.

## Same ordinary world instance

`ClientBroker::socket_update` computes `var11 = root + 512` at `0x2b006..0x2b00c` and passes it to `ServerState::apply` at `0x2c41d` or `0x2c599`. Inside that function (`func443`, `0xd528`), its chunk-map base is explicitly `var0 + 152` at `0xd652..0xd658`: the observer's `root + 664`. Chunk indexing is row times 1408 plus column times 44, matching the pinned getter and decoder.

`ChunkMap::get_0` (`0x125d24`) checks the entry's exact `0x80000000` None tag at `0x125d60..0x125d6a`. `get_chunk` returns the present entry's `+36` field; `get_1` (`0x13c354`) follows that tower-array pointer, indexes 48-byte tower slots, and separately checks the tower's None tag at `0x13c37e..0x13c388`. The singleton slot used by the same apply path is `ServerState + 45208`, or `root + 45720`; the decoded displayed tick is `root + 45732`. These are aliases within one owned normal context, rather than offsets borrowed from unrelated structures.

## Ordered successful apply

The actor-update path removes Chunk actors (`0xd67d..0xd6d1`), then Player and Singleton actors. It replaces retained actors' inboxes and has three inbox-count mismatch failure paths (literal loads `0xfddc`, `0xfdf9`, `0xfe16`; assertion calls `0xfde8`, `0xfe05`, `0xfe22`). It then calls `World::tick_before_inputs` at `0xffdd`, applies normal client inputs, and calls `World::tick_after_inputs` at `0x101c4`.

Completion insertion follows the tick: Chunk entries are copied and inserted at `0x10240..0x10292`, Player insertion is at `0x10352`, and Singleton completion is at `0x103a3..0x103f6`. Existing-actor replacement is rejected. The failure strings at `0x115649`, `0x115661`, and `0x11567f` correspond to inbox-count, completion, and removal invariants from the macro. No asynchronous boundary separates these operations.

For a normally updated, known-present chunk in a coherent current document/match/tick, an exact tower None tag denotes absence in that current local replica. Count assertions alone do not prove packet ordering or remote authority. This proof gives no freshness, payload, or absence guarantee for a missing chunk. The server visibility-policy source belongs to a different vendor tree and remains explanatory context, rather than evidence extending this binary proof.

## Observation boundary and next implementation

The decoder now exports `visible_slot_gaps` with `CHUNK_ABSENT` or `TOWER_NONE`, using only tags it already read after a positive current sensor gate. It does not follow an absent chunk, read empty-slot payloads, export pointers or hidden cell IDs, or reclassify canonical coverage. A new synthetic read-boundary test and the existing privacy checks verify those limits.

A canonical absence certificate must separately preserve the positive cell identity, present-chunk/tower-None distinction, fixed layout, current normal visibility gates, and coherent document/match/tick evidence. It must reject missing or malformed chunks, malformed or overlapping slot partitions, and unknown continuity; old omitted-tower fixtures must not be retrospectively declared complete. Any resulting contract change must be explicit and tested before it can qualify live commands or formal simulator cases.

The bounded live diagnostic retained its original strict coverage. Its sampled match had 32 positive refs and 32 decoded towers, so it supplied no real gap instance and no live absence-certificate validation. The static proof and synthetic cases do not earn M2 event or trajectory credit.
