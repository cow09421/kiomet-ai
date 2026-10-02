# Restricted Tank/Soldier fighter-loop final-vector boundary

## Finding

For the bounded fighter-entry case already used by the accepted reviews
(Shield zero, only Tank/Soldier counts, no Ruler/air/special units, known
morale), the pinned main combat loop preserves the same selected-unit
identity through availability selection, held-unit update, and damage
calculation. Combined with the accepted cleanup-order and held-casualty
reviews, this closes the local Tank/Soldier fighter-loop vector accounting
conditional on the same entry vectors and combat inputs. It does not certify
the upstream arrival/admission path, the combat context's input ownership, or
any broader combat category.

Pinned WASM SHA-256:
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`.
Offsets below are byte offsets in the pinned WAT/disassembly.

## Selection-to-consumption connection

In `World::tick_before_inputs`, the repeated fighter loop is
`0x1ad94..0x1af4d`. Its signed-score dispatch selects the attacker for a
negative score, the defender for a positive score, and uses both pending-aware
selectors at zero (`0x1adc2..0x1add1`). At zero, the branch selects the
attacker's candidate only when the defender's selector did not return the
empty marker; otherwise it feeds the no-candidate marker to the existing
break path. This is the same tie rule as Python `_fight`: attacker has
priority at zero, but its iteration ends if the defender has no remaining
candidate.

For a nonempty candidate, each participant branch calls `func2408` with that
side's unit vector and held byte; `func2408` calls `func1185` to select the
first pending-aware unit in the requested field. The attacker's zero-score
path reads the selected enum from scratch `+56` at `0x1adff` and stores it in
`var5` at `0x1ae02`; its negative-score path reads scratch `+40` at `0x1ae57`
and stores the enum in `var5` at `0x1ae5a`. The defender path reads the
selected enum from scratch `+64` at `0x1aefa` and stores it in `var4` at
`0x1aefd`. The nearby `0x1aeef..0x1aef3` instructions instead read the
defender result tag from scratch `+65` into `var8` and test it against the
empty marker `2`.

At zero score, the code calls both selectors, then `0x1ae23..0x1ae2f` chooses
sentinel `2` when the defender tag at scratch `+49` equals `2`; otherwise it
keeps the attacker's selected field/tag. Sentinel `2` reaches the
no-candidate branch at `0x1ae6b`, before consume or damage. Thus the attacker
is attempted at a tie only when the defender has a candidate, matching
`_fight`'s explicit `damage == 0 and next_unit(1, field) is None` gate.

The participant branch passes its selected enum unchanged as the new-unit
argument to `func1347` (`0x1aea4` for the attacker, `0x1af2a` for the
defender), then passes that same local to `func2022` (`0x1aebe` / `0x1af44`)
and adds its signed result to the existing score (`0x1af48..0x1af4d`). A
missing candidate branches out before either consume or damage. The loop then
repeats selection from the updated score and held marker; it does not advance
a separate precomputed fighter list.

`func2827`, called immediately before `func1347`, can replace the opposing
held-marker argument only for its special `(var3 == 9 && var4 == 10)` case.
The two values are the participants' held markers, not the newly selected
unit; the callsite passes the selected unit separately as `func1347`'s final
argument. In this restricted loop the held markers are Tank, Soldier, or
sentinel `10`, so the Ruler-specific fallback does not fire and the original
opposing marker is forwarded. The cross-side Ruler behavior remains outside
this proof.

The Python `_fight` loop has the same dependency order: select one
pending-aware unit for the current score and field; stop that side's field
loop on no candidate; call `consume(side, unit)`; apply that unit's signed
damage to the running score; repeat from the updated vectors/held cursor.
For the restricted T/S categories, the previously accepted
`func1347` review establishes that this consume step leaves the new selection
pending and resolves the previously held casualty exactly once. Thus the
selector does not repeatedly damage the same unit: subsequent selection
consults the matching held marker, just as Python's `unused()` excludes
`last[side]`.

## Final vector and remaining boundary

The accepted zero-score cleanup-order review covers the later two-participant
cleanup iterator; the accepted held-casualty review covers its vector updates;
the terminal-result review maps every resulting T/S alive/dead vector and
final score to the client result code. This note supplies the missing
main-loop selected-enum-to-consume connection rather than repeating those
proofs. Under their shared preconditions, the composition accounts for every
Tank/Soldier removal in the local fighter loop and terminal cleanup.

This is a conditional combat-loop equivalence statement, not a before-only
transition certificate. It relies on the combat caller providing the same
unit vectors, morale booleans, Tower flag/capacity inputs, and initial signed
score. Existing reviews leave the mapping of all separate Tower capacity
inputs and the ordinary attacker-winning arrival/postlude admission
conditions unresolved. Consequently it does not justify relaxing the normal
combat refusal or claim complete world-step equivalence. No counterexample
was found or fabricated; no live state, WASM execution, core edit, or formal
credit was used.
