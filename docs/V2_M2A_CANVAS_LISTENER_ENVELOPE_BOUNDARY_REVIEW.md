# M2A canvas listener envelope boundary review

## Finding

The pinned `listen` body constructs a 12-byte listener control envelope. It requests `(align=4, size=12)` from `func3670` at `0x11ea51–0x11ea55`, then writes the supplied closure Rc pointer at envelope `+0` (`0x11ea66–0x11ea6a`), the supplied closure vtable at `+4` (`0x11ea5f–0x11ea63`), and a one-byte control flag at `+8` (`0x11ea58–0x11ea5c`). At `0x11ea6d–0x11ea7c`, it passes the envelope pointer to `__wbindgen_cast_0000000000000004` and passes fixed adapter record `0x13e700` as the second argument.

The pinned cast implementation creates a mutable closure from those two arguments. Under the already-reviewed `makeMutClosure` ABI, that makes the envelope pointer the generated JS closure's `state.a`; `state.b` is the outer adapter record. The static element/data mapping for `0x13e700` to `func1359` is established in the accepted Canvas pair/stack producer review. The current document does not recertify that mapping. The pinned generated JavaScript implements `__wbindgen_cast_0000000000000004` with `makeMutClosure(arg0,arg1,...)` (client.js lines 1869–1872), whose `state` stores `{a: arg0, b: arg1}` (lines 2269–2271). This proves the ABI for closures created through this `listen` path; it does not by itself bind a particular callsite to the currently observed Canvas listeners.

`func1359` reads the envelope's `+8` byte at `0xe5455`. On its dispatch path, it loads envelope `+0` at `0xe5512–0xe5514` and envelope `+4` at `0xe5517–0xe5519`. The latter is used as the closure vtable: `func1359` reads its capture-layout field at vtable `+8` (`0xe551e`), loads its invoke-table index at vtable `+20` (`0xe552f`), and calls indirectly at `0xe5532`. The event handle is forwarded as the second indirect-call argument at `0xe552b`.

Therefore, **in principle**, a separately authorized read of the single 32-bit word at `state.a + 4` would retrieve the current inner closure vtable value and could compare it to candidate `0x1137a8`. The candidate's static `+20` invoke slot maps to `func4041` in the prior accepted original-pair review. No such runtime read or comparison was performed here, and this is not evidence that the current listener uses `0x1137a8`.

## Boundary and limits

The envelope is callback-dispatch control metadata, not an actor record. Its `+0` word is an opaque callback Rc pointer; the adapter uses it to derive the callback capture-data address. That capture may contain application data, so it must not be followed or described as harmless actor-free memory. The `+4` word is the callback vtable/dispatch identity. The `+8` byte is a control flag consumed by the adapter. These fields identify how the callback is invoked; none of them expose actor ownership, units, positions, or game state by themselves.

A narrow `state.a + 4` comparison can avoid following `+0`, but static evidence alone does not establish that the live `state.a` is a valid current envelope pointer, that memory bounds/liveness hold at a future observation, or that the candidate vtable owns the Canvas event route beyond the static function-table mapping. Those require separate provenance and a separately authorized bounded runtime read. The 12-byte allocation shape is not permission to inspect all 12 bytes: the minimal candidate comparison needs only the `+4` word. Do not read the Rc pointer's target or use it to reach callback capture data.

This static review makes no change to phase A, does not run a helper, and does not authorize phase B. No live memory, callback, actor, or world state was read; no guard was relaxed. The current runtime inner callback vtable remains **UNKNOWN**, listener topology and route qualification remain **NONE**, and formal credit remains **0**.

## Sources

- Pinned disassembly `runtime/research/v2/disassembly.json`, hash-pinned WASM `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.wasm`: `listen` at `0x11ea41–0x11ea9c`; relevant envelope writes and cast at `0x11ea51–0x11ea7c`; `func1359` at `0xe543e–0xe5548`, relevant flag read at `0xe5455` and vtable/call path at `0xe5512–0xe5532`.
- [V2_M2A_CANVAS_PAIR_STACK_PRODUCER_REVIEW.md](V2_M2A_CANVAS_PAIR_STACK_PRODUCER_REVIEW.md): pinned adapter record and `func1359` ABI context.
- [V2_M2A_CANVAS_ORIGINAL_PAIR_WRITER_REVIEW.md](V2_M2A_CANVAS_ORIGINAL_PAIR_WRITER_REVIEW.md): candidate `0x1137a8` and its `+20` invoke target mapping.
