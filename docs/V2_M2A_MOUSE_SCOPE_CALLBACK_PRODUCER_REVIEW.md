# M2A mouse scope callback capture producer review

## Finding

`func445` clones a 16-byte record from its input at `var1+49016` into an Rc capture block. The helper `func2636` handles four 32-bit words: it retains words at +0 and +4, clones the value at +8 via `func4590`, and copies +12. `func445` later reads the first two words directly from the same input field and passes them as the first two arguments to `func2181`, establishing that those words are the queue and conditional wake inputs used by that path. This is concrete evidence that the capture block carries queue-related state; the semantic identities of the remaining two words are **UNKNOWN**.

`func1242` independently reads its receiver's `+49016` field, then passes the first two words of that field to `func2181` in its own event path. This structural match does not establish that `func445`'s `var1` aliases `func1242`'s receiver, that both fields are the same Scope/App allocation, or that tag 9 from the `0x1137a8` callback is dispatched to `func1242`'s mouse branches. No positive static constructor write to the `+49016` block or owner link to the broker/UI root is established in this bounded review.

## Four-word capture block

Artifact: pinned `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.wasm`; WAT is `runtime/research/v2/disassembly.json` (`lines`, `offsets`). The new callee depth is limited to `func2636` and its called helper `func4590`; the known queue-copy path is not retraced here.

At `func445` offsets `0x1385a–0x13863` (WAT lines 18216–18220), the function forms `var1+49016` and passes it to `func2636`, with destination `var2+600`. It then reads two i64 values at `var2+600` and `var2+608`, storing them at offsets +8 and +16 of a 24-byte Rc allocation (offsets `0x1387c–0x1388b`; WAT lines 18227–18234). These stores preserve a 16-byte block as four 32-bit words in the Rc payload.

`func2636` confirms this is a 16-byte owned record rather than a two-word closure pair (WAT lines 514355–514397; offsets `0x11ba47–0x11baa1`). It increments the strong count through the pointers in source words +0 and +4, passes source word +8 to `func4590`, writes the resulting clone at destination +8, and copies source word +12 to destination +12. This supports the following structural description:

| Source word | Clone operation in `func2636` | Semantic status |
| --- | --- | --- |
| +0 | Retain referenced allocation | **UNKNOWN** |
| +4 | Retain referenced allocation | **UNKNOWN** |
| +8 | Clone through `func4590` | **UNKNOWN** |
| +12 | Copy unchanged | **UNKNOWN** |

The closure vtable `0x1137a8` reviewed separately selects `func4041` at invoke slot +20. When `func4041` calls `func6798`, its first argument is the capture-data pointer, and `func6798` reads words +0 and +4 from that pointer as the first two `func2181` arguments. That agrees with the queue-related front words. It does not identify or consume capture words +8/+12 in this invocation.

## Same-offset queue use and owner boundary

Within `func445`, offsets `0x13f79–0x13f8a` (WAT lines 18963–18969) load `var1+49016` and `var1+49020`, then pass those values and a message address to `func2181`. In `func1242`, the function forms `var0+49016` at `0xcc81e` and later loads its words at `0xcca2d`/`0xcca32` for another `func2181` call at `0xcca3d` (WAT lines 363196 and 363425–363432). `func1242` also contains independently established mousedown/mouseup name checks and `KiometGame::peek_mouse` calls, including `0xdf605`, `0xe0155`, `0xe0042`, and `0xe01a0`.

The matching offset and queue-call shape establish a useful structural parallel, not receiver identity. The exact-offset search in the pinned WAT found these relevant uses: `func445` forms the source pointer at `0x1385c` and loads the first two words at `0x13f79/0x13f80`; `func572` passes `+49016` to `func4182` at `0x7cf78`; `func1242` loads `offset=49016` at `0xcc7e8` and forms the field pointer at `0xcc81e`; and `func2475` clones from `+49016` at `0x115c82`. These are source reads, address passing, clone, or drop operations; this search did not reveal a direct store with an exact `49016`/`49020` immediate. It does not normalize other base-plus-offset expressions or bulk copies. This pass did not identify a constructor that stores the four-word block at that offset, nor a direct/indirect call argument edge tying `func445`'s `var1` to `func1242`'s `var0`. The same numeric field offset alone cannot close that alias.

Consequently, whether the source block belongs to a Scope, ClientBroker, `KiometGame`, or another owner remains **UNKNOWN**. The constructor/owner link from the field to the UI broker root, the exact identities of all four capture words, and the queue consumer's route from tag 9 to `func1242` remain **UNKNOWN**. No global claim is made about unreviewed bulk copies or other writers. No live/browser action, hidden actor read, semantic WASM execution, guard/core edit, or commit was involved.
