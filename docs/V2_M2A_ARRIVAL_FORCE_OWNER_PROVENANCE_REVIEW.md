# Ordinary-arrival candidate owner provenance review

## Finding

The pre-combat candidate at `scratch+300` is the arriving Force owner's
halfword. The proof combines the canonical Force record layout with the later
aliases: `var23` is assigned `scratch+292` and `var11` is assigned
`scratch+302` (`0x1a3e6..0x1a40c`). The selected Force record's owner at
`scratch+300` is therefore exactly `var23+8`, and its unit vector starts at
`scratch+302`, which is `var11`. That same `var11` is stored as the arriving units pointer at
`scratch+388` (`0x1ac56..0x1ac5c`). The later `scratch+300` load copied to
`scratch+386` is thus the arriving Force owner, not an unrelated iterator value.

Pinned WASM SHA-256:
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`.
This is a static disassembly review only; no WASM execution, live-state access,
or core edit was performed.

## Canonical Force layout and selected result

The normal visible-force decoder treats a Force vector element as a 24-byte
record. It obtains `f = ptr + i*24`, reads its owner with `u16(f + 12)`, and
reads the seven unit bytes from `f + 14` (`src/kiomet_ai/v2/observe/client_fae13.js:219-237`).
The tracker labels the owner source `visible Force.owner+12`
(`src/kiomet_ai/v2/observe/forces.py:97-98`).

In the pinned tick function, the force-iteration path forms an element pointer
from the force vector's data pointer and `24 * index`, then passes it to
`Force::raw_tick` (`0x1a9a0..0x1a9b0`). The subsequent loads at
`0x1a9ed..0x1aa0a` copy element bytes `+4..+11`, `+12..+19`, and `+20..+23`
into `scratch+360`, `scratch+368`, and `scratch+376`. Thus Force owner bytes
at element `+12..+13` travel in `scratch+368..369`.

The earlier `Tower::deploy_force` result is consumed through `func2536`:
`0x1a7af` calls `Tower::deploy_force`, initializes the result iterator, then
`0x1a7c0..0x1a7cc` calls `func2536` with output `scratch+288` and source
`scratch+216`. `func2536` calls `func4062` to select a 32-byte item. On its
selected-item branch (`0x11739d..0x1173da`), it copies four 8-byte chunks from
the selected item starting at source offset `+8` into output offsets `0, 8,
16, 24`. The caller copies output bytes `scratch+288..315` into `var18+0..27`
(`0x1a7e3..0x1a80c`) before passing that frame to `func2350`. In particular,
the output halfword at `scratch+300` (output offset 12) is preserved at
`var18+12`; the halfword at `scratch+316` is read separately as `var4` and
stored at `scratch+320`. The final two bytes of the 32-byte output are not
copied by these instructions. This selected-result frame is distinct from the
later ordinary-arrival Force-vector copy that proves the `scratch+300` owner
identity below.

For the subsequently processed Force, the selected element's owner bytes in
`scratch+368..369` are copied by the aggregate stores at `0x1ab30..0x1ab4e`
through `var23`. Since `var23 = scratch+292`, the second eight-byte store lands
at `scratch+300..307`. The owner is at `var23+8` / `scratch+300`; the units
begin at `var23+10` / `scratch+302`, which is the exact pointer assigned to
`var11`. This byte adjacency and the matching copied Force record establish
the owner-to-units relationship without relying on the postlude write.

## Alias lifetime and combat handoff

The aliases are assigned at `0x1a3e6..0x1a40c`: `var23 = scratch+292` and
`var11 = scratch+302`. A scan of the enclosing `World::tick_before_inputs`
body from its entry (`0x19b86`) through the combat setup (`0x1ab72`) finds no
later `local.set var23` or `local.set var11`, so these aliases remain in force
for the copy and combat call. The aggregate stores at `0x1ab30..0x1ab4e` copy
the selected Force fields into `var23`; the owner arrives at `scratch+300`, and
the units pointer remains `var11`.

At `0x1ab72`, the combat setup reads `scratch+300` into `var5` and stores it at
`scratch+386` (`0x1ab76..0x1ab78`). The alternate nonempty-defender path does
the same at `0x1aba9..0x1abbb`. Combat later reloads that value as `var6` at
`0x1b158` and `0x1b1af`. `scratch+388` receives `var11` as the attacker/arriving
unit vector at `0x1ac56..0x1ac5c`, tying the owner halfword to that same Force.
The post-combat write to `scratch+300` at `0x1b3ac` is not used as provenance;
the pre-combat copy and stable aliases already prove the source.

## Limit

This proves the candidate owner is the owner on the processed arriving Force
record. It does not by itself prove which ordinary combat result branch won,
that the pinned owner setter runs for every capture, or that the postfight
capacity/production behavior matches `step.py`. Retain those separate limits and
the corrected setter control-flow findings in
`V2_M2A_ORDINARY_CAPTURE_AFTERMATH_REVIEW.md`.
