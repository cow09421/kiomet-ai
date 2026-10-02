# M2A ordinary attacker-win aftermath: pinned dataflow review

## Question and result

This note traces the nonempty-defender ordinary combat result through the owner-update block and the later Tower addition call. It keeps the separate empty-defender transfer path out of the ordinary analysis.

The pinned combat setup stores arriving Force units (`var11`) at `scratch+388` and destination defender units (`var13`) at `scratch+396` (`0x1ac56..0x1ac64`). The common later addition path copies `var11` into a temporary vector and passes it as incoming units to `Units::add_units_to_tower`, with `var13` as the destination vector (`0x1b427..0x1b45b`). The broad vector order therefore matches the simulator shape: combat mutates the destination defender vector, then surviving Force units may be added to it. This trace does not prove the complete postlude, the resulting Tower capacity limits, the complete winner/merge result or production equivalence. No before-only counterexample to `step.py` is established; these parts remain **UNKNOWN**.

Pinned WASM SHA-256: `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`. Offsets are WASM byte offsets from the pinned disassembly. No WASM execution, live state read, or core edit was performed.

## Do not conflate the empty-defender path

At fight setup, `var11` is the arriving Force vector and `var13` is the destination defender vector (also recorded in `docs/V2_M2A_SHIELD_RETAINING_DEFENSE_REVIEW.md`). The early check at `0x1abaf..0x1abb5` tests whether `var13` is empty. Only that empty-defender transfer path contains `Tower::set_player_id_inner` at `0x1ac21` followed by `Units::reconcile` at `0x1ac38`; it exits at `0x1ac3b`. This is not the path for an ordinary fight against nonempty defenders.

## Ordinary result and setter arguments

The ordinary combat result/event control flow spans `0x1afee..0x1b223`. A result with `var4 == 1` branches out at `0x1b14f..0x1b154` and skips the later setter block. For other results, `var6` is loaded from `scratch+386` at `0x1b156..0x1b15c`; if the current Tower owner (`scratch+384`) is nonzero, it is loaded again from the same field at `0x1b1af..0x1b1b3`. Thus the candidate third setter argument is sourced from `scratch+386` on every path that reaches the predicate.

The source chain is now independently closed in `V2_M2A_ARRIVAL_FORCE_OWNER_PROVENANCE_REVIEW.md`. The stable aliases are `var23 = scratch+292` (`0x1a3ec`) and `var11 = scratch+302` (`0x1a40c`). The selected Force's `f+12` owner bytes are copied to scratch+368, then to `var23+8 == scratch+300` (`0x1a9ed..0x1aa0a`, `0x1ab30..0x1ab4e`). Its `f+14` units begin at scratch+302, the same var11 passed to combat. Consequently scratch+386's candidate is the arriving Force owner. The later postlude write at `0x1b3ac` is not used to infer that source. The previous unresolved-owner statement is superseded by this alias/copy evidence.

The nested predicate at `0x1b1ba..0x1b1c6` is equivalent to `var4 == 0 && (var6 & 0xffff) != 0`. Result one has already exited at `0x1b154`. Root independently followed both named block exits, including the instructions skipped by `br $label70`:

| remaining result / candidate | current owner | setter behavior |
| --- | --- | --- |
| result zero, candidate nonzero | either zero or nonzero | event then `br label70` at `0x1b20d`; skips both candidate zeroing and the old-owner check; setter receives original nonzero candidate |
| every other remaining combination | zero | candidate zeroed at `0x1b210`; `br_if label71` at `0x1b21a` skips setter and enters metadata path |
| every other remaining combination | nonzero | candidate zeroed; setter receives zero, clearing the owner |

The true predicate's branch crosses the old-owner check as well as the zero assignment. Therefore it can call the setter for a previously neutral destination. `var14` is `Tower+36` (`0x1a565..0x1a56a`) and `var27` is `Tower+24` (`0x1a959..0x1a964`).

The setter body (`0x13b009..0x13b04c`) has a separate nested branch. If the old owner is nonzero, it calls `func5420` on the line field, writes its empty sentinel, and branches to label0 at `0x13b025`, skipping the new-owner nonzero test. It then stores the third argument at `0x13b037`, including zero. If the old owner is zero, the new owner must be nonzero; old-zero/new-zero reaches a panic rather than a store. The caller's table above avoids that combination. A nonzero candidate may therefore capture a neutral or owned destination; zero may clear an owned destination. The candidate is the arriving Force owner by the independent pre-combat copy above.

