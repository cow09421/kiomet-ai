# Ordinary Tank/Soldier terminal-result mapping

Pinned WASM SHA-256: `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`. This review reads static disassembly only and adds zero formal events. It scopes the result calculation to ordinary Force-against-Tower combat with Tank/Soldier vectors, no Shield/single-use/Ruler units, and the actual terminal vectors produced by the pinned fight. It does not establish every preceding fighter-loop branch.

## Concrete result flow

At `0x1ac4c..0x1ac60`, combat setup stores kind sentinel 27 at scratch+392, the arriving Force units pointer at scratch+388 and destination units at scratch+396. The separate destination kind is at scratch+400 (`0x1ac73..0x1ac7a`). These fields must not be interchanged.

When the cleanup iterator reaches its terminal branch at `0x1afe2`, the code reads `Units::is_alive(scratch+388)` at `0x1afe3..0x1afec`, then `Units::is_alive(var13)` at `0x1afee..0x1aff0`. It pushes result zero and branches to label67 if the arriving units are alive (`0x1aff3..0x1aff7`); the branch carries that zero, not the defender-alive Boolean below it. Thus a surviving attacker yields result zero.

If the attacker is not alive, that zero is dropped (`0x1aff9`). The predicate at `0x1affc..0x1b009` is `(scratch+392 != 27) && score >= 0`; for this Force context it is false. The code combines it with defender alive and either branches to label68 when both are false (`0x1b00b..0x1b00d`) or returns the predicate's negation, one, through label67 (`0x1b00f..0x1b012`). Therefore a surviving defender yields result one.

When neither side is alive, label68 ends at `0x1b0e2`. The following select pushes 1, 2, and `score <= 0` (`0x1b0e4..0x1b0ed`); it yields one when the condition is true and two otherwise. The common label67 end stores this result in var4 at `0x1b0ee..0x1b0ef`.

| Terminal attacker alive | Terminal defender alive | Terminal score | var4 |
| --- | --- | --- | --- |
| true | either | any | 0 |
| false | true | any | 1 |
| false | false | <= 0 | 1 |
| false | false | > 0 | 2 |

`Units::is_alive` at `0x1048e5..0x104965` iterates nonzero units, skips Shield enum zero and single-use units (`0x10494f..0x104958`), and reports whether an eligible unit was found. In the T/S-only scope, the previously pinned non-single-use classification for enums 4 and 5 makes this exactly a nonzero Tank-or-Soldier predicate.

## Simulator comparison and remaining limits

`combat.py::_fight` chooses ATTACKER if its attacker vector is alive, otherwise DEFENDER if its defender vector is alive or `defender_is_tower and damage <= 0`, otherwise None. With the ordinary destination-Tower flag true and T/S vectors, this is the same conditional truth table as var4 values 0/1/2 above, assuming the terminal vectors and cumulative signed score agree. It does not replace that necessary assumption with an after-fit score.

Result one skips the owner setter at `0x1b14f..0x1b154`. For result zero with a nonzero arriving owner, the independently reviewed candidate predicate passes that owner to the setter. Result two enters the owner-clearing/neutral-metadata branch. The neutral/destruction downgrade remains unsupported in normal simulation; no result-two world is silently accepted. See `V2_M2A_ORDINARY_CAPTURE_AFTERMATH_REVIEW.md` for the separately traced setter and postlude.

This closes the local result-code interpretation for the stated Force/Tower terminal state. Complete fight-loop equivalence, actual handler binding, force route/fuel, world admission and genuine ordinary differential evidence remain required. No core fix or formal-corpus entry is proposed.
