# M2A CTW named receiver identity review

## Finding

The pinned disassembly does not identify `func445` as a CTW `view` method or
`func1242` as the matching CTW `update` method. Both function headers retain
synthetic function names, and neither has an exact direct `call` site in the
WAT. The table entries at indices 436 and 438 therefore do not prove shared
receiver identity. Keep the proposed `func445`/`func1242` CTW update/view
relationship **UNKNOWN**.

Pinned WASM SHA-256:
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`.
The line numbers and byte offsets below are from
`runtime/research/v2/disassembly.json`. This is a bounded static review only;
no live state, memory, semantic WASM execution, guard, or core code was used.

## Function identities and call evidence

The element segment starts at table index 1. Its entries map table index 436
to `func445`, 437 to `func2475`, and 438 to `func1242`. The actual function
headers are at WAT line 18160 / offset `0x13841` and line 363058 / offset
`0xcc7bc`:

| Function | Pinned WAT header | Retained identity |
| --- | --- | --- |
| `func445` | `(i32, i32) -> ()` | synthetic name only |
| `func1242` | `(i32) -> i32` | synthetic name only |

An exact WAT call-site search finds zero direct `call $func445` instructions
and zero direct `call $func1242` instructions. Their table appearances and
the order of those entries do not identify a type or the function that
indirectly calls them with a particular receiver.

The same pinned module does retain named Ctw-related symbols, including
`frontend::Ctw` (function index 496, WAT line 147077), `Ctw::eq` (index 498,
line 149122), and `Ctw::clone` (index 582, line 214730). The disassembly has
no named `Ctw::view` or `Ctw::update` header, and no direct call edge from
those named symbols to either target was found in this bounded check. These
names do not relabel the two synthetic functions.

## Relation to the existing typed Canvas evidence

The established Canvas factory record at `0x108f84` selects table indices
722/723 (`func874`/`func1262`). The typed Canvas component record at
`0x110a6c` selects `func539` at method slot 1024, and the CanvasProps record at
`0x110a7c` supplies its drop and type-id entries. None names table entries 436
or 438 as a matching method pair. The accepted typed-factory review also
records that `func445` constructs a separate trait-object pair using
`0x108f84`; that fact does not turn `func445` itself into one of that
factory's methods.

The earlier bounded CTW vtable review found no validated active-data record
pairing 436 and 438 as a view/update vtable. `func445`'s input record and
`func1242`'s input record each contain data at a matching `+49016` offset, but
matching local offsets do not establish that their bases are the same
receiver allocation. Their headers are also distinct signatures. No direct
call or typed receiver construction closes that alias in the inspected
evidence.

The mouse-like behavior in `func1242` and the callback construction in
`func445` remain useful candidate context from the existing callback reviews,
but they do not prove CTW method roles, common receiver identity, or a route
from the current Canvas listener. No broader table scan or callback-body
retrace is added here.

## Consequence

Keep the static path from the candidate tag-9 callback through a CTW update to
`peek_mouse` **UNKNOWN**. The needed evidence is a typed constructor/receiver
edge or concrete indirect-dispatch call site tying the runtime receiver to
both named method roles. Table adjacency, matching field offsets, and behavior
similarity do not supply that edge. No code fix or formal-corpus credit is
proposed.
