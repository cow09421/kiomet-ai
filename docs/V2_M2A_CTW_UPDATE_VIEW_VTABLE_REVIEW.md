# M2A CTW update/view vtable review

## Finding

The pinned element segment maps table indices 436 and 438 to `func445` and `func1242`, respectively, with index 437 between them mapping to `func2475`. That ordering does not by itself prove a shared trait or component. The WAT signatures also differ: `func445(i32, i32) -> ()` and `func1242(i32) -> i32`. In the inspected static vtable/factory records, the Canvas factory at `0x108f84` selects indices 722/723 (`func874`/`func1262`), while the typed Canvas component and props records use indices 1023/1024 and 1025/1026. None of these records selects 436 or 438.

No inspected active-data record establishes `func445` as a CTW `view` method and `func1242` as the matching `update` method on one receiver type. The direct queue callback for the 16-byte capture enters `func6798` and the shared enqueue/wake path; the generic asynchronous consumer's poll slot has not been resolved to `func1242`. Therefore the static route `MouseEvent -> tag 9 -> CTW update func1242 -> peek_mouse` remains **UNKNOWN**. The callback's eventual Canvas listener binding remains **UNKNOWN** as well.

## Element table and receiver evidence

Artifact: pinned `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.wasm`; WAT is `runtime/research/v2/disassembly.json` (`lines`, `offsets`). The element segment starts at table index 1 (WAT line 447). The entries in question are:

| Table index | Function | WAT signature |
| ---: | --- | --- |
| 436 | `func445` | `(i32, i32) -> ()` |
| 437 | `func2475` | `(i32, i32) -> ()` |
| 438 | `func1242` | `(i32) -> i32` |

`func445`'s input record at `var1+49016` is a 16-byte capture block, and `func445` uses its first two words as inputs to `func2181` (offsets `0x1385c`, `0x13f79–0x13f8a`). `func1242` separately uses the first two words from its own `var0+49016` field as inputs to `func2181` (offsets `0xcc81e`, `0xcca2d–0xcca3d`). This is a matching field offset and call shape, but neither the immediate caller edges nor a shared receiver pointer/type descriptor are present in those operations. The element-index adjacency does not close this alias.

## Static vtable/factory records

The concrete factory record at `0x108f84` is `[718, 4, 4, 719, 720, 721, 722, 723]`; its methods at byte offsets +24/+28 dispatch to table indices 722/723, which map to `func874` and `func1262`. `func445` writes this address into the separate trait-object pair it constructs at `0x14f37`. Thus this factory's actual method slots do not select table indices 436 or 438.

The typed Canvas component record at `0x110a6c` identifies drop index 1023, size/alignment 76/4, and component method index 1024 (`func539`). The adjacent CanvasProps typed record at `0x110a7c` identifies drop index 1025, size/alignment 44/4, and type-id method index 1026. These records establish the Canvas component/props relation reviewed in the accepted constructor document, but do not include 436 or 438 as their dispatch methods.

A bounded aligned-word scan of active data for values 436 and 438 found no validated vtable record that contains both as the matching view/update methods. One nearby occurrence at `0x1079b8` is referenced as translation text by `Translator::translate_phrase` at WAT line 555184 / offset `0x1320d1`, so that sequence is not treated as a vtable. Other value occurrences examined did not provide a constructor reference or the established vtable shape. This is a bounded finding, not a claim that no such record can exist through unexamined encodings or constructed memory.

## Queue consumer boundary

For the `0x1137a8` callback, the known path is `func4041 -> func6798 -> func2181`; `func2181` calls `func4173` only when the queue was empty. The generic callback/executor path then schedules a future poll. The accepted input-callback descriptor review leaves the later indirect poll target unresolved and does not connect it to table index 438. Within this review's two-new-callee bound, no queue consumer slot can be assigned to `func1242`, and no evidence ties the tag-9 message's JavaScript handle to `func1242`'s raw mouse-name branches or `KiometGame::peek_mouse` calls.

No static source-to-handler semantic route is claimed. Type identity between the `func445` receiver and `func1242` receiver, CTW view/update role labels, the constructor or store for `var1+49016`, the queue drain/poll target, and the final listener alias all remain **UNKNOWN**. No live/browser action, hidden actor read, semantic WASM execution, guard/core edit, or commit was involved.
