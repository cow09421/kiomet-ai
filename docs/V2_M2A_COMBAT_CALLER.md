# Ordinary combat: bounded field-selector caller proof

STATUS: static pinned caller proof only; complete fight remains a candidate.

Pinned SHA: fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.

Luna identified that func2408's condition pointer still needed caller-level
mapping. Sol independently traced the complete local chain:

1. `0x1ad78..0x1ad88` stores u16 value 1 at scratch+428, therefore the two
   little-endian element bytes are `[1,0]`. An i64 store of 8589934592 at +420
   creates iterator index 0 at +420 and end 2 at +424.
2. `0x1ad8e..0x1ad94` passes scratch+420 to func3449. func3449 at
   `0x139438..0x139440` invokes func6761 with exhausted-result sentinel 2.
3. func4062 at `0x13eec8..0x13eef7` returns the old index and increments it
   while index differs from end. func6761 at `0x15687b..0x1568b6` reads
   iterator+8+old_index when present, otherwise returns sentinel 2.
   Consequently this caller emits fields 1, then 0, then terminates.
4. `0x1ad97..0x1ada6` excludes sentinel 2 and stores the emitted field byte
   at scratch+415. `0x1adb0..0x1adb4` creates its pointer. The calls to
   func2408 at `0x1adfa`, `0x1ae20`, `0x1ae52`, and `0x1aee9` use that
   field-byte pointer as the condition argument.
5. func2408 `0x114152..0x114162` invokes the selector with any_air=false.
   `0x11416e..0x114178` skips a second call if the result field is sentinel 2;
   `0x11417a..0x114180` also skips it if the condition byte is zero.
   Otherwise `0x114182..0x11418f` repeats the selector with any_air=true.

Independent pinned Unit::field scalar evaluations establish 1=Air and 0=Surface
for ordinary IDs; see V2_M2A_ORDINARY_RULES.json. This establishes Air before
Surface and the nonempty-first-result plus Air-phase gate for the second scan.
It does not establish every selector detail, deferred casualty branch, whole
combat, capture, ruler death, server authority, or live accuracy.

No live semantic call, offline whitelist expansion, actor write, or hidden state
read was used. This proof is a targeted static inspection of the pinned file.
