# CanvasProps Rc allocation review

Static review of the pinned WASM only (`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`). No runtime, live browser, or input was used.

## Anchored target type

`CanvasProps::type_id` at WASM offset `0x14f944` writes the two-word TypeId loaded from static addresses `1084196` and `1084204` (`0x14f954` onward). The component-props comparator at `func1462` (`0xef1aa`) performs the indirect type check and calls the named `CanvasProps::eq` (`0x106bb6`) only after the type-id comparison matches. Replaced/equal props are released through `func4917` (`0x1482ed`): it calls `func4426` on `Rcbase+8`, then deallocates exactly 52 bytes at `0x14832a` with `func5412`.

That fixes the relevant representation as an 8-byte Rc header followed by a 44-byte `CanvasProps` payload. `func4426` drops payload fields at offsets 8, 16/20, 24, and 32. The offset-16/20 pair is passed to `func5853`, which forwards it to `func4789`; it is not one of the `func4418` drops. `CanvasProps::eq` compares payload offsets 0, 8, 16, 24, 32, and 40. These typed accesses are more discriminating than allocation size alone.

## Layout-only pair-writer candidate

The allocation/layout candidate reviewed here is in `func3182`, beginning at `0x12efbd`. At `0x130597` it calls `func3670` with alignment 4 and size 52. The returned pointer is initialized as an Rc (`i64.const 4294967297` at the allocation base). Its payload fields are copied from the same temporary record as follows:

| Source in `func3182` | Destination from Rc base | Relevance |
| --- | --- | --- |
| `var2+1256`, 8 bytes (`0x1305d6`) | `+8` | payload `+0` |
| `var2+1264`, 8 bytes (`0x1305e1`) | `+16` | payload `+8` |
| `var2+1272`, 8 bytes (`0x1305ec`) | `+24` (`0x1305f0`) | payload `+16/+20`, the requested two-word pair |
| `var2+1280`, 4 bytes (`0x1305fb`) | `+32` | payload `+24` |

The following constructor writes scalar/pointer fields at base offsets 36, 40, 44, 46, 48, and 49, covering the remaining payload positions through byte 43. Thus the pair writer is a real source-to-destination copy, not an unrelated 52-byte allocation: its field offsets align with the named `CanvasProps::eq` fields and with the nested drops in `func4426`.

The new pointer is later copied into a child-node record at `var17+16` (`0x130a07`). The disassembly segment reviewed here does not close the final edge from that child record to `Component+56` or show a direct call to `CanvasProps::type_id` at construction time. The layout match does not establish the dynamic type; do not treat the 52-byte allocation alone as constructor identity. The subsequent pair-stack trace identifies this allocation as a NexusDialog callback capture, rather than a proven CanvasProps constructor (see `V2_M2A_CANVAS_PAIR_STACK_PRODUCER_REVIEW.md`).

## Similar allocation rejected as type evidence

`func445` also allocates 52 bytes at `0x14eb5` and writes a two-word pair at base offsets 24/28. It is not promoted as the CanvasProps constructor: its surrounding wrapper loads a distinct adjacent TypeId pair from addresses `1084212`/`1084220`, while `CanvasProps::type_id` uses `1084196`/`1084204`. Its size and pair stores therefore do not establish CanvasProps identity. Other size-52 sites in `func442`, `func459`, and `func603` either have different field shapes or copy an existing 52-byte value; none provides a stronger type/pointer chain than `func3182`.

## Bounded conclusion

The requested `Rcbase+24/+28` writer is located at `func3182` offsets `0x1305ec`–`0x1305f0`, copying the qword from source record `var2+1272` into the allocation. Its payload shape agrees with CanvasProps equality and drop behavior, giving only a layout match. This candidate is not the typed CanvasProps producer. The newer `V2_M2A_TYPED_CANVAS_PROPS_CONSTRUCTOR_REVIEW.md` follows an exact CanvasProps vtable reference in func1262 instead. The exact dynamic TypeId binding and final transfer into the known component Rc slot still need one more caller/callback edge before using it to patch callback binding. In the pinned disassembly, the direct loads from `1084196`/`1084204` occur only in the `CanvasProps::type_id` definition; no construction-side reference to those constants was found. No unrelated 52-byte allocator site should be substituted for that missing proof.
