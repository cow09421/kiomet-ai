# M2A Canvas mouse callback message binding review

## Finding

The statically mapped callback at vtable `0x1137a8` is a queueing wrapper: `func4041` calls `func6798` with its captured-data pointer, the incoming JavaScript event handle, and tag 9. `func6798` writes tag 9 and the unchanged handle into a temporary message, then `func2181` copies 248 bytes from it into the queue; if the queue was empty, `func2181` calls `func4173`. The capture data passed to this callback is 16 bytes (four 32-bit words), cloned from `func445`'s input at `+49016`; it is not an 8-byte callback pair. `func2636` shows two retained pointer words, one helper-cloned word, and one copied word, but the semantic names of those fields remain **UNKNOWN**.

This proves a concrete tag-9 queue producer and a conditional queue wake. It does **not** prove that the queued event reaches `func1242`, nor that this callback pair is the one registered as the Canvas mouse listener. `func1242` independently contains mouse-event-name branches and `KiometGame::peek_mouse` calls, but no static edge in this bounded trace connects tag 9 or its queued JavaScript handle to those branches. The producer that originally populated the input record at `var1+49016` is likewise **UNKNOWN**.

## Captured state and message construction

Artifact: pinned `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.wasm`; WAT is `runtime/research/v2/disassembly.json` (`lines`, `offsets`). This review uses only pinned static evidence, with at most two new callee bodies followed from the callback: `func6798` and `func2181`.

The previously reviewed `func445` source clone is from `var1+49016` into stack storage at `var2+600` via `func2636` (WAT lines 18207–18220; offsets `0x13848–0x1388b`). In `func445`, the stack record is copied as two i64 words from `var2+600` and `var2+608` into the Rc payload at +8/+16 (e.g. lines 18225–18238; offsets `0x1386d–0x1388b`). The clone helper `func2636` treats this as a 16-byte record: it retains the pointers at source offsets 0 and 4, clones the value at offset 8 through `func4590`, and copies the word at offset 12 (WAT lines 514355–514397; offsets `0x11ba47–0x11baa1`). The outer closure Rc therefore carries four words. The exact meanings of the four words are not established by these operations.

The callback mapping from the prior review is `0x1137a8` -> invoke slot `+20 = 1152` -> element-table entry `func4041`. `func4041` forwards its two arguments and tag 9 to `func6798` (WAT lines 579402–579407; offsets `0x13eba7–0x13ebb1`). `func6798` stores its third argument as a byte at temporary +8 and its second argument as an i32 at +12, then loads two fields from its first argument and calls `func2181` (WAT lines 627124–627145; offsets `0x15773f–0x157769`). In this call, the second argument remains the JavaScript event handle supplied by the callback adapter; only its numerical value is forwarded, with no conversion in `func6798`.

`func2181` obtains the queue, grows it by 248-byte entries when full, copies exactly 248 bytes from the message pointer, increments queue length, and calls `func4173` only when the prior queue length was zero (WAT lines 489252–489310; offsets `0x10e496–0x10e50b`). In the message source written by `func6798`, the proven fields are the variant/tag byte 9 at message offset 0 and the event-handle word at offset 4. This trace does not assign meanings to the remaining bytes or establish when or where the queued item is drained.

## Mouse and app-handler boundary

The fixed generated adapter `func1359` performs MouseEvent filtering and invokes the callback at its vtable's `+20` slot (WAT lines 408406–408541; offsets `0xe5512–0xe5532`). Therefore, **if** the pair with vtable `0x1137a8` is the pair supplied to that adapter, its invoke target is `func4041`, and that MouseEvent handle is queued under tag 9. The inspected constructor/registration evidence does not prove that conditional alias for this pair; the accepted Canvas factory and props reviews keep the final `func539` listener pair alias unresolved.

Separately, `func1242` checks raw event-name strings for mouse cases and calls `KiometGame::peek_mouse` at offsets including `0xe0042` and `0xe01a0` (WAT lines 398882 and 399034; see also the mousedown/mouseup comparisons around `0xdf605` and `0xe0155`). No direct call, table-slot forwarding, queue consumer, or argument-copy edge reviewed here joins the tag-9 message from `func2181` to `func1242`'s `peek_mouse` branches. The equality of the callback's tag value to any event-related number in `func1242` is not evidence of such a dispatch. Thus “MouseEvent tag 9 reaches `func1242` and `peek_mouse`” remains **UNKNOWN**.

Likewise, the only proven predecessor of the `func445` capture block is the input field at `var1+49016`; the inspected two-layer chain does not identify the code that populated that field. The occurrence of the same numeric offset in `func1242` does not establish object identity or aliasing. No global negative claim is made about other writers or routes.

No live/browser interaction, hidden actor inspection, semantic WASM execution, guard/core edit, or commit was used.
