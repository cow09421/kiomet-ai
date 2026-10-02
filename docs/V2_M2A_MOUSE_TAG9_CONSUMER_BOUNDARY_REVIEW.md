# Mouse callback tag-9 consumer boundary review

## Finding

The pinned static source proves that the reviewed closure callback writes
discriminant byte `9` into a message passed to the shared queue. It does not
prove that this is the message variant consumed by `func1242`'s mouse-name and
button branches. Keep that producer-to-handler identity **UNKNOWN**. In
particular, the matching presence of the number 9 elsewhere is not an alias
or dispatch edge.

Artifact: pinned WASM
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`;
WAT is `runtime/research/v2/disassembly.json` (`lines`, `offsets`).

## Producer trace

The closure invoke method `func4041` is only six WAT instructions long. At
WAT lines 579403–579406 (binary offsets `0x13eba8–0x13ebae`), it forwards its
two arguments and constant `9` to `func6798`:

```wat
local.get $var0
local.get $var1
i32.const 9
call $func6798
```

At WAT lines 627131–627144 (offsets `0x15774c–0x157769`), `func6798` stores
that third argument as one byte at temporary-record offset `+8`, stores its
second argument at `+12`, loads two words from its first argument at `+0` and
`+4`, and calls `func2181` with those words and a pointer to the record at
`+8`. This proves the producer-side tag and message shape for this callback.
It does not, by itself, assign a semantic name to tag 9 or identify the
queue's eventual consumer. The queue append/wake behavior of `func2181` is
covered by the existing input-callback review and is not retraced here.

## Comparison with the mouse branches

The existing bounded `func1242` review identifies direct event handling at
WAT/binary offsets `0xdf605` and `0xe0155`: the function compares the incoming
event name against `mousedown`/`mouseup`, reads the JavaScript event's button
at `0xe0176`, and calls `KiometGame::peek_mouse` in the corresponding paths
(including `0xe0042` and `0xe01a0`). The inspected branch works from the event
name and event handle. It is not shown loading the queued record's byte at
`+8`, nor does the branch contain a proven edge from `func2181`'s queued tag
to those event comparisons.

Other uses of numeric constant 9 in this function are not discriminant
evidence: for example, the mouse-name comparison passes a string pointer and
length 9 to `func4701`. Matching that string length to the producer's byte
value would conflate unrelated values and operands.

The exact missing edge is the typed queue-consumer/poll target that receives
the message written by `func4041 -> func6798 -> func2181` and then enters
`func1242` with the JavaScript event handle used by its mouse branches. The
reviewed capture layout, equal field offsets, queue call shape, table ordering,
and matching small constants do not establish that edge. Do not attribute
tag 9 to mousedown/up processing or grant it handler-level evidence until a
typed receiver or concrete dispatch path closes this boundary.

This review is source-only and bounded to the existing producer chain and
previously documented mouse-branch regions. It performs no live inspection,
private capture reads, WASM execution, guard/core edit, or formal-corpus
credit.
