# M2A — deterministic simulator engineering checkpoint

CURRENT MILESTONE: M2A / M2B measurement only
STATUS: IN_PROGRESS. M2 has not passed; M3 has not started.
OLD M1 FAIL documents remain unchanged. M1B PASS checkpoint: 2212346.

## Current evidence and corrected accounting

Formal production/current-leg movement: 1052/1052 genuine one-tick complete
visible-state transitions: development 611/611 (38 production-only, 573 movement),
untouched holdout 441/441 (35 production-only, 406 movement). Overlapping event
categories are not additional cases. All formal outputs contain actual visible
changes. Before-input event selection never depends on after-state agreement.

RETRACTION: historical 440, 868/338/1206 and subsequent 1340 counts included
at-capacity stationary production attempts. The six-cohort 1340 denominator
contained 347 unchanged cases; these are removed. New cohorts supply the current
1052 genuine events. Historical Git and runtime before-event-tightening receipts
remain available; their counts and static-weighted performance are superseded.
The root agent identified and corrected this accounting error.

Ground candidate: 1054/1054 overall, only TWO actual ground combat events, 2/2
complete-world matches. The daf development event and independent 7d event are
retained as full-state fixtures. Default ground/ordinary combat flags remain OFF.

Ordinary Air/Surface candidate: 593/594 complete-world matches. Actual ground
2/2; actual air 1/2. The second air case includes an unrecorded simultaneous enemy
launch. Local defender agreement is not full-state agreement. Its mismatch stays
in the denominator; an after-inferred launch reproduces the world only as
calibration, with no accuracy credit. Do not use the aggregate ratio as combat PASS.

Trajectories: two nonoverlapping five-second multievent rollouts match all
intermediate visible states. Thirteen intermediate failures are retained; these
include unrecorded force births. No intermediate canonical resets. The required
100 trajectories and ruler death/elimination direction gates are unfinished.

## Core rules and root integration

Pinned official-client WASM SHA:
fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.
Old public AGPL source informs hypotheses; it is not current-server authority.

SUPPORTED: u16 relative world phase/wrap, ordinary production within guarded
capacity scope, current-segment movement, owned immobile Shield overflow decay,
stationary special inventory preservation, explicit local ordinary launch after
world advancement at progress zero. Limited terminal capture/reference scenarios
require known path/fuel and non-overflowing ordinary units.

Friendly terminal reinforcement additionally requires an independently supplied
Scenario.no_supply_line_towers premise. Terminal=True and positive fuel alone do
not establish that premise. Public Force::try_move_on can clone a destination
supply line and relay a Many force; unknown destinations now refuse with
UNKNOWN_REINFORCEMENT_SUPPLY_LINE. No canonical unknown is converted to false.
The existing observation contract is unchanged, and no live friendly-arrival
accuracy claim is made. Invalid scenario tower references are rejected.

Root independently corrected morale bonus to min(3, headcount//2): pinned select
at 0xffb43..0xffb51 selects 3 when half>=3. The old max interpretation and previous
iterator-Tower scratch alias were rejected. Force+21 is scratch309 within the
aggregate i32. Shield and Single-use weapons do not inflate morale headcount.

Ordinary combat is an explicit isolated hypothesis: Air before Surface, held-unit
accounting, capacity-sensitive aircraft fields, Shield air grouping, and retained
damage across phases. Root ran 84 independent pinned damage/field scalar cases;
scalar agreement does not establish complete fight correctness.

UNSUPPORTED: king death/global elimination, dynamic morale/aura, active EMP or
upgrade, special production/movement/combat, mobile overflow/supply-line effects,
unknown arrival acceleration, unknown future path/fuel, neutral decay/downgrade,
opposed force combat, unknown pair relationship, and unrecorded external actions.
Unsupported transitions do not earn accuracy credit.

## Parallel review decisions

SUBAGENTS USED: arrival_review, combat_review, corpus_candidates; dispatched with
gpt-6-luna/high. Root alone controls integration, Git and milestone decisions.

ACCEPTED: arrival Single/Many and overflow risks; bounded corpus references and
uncertainty classifications; combat scalar/dataflow evidence after independent
root verification. Corpus canonical convertibility is not scenario eligibility.

REJECTED: max morale, previous-Tower flag alias, stale ground calculations,
aggregate combat PASS claims, and unsupported after-inferred actions as accuracy.
REWORKED: event denominator, miner EOF/target provenance, complete combat fixtures,
source manifests and whole-state failure reporting. Original candidate report
SHA and old M1 failure documents are preserved.

SOL DIRECT WORK: pinned rule/dataflow tracing; compact-state/world ordering;
combat candidate integration; event selection correction; new independent ground
fixture; terminal reinforcement supply-line guard; complete-state differential,
trajectory and performance verification; bounded Python optimization.

## Verification and performance

68 v2 regression tests pass. Performance inputs are all 611 development genuine
event states, each restored from original canonical records and independently
checked against its complete expected visible state before timing. Every measured
step includes all visible towers and forces; conversion/IO is outside timing.

Quiet baseline before phase caching: 47058 / 46973 / 46749 transitions/sec,
median 46973. Bounded pure phase-offset caching and direct immutable input-tower
iteration produced 50149 / 50940 / 51357, median 50940 before the latest relay guard.
Caches contain only immutable rule inputs, never actor facts. Duplicate tower IDs
are rejected. Latest source-specific rerun is V2_M2A_PERFORMANCE.json:
43963 / 46759 / 52314, median 46759 complete transitions/sec, below target. All trials,
including below-target trials, remain reported. This limited-scope measurement
is not full M2/M2B PASS. No native rewrite or GPU work has started.

Passive cohorts 7d and b1 were captured without troop gestures. b1 contains a
single 600-second NETWORK match; 7d naturally entered RESULT and remains a partial
cohort. Optional --stop-on-result ends finite sampling without automatic rejoin;
the natural-result branch still needs its own live verification.

## Authorization and next work

No troop command has been sent. A concrete two-match bounded ordinary-UI input
capture plan is recorded in V2_M2A_CONTROLLED_CAPTURE_PLAN.md. The earlier M1 user
instruction explicitly prohibited automatic dispatch/attack; execution awaits an
explicit answer about these M2 tests. Core fixes and offline verification continue.
This is a pending authorization for that action, not a reason to stop all work.

Genuine engineering blocker: none. Remaining gates are construction work.
NEXT PARALLEL PLAN: Luna independently red-teams arrival relay and evidence
accounting; Sol verifies pinned ownership/supply-line boundaries and integrates
only independently checked results. Preserve all failures and uncertainty. No M3.
