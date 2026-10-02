# Party cohort simulator-admission review

## Result

The saved 21-sample pinned NETWORK cohort restores cleanly through the strict
canonical deserializer and has no control-readiness gaps. That does not make
its observed arrival/capture pair simulator-admissible: the tick-33 before
state reaches the explicit `UNKNOWN_POST_ARRIVAL_PATH` guard. Two forces are
geometrically due to reach distinct, neutral, empty destinations in the next
world tick, but their terminal route and fuel are unknown. The next displayed
sample corroborates two arrivals: both candidate Force records disappear,
both destinations change owner to the corresponding Force owner and change
units, and the visible Force count falls from four to two. This after-state
corroboration does not fill the before-state route, terminal, or fuel gaps.

Formal credit is **zero**. No state was selected by its after-state result and
no synthetic or repeated-tick cases were counted as events.

The ignored machine-readable record is
`runtime/research/v2/party-supported-simulator-admission-20261002.json`.
It contains aggregate pair diagnostics without Party route or code data. Its
source receipt is
`runtime/research/v2/party-readiness-route-supported-2-20261002.json`
(SHA-256 `eff3d5a73c72ce49fc28e8907cce6c976b56c0e543719193c746cfc8e6da4f2f`).

## Before-state admission and timeline

All 21 samples restore and pass the local readiness gate. Their declared
coverage is `PLAYER_VISIBLE_COMPLETE`; that does not establish complete
worldwide actor visibility or absence of foreign actions. The step accepts 20
single-state predictions. For the tick-33 state it stops at
`UNKNOWN_POST_ARRIVAL_PATH`, before it can evaluate the candidate arrival. The
first failure must remain the admission result even though the next sample
shows related changes.

After dropping same-tick polls, the cohort has 15 exact one-tick pairs, three
same-tick repeats, and two multi-tick gaps. Fourteen pair-before states pass
`step`; 13 of those predictions match the complete next displayed signature.
The sole mismatch is tick 22→23: one Tower's observed morale, capacity, and
production changed while owner, kind, and units did not. This is evidence that
the `fixed_morale=True` scenario premise is not established across every
transition; it is not a before-only rule or an arrival counterexample. A
separate tick 24→25 pair has a due-production category and one Tower unit-vector
change, and the full prediction matches. Neither pair is a capture case.

## Tick 33→34 candidate arrival

Before the transition, two of four visible Forces satisfy the pure movement
test for arrival in the next tick: each has progress 52, speed 2, and required
progress 54. Both Force relations are `SELF`; each destination is observed
neutral and empty, so these candidates do not enter the enemy-combat branch.
The other two Forces are not due to arrive on that step. The simulator rejects
the first due arrival at `UNKNOWN_POST_ARRIVAL_PATH`; `terminal`, route, and fuel
are all retained as **UNKNOWN**.

The displayed next state provides corroboration only: each candidate's Force
record is absent, each corresponding destination is owned by that Force owner
and has changed units, and total visible Forces fall from four to two. Two
Tower owner changes and two unit-vector changes occur. This is consistent with
two genuine empty-neutral arrivals, but it does not justify assuming a
terminal route, enough fuel, or no other world action for prediction. No
arrival is admitted or credited.

## Remaining boundaries

The canonical facts include Tower capacity, production, and current morale, but
this cohort does not establish aura stability after capture or full-world
action completeness. The observed aura change confirms the need to retain the
dynamic-aura boundary for longer trajectories. No owner, relation, route, fuel,
or foreign-action unknown was inferred from the after state. No core edit,
formal-corpus addition, or count padding was made.

Root independently reproduced all aggregate and pair outcome labels using `tools/v2_party_admission_audit.py` from the committed canonical gzip alone. This tool computes its own output rather than copying earlier review fields and retains an exact first signature-difference path. The earlier ignored audit, Luna reproduction/script/plan, and Root result are now stored as hash-checked portable gzip fixtures. See `V2_M2A_PARTY_ADMISSION_AUDIT_VALIDATION.json`; all results remain diagnostic and add zero formal credit.
