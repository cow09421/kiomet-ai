# M2A original Canvas callback-pair writer review

## Finding

The callback pair later read from the `func445` 60-byte temporary at `+16/+20` is written in that same function. Its capture word is a newly allocated Rc containing a clone of the callback pair from the caller record at `var1+49016`; its closure-vtable word is the concrete constant `1128360` (`0x1137a8`). The stored vtable record has invoke slot `+20 = 1152`, and the pinned element segment maps table index 1152 to `func4041`. The concrete `func4041` body forwards its two arguments to `func6798` with tag 9. This identifies the pair's static invoke mapping and wrapper shape; it does not identify the caller-record pair's runtime values or prove which UI action supplies that record.

## Source record and pair construction

Artifact: pinned `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.wasm`; static WAT is `runtime/research/v2/disassembly.json` (`lines`, `offsets`). No runtime inspection or WASM execution was used.

In `func445` (function begins at WAT line 18160), the function's locals are listed at lines 18160–18206. The stack slot `var2+600` receives a clone of the pair at `var1+49016/+49020` through `func2636` at lines 18207–18220 (offsets `0x13848–0x1388b`); the pair is copied as two i64 words at `var2+600` and `var2+608`, so the copied capture block spans 16 bytes. This gives the relevant field its concrete predecessor in `func445`'s input record while leaving that input record's upstream writer outside this bounded trace.

The 60-byte temporary is allocated into `var3` at line 20444 (offset `0x14cb2`). Its +16/+20 words are initialized at lines 20497–20504 (offsets `0x14d2e–0x14d3d`): constant `1128360` (`0x1137a8`) is stored at `var3+20` at `0x14d33`, and `var6`, an Rc box populated from the 16-byte cloned block at `var2+600/+608`, is stored at `var3+16` at `0x14d3a`. Later, the exact source loads requested for this trace read `var3+20` into `var13` at lines 20638–20641 (`0x14e87–0x14e8c`) and `var3+16` into `var12` at lines 20641–20643 (`0x14e8e–0x14e93`). `func445` copies those words into the new 52-byte Rc payload at offsets +28/+24 respectively (lines 20674–20677; offsets `0x14edc–0x14ee5`). This is the pair reboxed as the CanvasProps-shaped pair documented in the typed Canvas factory review; the distinct outer trait-object vtable `0x108f84` formed at `0x14f37` is not the callback-pair vtable.

Thus the direct construction chain is:

`func445 input +49016/+49020 -> func2636 clone -> 16-byte block at var2+600/+608 -> Rc copy in var6 -> temporary var3+16 = var6, var3+20 = 0x1137a8 -> load at 0x14e87..0x14e93 -> new Rc payload +24/+28`

## Vtable and invoke mapping

Read-only decoding of pinned active data at `0x1137a8` yields words `[358, 16, 4, 1151, 1152, 1152, 1134]`. For the closure layout used by the event adapter, the invoke slot is byte offset +20, hence table index 1152. The single pinned element segment begins at table index 1; its entry at index 1152 is `func4041` (WAT element segment line 447). `func4041` is at WAT lines 579402–579407 / offsets `0x13eba7–0x13ebb1`; at `0x13ebae` it passes its two `i32` arguments and constant 9 to `func6798`. The generic MouseEvent wrapper `func1359` performs the indirect call through vtable +20 at WAT lines 408513–408529 / offsets `0xe552b–0xe5535`, so a pair with this vtable dispatches to `func4041` when passed through that adapter.

This does not establish that this pair is the eventual `func539` listener input, because the accepted CanvasProps producer review leaves the allocation-to-component invocation alias unresolved. Nor does the bounded chain show who wrote `var1+49016`, identify its own captured closure's dynamic invoke target, or establish a human-facing semantic label for tag 9. Those remain **UNKNOWN**. This review does not repeat the generic `func1873` factory-dispatch trace and makes no global claim about other possible writers or handlers.

## Scope

The trace is limited to the constructor region in `func445`, the static closure record and element mapping, and the direct adapter/invoke bodies needed to name the mapped call. No live/browser action, hidden actor state, semantic WASM invocation, guard/core edit, or commit was involved.
