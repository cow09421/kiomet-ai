# Before-input direct path certificate

Pinned WASM SHA: fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.
Root inspected the aligned offline disassembly, not a running WASM function.
This is a sufficient certificate for one recorded UI drag, not a general
assumption that adjacency implies a terminal route.

## Pinned normal UI algorithm

The normal mouse handler is function488 (0x57c65). Its non-ranged path branch
seeds the frontier at 0x58083..0x580ff and pops at 0x58143 (func881).
The popped TowerId is compared with the destination before expansion at
0x58195..0x581ab; equality exits to path reconstruction at 0x5840a.
Only otherwise does it enumerate neighbors at 0x581c0. Tower lookup,
alliance exclusion and positive-visible filtering are at
0x58264..0x582a7. Edge cost is distance_squared shifted left 16, followed by
integer square root func2801, at 0x582a9..0x582b6; it is added to parent g
at 0x582c9..0x582cf.

The heuristic is func2027 (0x1094b8..0x10954c): distance_squared to the
destination shifted left 16 and integer square root at 0x1094bd..0x1094cd;
owner equality adds 512 at 0x109523..0x109529; non-self ownership or nonempty
neutral inventory adds 8192 at 0x1094fe..0x109514; empty neutral receives no
penalty. The handler invokes this heuristic at 0x582ed / 0x58351, stores
g+h at 0x5837f..0x58386 and pushes it at 0x58396 (func3054).

Frontier entry layout is f/g/index at +0/+4/+8. Push helper func1839
(0x1028b2..0x102958) moves an entry upward when its f is less than its
parent at 0x10290d..0x102912; equal f uses the g tiebreak at
0x1028fe..0x102908. Pop helper func881 chooses the lesser child f at
0xb1e2f..0xb1e4b and maintains the same ordering. Thus the unique lowest f
is popped first. Reconstruction follows stored parents and passes the resulting
path into the normal command branch. No heap contents or future path was read.

## Recorded before input

Only the BEFORE_INTENT record from
runtime/research/v2/controlled-transition-77636cad4e97.jsonl is used for these
scores: tick65155, player25, own source14090505 at (1328,1078), empty neutral
destination14090504 at (1324,1076). All five source neighbors are positively
visible with complete inventory and relation facts.

| Neighbor | Owner / inventory class | First expansion f |
|---|---|---:|
| 14090504 destination | empty neutral | 1144 |
| 14024969 | own | 2680 |
| 14090506 | own | 3270 |
| 14156040 | empty neutral | 2797 |
| 14156041 | own | 3275 |

Every other neighbor has a strictly greater f. Source expansion therefore
inserts the direct destination as the unique minimum; the next pop terminates
before expanding any other node. This establishes exactly [14090505,14090504]
from before-input facts, independent of later movement or arrival. Hidden nodes
beyond those neighbors cannot be expanded before termination.

The certificate requires these ownership/empty-inventory/visibility classes to
remain valid during the UI gesture, and the normal non-ranged branch to apply.
The recorded source is a Cliff with Soldier-only mobile inventory, with no
selection before the drag; it has no ranged-distance override. Neither a later
force segment nor simulator agreement can substitute for this qualification.
Command input timing remains independent: a unique progress-zero newborn and
its preceding absence identify the displayed application tick; the local mouse
timestamp is not server time.

The manual constructor independently proves initial fuel150 and progress0;
fuel is not spent during the first leg. At this two-node path's first arrival,
the old empty-neutral target changes owner and clears its supply line, then
merges the arriving ordinary force. This closes this route/fuel premise only.
Dynamic post-capture aura, external inputs and newly revealed actors retain
their separate eligibility checks. The original failed recorder receipt stays
unchanged, and the historical terminal hypothesis audit remains calibration.
