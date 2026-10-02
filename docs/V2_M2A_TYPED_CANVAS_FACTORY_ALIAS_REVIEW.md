# M2A typed Canvas factory alias trace

## Finding

The typed Canvas component vtable at `0x108f84` contains both relevant method entries: drop index 718, size/alignment 4/4, then method table indices 719, 720, 721, 722, and 723. The pinned element map identifies index 722 as `func874` and 723 as `func1262`. A concrete six-argument dispatcher, `func1873`, reads the method index at vtable +24 and therefore selects `func874` for this vtable. Its receiver-data flow, followed by `func874`, is `trait-object pair.data -> one-word box -> captured Rc pointer -> component+56`.

Independently, `func445` constructs a 52-byte Rc-shaped object, writes a two-word pair at Rc-header +24/+28, boxes its pointer in a 4-byte cell, and forms a trait-object pair using this exact vtable address. The stored pair words come from `var12`/`var13`, copied from the preceding temporary record's +16/+20 fields. This ties the concrete props-like allocation to the same factory type. The static call/argument chain does not prove that this exact local pair is the `func1873` receiver at either observed caller, nor that `func1262`'s `i64.load(*var3)` aliases this exact allocation. Those final invocation aliases remain **UNKNOWN**.

## Vtable and method dispatch

Artifact: pinned `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.wasm`; WAT is `runtime/research/v2/disassembly.json` (`lines`, `offsets`). A narrowly targeted aligned-word search of initialized static data for adjacent table indices 722/723 found the relevant pair at `0x108f9c`; the preceding words establish the enclosing record at `0x108f84`:

`0x108f84: [718, 4, 4, 719, 720, 721, 722, 723]`

Thus the method slot at byte offset +24 is 722 (`func874`) and +28 is 723 (`func1262`). The following record begins at `0x108fa4` with `[617, 4, 4, 724, ...]`, so it is not the record containing 722/723. Direct WAT references to `0x108f84` occur at the `func445` constructor site (line 20712, offset `0x14f37`) and wrapper `func3732` (line 575689, offset `0x13cc05`).

`func1873` (lines 468275-468306; offsets `0x103ec5-0x103eff`) receives a trait-object pair as `param1`: it loads data pointer `*(param1+0)` into the first method argument and vtable pointer `*(param1+4)` into `var9`, then calls indirectly using `*(var9+24)`. The six arguments are its output cell, data pointer, `param2`, `param3`, cloned `param4`, and `param5`. For vtable `0x108f84`, the indirect-call index is the static word at `0x108f9c` (=722), selecting `func874`. This is an exact dispatcher/slot match, rather than a direct `call func874` (the targeted direct-call search found none).

The two direct call sites of `func1873` are in `func457` at WAT line 56967/offset `0x2a476` and `func644` at line 245227/offset `0x90368`. `func457` supplies `var7+152` as its trait-object pair; `func644` supplies `var6+272`. Neither site in the bounded trace materializes constant `0x108f84` immediately before the call, so they are candidate generic uses, not proof that the `func445` pair reaches either invocation.

## Rc and callback-pair dataflow

In `func445` (function starts at line 18160/offset `0x13781`), the relevant constructor path is at lines 20635-20728 (offsets `0x14e80-0x14f6a`):

- It loads `var12 = *(old_record+16)` and `var13 = *(old_record+20)` at lines 20638-20643 (`0x14e87-0x14e93`).
- It allocates 52 bytes (`align=4`) at lines 20656-20659 (`0x14eb1-0x14eb8`), writes `i64 4294967297` at base +0 (strong/weak header words 1/1), and stores `var12` at new base +24 and `var13` at +28 (lines 20674-20678; offsets `0x14ede-0x14ee5`).
- It allocates a 4-byte cell and stores the new 52-byte allocation pointer in that cell (lines 20699-20704; offsets `0x14f17-0x14f22`). The trait-object pair at local stack `var2+600` is then `{data=cell, vtable=0x108f84}` (lines 20711-20716; offsets `0x14f35-0x14f44`). `func4807` copies 36 bytes beginning at this pair into a 44-byte Rc wrapper (lines 595648-595663; offsets `0x146d12-0x146d36`).

The field offsets agree with the independent CanvasProps drop/read evidence: the 52-byte allocation is an 8-byte Rc header plus 44-byte payload, so header +24/+28 are payload +16/+20. `func539` reads the former pair at component+56 Rc-header +24/+28, while `func4426` drops payload +16/+20. This supports treating the two writes in `func445` as the callback-pair producer for the props-shaped allocation. The old temporary's +16/+20 source values are still not traced back to their original event-handler binding in this bounded pass.

When `func1873` is given a pair shaped like the one built in `func445`, its `data=cell` is passed to `func874` as `param1`; `func874` loads `*(param1)` into `var11` and stores `var11` at the new component object's +56 (lines 310190-310192 and 310228-310233; offsets `0xb1219-0xb1272`). Therefore the explicit conditional alias is:

`func445 new Rc base +24/+28 <- old temporary +16/+20; cell[0] = new Rc base; pair = {cell, 0x108f84}`

`func1873 pair.data -> func874 param1; func874 *(param1) -> component+56; func539 reads component+56 Rc-header +24/+28`

This shows how the actual incoming props Rc reaches `component+56` for the matching vtable, while retaining the unresolved cross-function invocation alias noted above.

## Method 723 boundary

`func1262` is the other method in this same record, at vtable byte offset +28. Its exact typed-wrapper edge remains the one reviewed separately: it passes typed vtable constant `0x110a7c` and `i64.load(*var3)` to `func2533` (WAT lines 401386-401391; offsets `0xe183c-0xe184a`). A separate four-argument indirect call in `func1242` uses an index loaded through offset +28 (lines 396252-396255 and 396381-396384), but the receiver pointer comes from separate `func4584` calls using constants `1115792`/`1115808`; the inspected evidence does not establish that pointer equals `0x108f84`. Consequently this is not used as a proven dispatcher for method 723 here.

The callback-pair producer is now concrete at the `func445` allocation stores, and the method-722 Rc handoff is concrete for the matching vtable shape. The pair's original semantic source and the exact runtime invocation alias between `func445` and a `func1873` caller remain unresolved. No runtime memory, hidden actor state, semantic WASM invocation, or core/guard files were used or changed.
