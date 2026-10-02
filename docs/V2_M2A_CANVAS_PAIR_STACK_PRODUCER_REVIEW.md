# M2A candidate pair stack producer review

Static review of pinned WASM `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`. No runtime, browser, or input was used.

## Pair source and bounded producer chain

The candidate 52-byte allocation in `func3182` is at `0x130597` (`func3670(4, 52)`). Its `Rcbase+24/+28` pair is copied by `i64.load offset=1272` / `i64.store offset=24` at `0x1305ec`–`0x1305f0`. The nearest preceding producer for that stack record is the `func5158` call at `0x130431`, with destination `var2+1256` and source `var2+832`; that cloned record is then the source of the 52-byte allocation's fields.

`func5158` calls `func2138` for the first 12 bytes and `func4527` for the tail beginning at offset 16. For the tail, `func4527` tests the source tag and, on the populated branch, calls `func2901(dst, src+4, src+8)`. This is an indirect clone of a tagged payload; the helper chain does not load a static vtable address or reveal the runtime words at `var2+848/+852`. The record at `var2+832` was initially copied from `func565`'s result (`func565` call at `0x12f056`, then its output fields copied into `var2+832..856`). Within the two-layer bound, the high word of the inner pair at `var2+1276` therefore remains **UNKNOWN**. No concrete static closure-vtable address can be assigned to that inner pair from this chain.

## Concrete outer closure pair and invoke target

The same control path does expose a separate, concrete closure pair. After building the 52-byte Rc at `var12`, `func3182` carries the branch result `1128864` into `var4` (`0x130817`), then stores `var12` and `var4` at offsets +16/+20 of the `NexusDialogPropsBuilder` value (`0x130a07` and `0x130a00`). This pair is therefore `(capture Rc = var12, closure vtable = 1128864)`. The Rc has an 8-byte header and 44-byte capture payload, matching the vtable's recorded capture size 44 and alignment 4. The builder path is explicitly `NexusDialogProps::builder` at `0x1309b5`, followed by `NexusDialogPropsBuilder::title` at `0x130a33`.

The pinned WASM data segment covering address `1128864` has words:

| Vtable offset | Value | Table function |
| --- | ---: | --- |
| +0 | 1205 | `func6000` |
| +4 | 44 | capture size |
| +8 | 4 | capture alignment |
| +12 | 1206 | `func6319` |
| +16 | 1207 | `func2090` |
| +20 | 1207 | `func2090` |
| +24 | 1208 | `func5139` |

The `func1359` callback adapter loads the function-table index from vtable+20 and calls it indirectly with two `i32` arguments (`0xe552b`–`0xe5535`). The first is the aligned capture-data address derived from the capture Rc and vtable size/alignment. The second is the event handle passed into `func1359`; the adapter forwards it unchanged. `func2090` stores that second argument in its local frame and passes it as the final argument to `func3432` (`0x10b73f`–`0x10b743`), while reading callback state from the captured memory. Thus this outer callback receives a memory capture payload plus a JavaScript event handle.

## Canvas association

The static vtable at `1128864` is attached to the `NexusDialogPropsBuilder` callback pair in this path. The 52-byte allocation is used as that closure's capture Rc. This is a concrete mouse-event-compatible closure, but it does not establish that the allocation is `Rc<CanvasProps>` or that the inner dynamic pair copied into its +24/+28 is the Canvas mouse callback. In the reviewed region, the builder/name path is NexusDialog; no transfer into the Canvas-associated component slot at +56 or component method/table 1024 / type-id table 1026 is shown. Therefore exclude this path as proof of the CanvasProps pair writer. CanvasProps-specific producer and its inner pair's vtable remain **UNKNOWN**.
