# M2A typed CanvasProps constructor trace

## Finding

The active-data record at `0x110a7c` is a concrete typed vtable record for `CanvasProps`: its drop slot is table index 1025 (`func4426`), its size/alignment are 44/4, and its type-id slot is index 1026 (`CanvasProps::type_id`). The adjacent word at `0x110a78` is index 1024 (`func539`), the component method that reads the CanvasProps callback pair. The earlier claim that there was no code immediate referencing the typed vtable was incorrect: `func1262` passes the exact address `0x110a7c` to `func2533`, which copies the typed pair into a 20-byte wrapper and registers it through `func3547`. Separately, `func874` constructs a 76-byte component object with field +56 copied from the first word of its `param1` input, then registers it with the containing-component vtable at `0x110a6c` (`func539` at method slot 1024). These are concrete producer edges, but the bounded static trace does not prove that `func1262`'s output is the `param1` value supplied to `func874`; the final alias from typed props wrapper to that component field remains **UNKNOWN**.

## Static typed-record and reader edges

Artifact: pinned `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.wasm`; WAT in `runtime/research/v2/disassembly.json` (`lines` and `offsets`). The active-data words at `0x110a7c` begin `[1025, 44, 4, 1026, 975, 76, 4, 1027, 975, 76, 4]`. The first record identifies the typed drop method and type-id method; table 1025 maps to `func4426`, and table 1026 maps to `CanvasProps::type_id` (the method body is at WAT lines 612606–612615). This is consistent with the component method at adjacent table index 1024 being `func539`. The numeric mapping sequences at `0x11ccf8` and `0x11fcb4` are not used as vtable records in this trace.

In `func539` (WAT line 183018; offset `0x6f10c`), the component's field +56 is loaded into `var3` (lines 183085–183087; offsets `0x6f184–0x6f189`). The mouse-listener path reads the adjacent words at Rc-header +24/+28 and passes them to `func4036` (lines 183180–183184; offsets `0x6f287–0x6f291`). `func4036` clones the first word as the captured Rc and preserves the second as its closure vtable in the listener pair (lines 579351–579356; offsets `0x13eb3c–0x13eb47`).

The destructor confirms the payload basis: `func4917` passes its Rc payload at `var0+8` to `func4426` only after the outer Rc count reaches zero (lines 598386–598401; offsets `0x1482ed–0x148309`). `func4426` then forwards payload +16/+20 to the closure-pair drop path, which is the same pair as Rc-header +24/+28 (lines 588242–588246; offsets `0x14321e–0x143228`). Its other `func4418` fields are payload +8, +24, and +32 and do not write or identify the listener pair.

## Concrete typed-wrapper and component edges

The exact typed-vtable immediate occurs in `func1262` (table slot 723). At WAT lines 401386–401391 (offsets `0xe183a–0xe184a`), it passes `local.get $var5`, the constant `1116796` (`0x110a7c`), and an `i64.load` from `local.get $var3` to `func2533`. Thus this is an exact code reference to the CanvasProps vtable, not an absent-xref case.

`func2533` (lines 506659–506703; offsets `0x117250–0x1172b2`) allocates 20 bytes. It writes the incoming i64 pair at allocation +0, the other two i32 arguments at +8/+12, and the typed vtable pointer at +16. It then supplies that record and constant `1343928` to `func3547` with a context pointer at +36. This proves a concrete typed CanvasProps wrapper-registration edge carrying the two words loaded by `func1262`; it does not alone establish which source fields those words alias.

The neighboring element-table method `func874` is at slot 722. In its body (lines 310116–310287; offsets `0xb1175–0xb12f3`), it loads `*(param1)` into `var11`, allocates a 76-byte component object, and stores `var11` at object +56 (lines 310190–310192 and 310228–310233). It then passes component vtable constant `1116780` (`0x110a6c`) and the new object to `func2850` (lines 310282–310287). Active data at `0x110a6c` identifies this containing-component vtable: drop slot 1023 maps to `func5270`, size/alignment are 76/4, and method slot 1024 maps to `func539`. `func2850` records the component/vtable through `func3547` and registers its closure through `func549` (lines 531304–531341).

Therefore the bounded producer/use graph is:

`func1262 --(0x110a7c, i64 pair from *var3)--> func2533 --(20-byte typed wrapper)--> func3547 at context+36`

`func874 --(*(param1) stored at component+56)--> component vtable 0x110a6c --(method 1024)--> func539 --(Rc-header+24/+28)--> func4036 listener clone`

`func1262` and `func874` occupy adjacent table slots, but no direct call or proven argument-forwarding edge joins these paths in the inspected static evidence. Accordingly, the actual source writer/field alias for the callback pair at the `func874` `param1` boundary remains unresolved. The reader/drop/listener identity and the typed wrapper producer are now narrowed concretely; no handler binding is claimed. No runtime memory, actor state, or semantic WASM call was used; no core or guard file was modified.
