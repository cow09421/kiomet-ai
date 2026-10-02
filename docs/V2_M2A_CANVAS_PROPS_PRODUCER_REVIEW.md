# M2A CanvasProps producer trace

## Finding

The pinned WASM identifies the CanvasProps-associated component method and confirms that its mouse-listener callback is read as an `(Rc data pointer, closure vtable pointer)` pair. This bounded pass did not identify the constructor or copy that writes the pair into the `Rc<CanvasProps>` at component offset +56. The callback-to-mouse-handler binding therefore remains **UNKNOWN**.

## Component and table boundary

The artifact is `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.wasm`, with WAT in `runtime/research/v2/disassembly.json`.

- There are no direct `call $func539` sites in the WAT. `func539` is present at element table index 1024 (element segment at WAT line 447), so its caller edge is indirect through the component machinery.
- Its immediate table neighborhood is 1020 `PropertiesWrapper::type_id`, 1021 `func1007`, 1022 `UnitIconProps::type_id`, 1023 `func5270`, 1024 `func539`, 1025 `func4426`, and 1026 `CanvasProps::type_id`. This identifies `func539` as the CanvasProps-associated component method adjacent to its drop glue and type-id method; it does not expose an app-side props constructor.
- The only direct WAT caller of `func4426` is `func4917` at line 598401 / offset 0x148309, after its reference-count decrement reaches zero. This is a destruction edge, not a props writer.

## Props pair read and ownership

In `func539`, the pointer at component +56 is loaded into `var3` (WAT lines 183085–183087; offsets 0x6f184–0x6f189). The mouse event loop obtains the two adjacent words at `var3+24` and `var3+28` and passes them to `func4036` (lines 183180–183184; offsets 0x6f287–0x6f291). `func4036` increments the refcount rooted at the first word, stores that captured data pointer at pair offset 0, and stores the second word—the closure vtable pointer—at pair offset 4 (lines 579351–579356; offsets 0x13eb3c–0x13eb47). The loop reuses this same pair for its mousedown and mouseup listener descriptors.

Offset bases matter here. `var3` is the `Rc<CanvasProps>` header loaded from component +56, while `func4917` passes `var0 + 8` to `func4426` after the outer strong count reaches zero (WAT lines 598386–598401; offset 0x148304–0x148309). Thus `func4426` receives the CanvasProps payload base, eight bytes past the Rc header. The listener pair read by `func539` from Rc-header offsets +24/+28 is therefore at CanvasProps payload offsets +16/+20.

`func4426` confirms this pair's drop path: it loads payload offsets +16 and +20 and passes the two words to `func5853` (lines 588242–588246; offsets 0x14321e–0x143228). `func5853` calls `func4789(captureRc, closureVtable)` only when the capture pointer is nonzero (lines 615092–615098; offsets 0x1513ab–0x1513b7). In `func4789`, the first word of `captureRc` is decremented; when it reaches zero, the function loads the vtable's first word and conditionally invokes that indirect destructor on the capture data at offset 0x146aeb (lines 595353–595381; offsets 0x146ab8–0x146aee). It then decrements the separate allocation reference at `captureRc+4` and frees the allocation when that count reaches zero, except for the `-1` sentinel path (lines 595382–595419; offsets 0x146aef–0x146b34). So this is a drop of the captured data/vtable pair, not a `func4418` drop of payload +24 and not an independently ignored vtable word. Separately, `func4426` sends payload +8, +24, and +32 to `func4418` (lines 588238–588254); those are distinct fields and do not describe the mouse listener pair.

## Constructor boundary and next edge

The exact static edge established here is:

`component+56 -> Rc<CanvasProps> header -> (header+24/+28 = payload+16/+20: captured Rc, closure vtable) -> func4036 clone -> listen -> func1359 -> call_indirect(load(vtable+20))`.

The constructor/copy edge into the two CanvasProps words is still missing. Since `func539` has no direct caller, resolving it requires identifying the indirect component invocation that supplies this Rc and following that invocation's props construction or copy. The current evidence does not authorize substituting a nearby app callback vtable: the candidate at 0x113b08 stores a 16-byte payload from its second argument, while func1359 passes a JavaScript event handle unchanged. No static MouseEvent-compatible vtable writer was found in this bounded pass.

No runtime heap, actor state, or semantic WASM call was used. No guard or core files were modified.