After the call, the code reloads the 16-bit value at `var14` and branches to the end of the enclosing block if it is nonzero (`0x1b226..0x1b22b`). Only when that test is zero does it run the following metadata path (`0x1b22e..0x1b25a`): it normalizes Tower+46 through `tower::TowerType` and clears Tower+47. Therefore the Tower-type repair is conditional; it must not be described as part of every attacker capture. This block repairs a resulting neutral Tower; it is skipped after a nonzero arriving-owner transfer. Full winner/units/capacity and production equivalence still require their separate proofs.

## Gated survivor-addition postlude

The type-15 and Force-byte-below-11 checks (`0x1b3b3..0x1b3c7`) belong to a supply-line/relay subpath and are not universal prerequisites for the addition call. At `0x1b349..0x1b354`, an empty destination line sentinel branches to label76, skipping those checks. After label76, `0x1b3ca..0x1b3d4` branches to label79 when `var4 == 0` or the Force has no Ruler. That label ends immediately before the vector copy and addition. Thus a line-empty, Ruler-free arrival can reach the addition without a type-15 condition. Other line/relay branches remain outside this bounded trace. On the path that reaches it, `var11` is copied into a temporary unit vector (`0x1b427..0x1b43a`), and `Units::add_units_to_tower` is called (`0x1b43e..0x1b45b`) with:

- destination units at `var13`;
- incoming units copied from the arriving Force vector `var11`;
- Tower+46 as a byte;
- `Tower+36 != 0` as a Boolean;
- Tower+45 as a byte.

`Units::add_units_to_tower` (`0x10ea28..0x10eaa1`) walks categories 0 through 9 and passes nonzero, non-single-use counts to `Units::add_inner`. That helper (`0xb3cbb..0xb3e3d`) consults `Units::capacity` (`0x13d8d1..0x13d901`) using the unit enum, Tower type, and its fifth capacity-related argument; it also receives the Boolean above. This proves the runtime inputs, including the owner nonzero flag, but does not establish the effective T/S limits or equivalence to decoded capacity. Do not assume `dst.capacity` equals these computed limits without separately proving its decoder semantics.

## Comparison with the simulator and limits

For an attacker-winning arrival, `step.py` stores `fight.defender` into `dst.units`, replaces the force with `fight.attacker`, updates owner/production, and then follows its friendly merge path to combine the remaining Force vector. That broadly resembles the pinned defender-vector plus incoming-force-vector dataflow. The pinned setter path is conditional: result zero with a nonzero candidate passes that candidate for either a neutral or owned destination; other non-exited combinations pass zero only for an owned destination, while result one exits before it. The setter can write zero when clearing a previously owned destination. The metadata repair is also conditional on the owner remaining zero after the call. The later unit addition has separate line/relay/Ruler branches and receives Tower+46, the Tower+36 nonzero flag, and Tower+45. The candidate now identifies the arriving attacker owner. This review has not proven the complete result mapping or that production and effective capacities match. It therefore supplies no concrete before-only counterexample and proposes no code fix.

A minimal counterexample would require a legal, before-known ordinary fight whose result reaches the addition block, a proof tying its result/candidate-owner values to the arrival, plus the exact Tower+46/+36/+45 values and decoded `dst.capacity` meaning, followed by a demonstrated difference in resulting units/owner/production. None is established here. The conditional setter dataflow is now known, while complete winner/merge/production/capacity equivalence remains **UNKNOWN**; do not add synthetic captures to the formal corpus.

## Subsequent scoped checks

The effective T/S limits and incoming clipping are now independently checked in `V2_M2A_TS_CAPTURE_CAPACITY_REVIEW.md`, including Tank +5 and Soldier +10 owned allowances and preservation of existing overflow. `V2_M2A_CAPTURE_PRODUCTION_ORDER_REVIEW.md` establishes that the scheduled production pass precedes ordinary capture and survivor merge for the stated stable-kind, known-morale, no-Ruler scope. These supersede those narrow UNKNOWN entries above; the complete winner/result mapping and full-world ordinary admission remain unresolved. Neither scoped check supplies a genuine new differential event.
