# Ordinary UI launch boundary

Current production WASM: `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`.
Static instructions below are from the pinned local `disassembly.json`; no
semantic WASM function was called and no future force path was read.

Root independently inspected `KiometGame::peek_mouse` (func488,
0x57c65..0x58715). At 0x57deb..0x57df1, var10 points to game+688,
the ordinary selected-tower Option. A mismatched source clears this Option at
0x57e1e..0x57e2f. At 0x57edf..0x57f09, var13 starts at zero; the
generates-mobile and range predicates are evaluated only if the selected Option
is present. At 0x58622..0x58633, zero var13 calls
`Command::deploy_force_from_path`. The alternative builds a `Path` and checks
the tower's supply-line Option at 0x5863e..0x5866b. Both commands use the normal
`ClientContext::send_to_game` at 0x58700.

Consequently an ordinary quantity-panel inspection must be followed by normal
UI deselection and a fresh readback proving selected_tower is None before a force
drag. Selection and deselection must each remain recorded; source quantity alone
does not certify a command. The controller must additionally recheck both endpoint
visibility, ownership, camera projection, hit tests and deployment quantity.

This static branch proof establishes which UI command branch is selected. It
does not prove the complete A* route, server application tick or force acceptance.
Those remain independent eligibility requirements. A before-recorded intent and
unique new force with progress zero can establish a candidate application tick;
the simulator may not choose a tick by matching the after-state. Any gap,
ambiguous lineage or changed quantity excludes formal accuracy credit.

Live evidence must retain every observed distinct full tick, including ticks
after arrival. A trajectory starts at its one persisted before-state and advances
without resetting from subsequent canonical states. Missing intermediate ticks,
unknown terminal path or fuel, and unsupported owner/morale transitions stay
explicitly excluded; local endpoint agreement is insufficient for full-world PASS.
