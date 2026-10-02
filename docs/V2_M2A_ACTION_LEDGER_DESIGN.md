# Bounded Own Action Ledger design

## Purpose and scope

The ledger makes the operator's own ordinary UI action observable as a durable
chronology. It is intended to improve action-to-visible-birth attribution; it
does not establish an exact server application timestamp or certify the
callback or queue consumer. A complete, independently unique action-to-birth
match with a verified expected result can support Grade A for that bounded
dispatch behavior; route/fuel and complete-simulation/trajectory readiness
remain separate gates. The callback/queue consumer remains `UNKNOWN` until
independently proved. This is a design only: no live action was taken and no
core or capture tool was changed.

The least disruptive implementation would extend the existing JSONL event
stream in `tools/v2_controlled_transition_capture.py`. `durable_before`
flushes and `fsync`s each record, and `record_before_gesture` writes the intent
before it permits the mouse gesture (lines 572 and 825). The current flow
already records a before state, UI quantity evidence, distinct post-action
ticks, and a command result. Add the ledger identity and separate UI result
records to that stream; keep the existing capture and observer machinery.

## Durable event contract

Each gesture attempt gets a new random `intent_id`. Persist `ACTION_INTENT`
after final fresh-state, endpoint, selection, hit-test, and readiness checks,
immediately before the first mouse event. The minimum record is:

```json
{
  "kind": "ACTION_INTENT",
  "intent_id": "random-unique-id",
  "cohort_id": "operator-chosen-cohort-id",
  "intent_host_monotonic_ms": 123456789,
  "snapshot_sequence": 51,
  "world_sequence": 54012,
  "world_sequence_observed_at_host_monotonic_ms": 123456700,
  "document_id": "document-local-id",
  "match_epoch": "document-local lifecycle identity",
  "player_id": 31,
  "client_sha256": "pinned client hash",
  "source": {"tower_id": 123, "tower_type": 4},
  "destination": {"tower_id": 456, "tower_type": 2, "relation": "SELF"},
  "intended_action": "ALL_CURRENT_DEPLOYABLE",
  "intended_unit_vector": [[5, 12]],
  "unit_vector_basis": "observed typed source vector and matching direct UI rows",
  "selected_tower_none_confirmed": true,
  "prior_force_ids": ["visible-id-1"],
  "input_method": "official page mouse"
}
```

`world_sequence` is the displayed 16-bit world tick (`GameState.tick`); record
the extractor-local `GameState.sequence` separately because it counts samples,
not world advances. `world_sequence_observed_at_ms` marks the first host
observation of that displayed tick and repeated polls do not refresh it. All
times used for ordering are host monotonic values. Do not compare browser epoch
time to the host clock. `match_epoch` should preserve both `document_id` and
the current `match_id` lifecycle identity. The latter is generated locally
from document/player/lifecycle observations; it is not an official arena ID.

The unit vector is the declared intent basis, not a claim that the server
accepted exactly that amount. For `ALL_CURRENT_DEPLOYABLE`, store the typed
pre-gesture baseline and the selected-panel evidence separately, and label the
vector as observed UI evidence. If either is unknown or inconsistent, withhold
the gesture. Never select a later force by matching its quantity.

Append `UI_ACTION_RESULT` as a distinct, fsynced event after the mouse path
returns or errors. Include `intent_id`, monotonic down/up times when observed,
whether the browser mouse-up completed or recovery attempted it, and a bounded
error class. This reports UI event delivery only; it does not mean the game
accepted the command. If the process ends after the intent and before this
event, classify the gesture `UI_RESULT_UNKNOWN`; do not infer success or
failure and do not repair it from a later force.

Append every distinct visible tick as the current capture does. Before any
action, predeclare a candidate window covering the next one or two distinct
world ticks (modulo the 16-bit sequence), and retain every tick in that
window, including a complete tick where no birth appears. This accommodates
observed timing such as before tick 65155, absence at 65156, and birth at
65157 without choosing a window after seeing the outcome. Association is
eligible when one own `NEW_TRACK` appears on the intended source/destination
pair within that fixed window, at progress zero, absent from
`prior_force_ids`, with known owner, endpoints, identity, confidence, and typed
vector. Require complete visible coverage and a known force collection for
each tick in the window. First select by independent lineage and pair; then
compare the observed vector to the recorded intent vector. A quantity mismatch
marks the action/result inconsistent; it must not change which force is
selected. Multiple candidates, competing unresolved intents that prevent a
unique match, missing ticks, identity changes, or unknown force endpoints
make the association `AMBIGUOUS` or `UNRESOLVED`.

The ledger may name the birth tick as the first observed post-intent world
sequence, but the exact server application tick remains `UNKNOWN`. A UI
timestamp, local event timestamp, force `first_seen_ms`, or client sequence
cannot be backfilled into a server time. The ledger can support Grade A only
for the narrowly named dispatch/birth behavior when: the pre-action intent was
durably flushed before input; UI delivery status was recorded; the fixed tick
window is complete; exactly one new force is independently attributed without
using its quantity as the selector; and its declared expected properties
verify. A failed or ambiguous check earns no Grade A. This grade does not
transfer to route/fuel, terminal path, combat, or full trajectory accuracy,
which keep their own proof and simulator gates.

## Which readiness can change

The current `control_readiness_gaps` implementation has no callback, receiver,
or queue-consumer check (`src/kiomet_ai/v2/control.py:31`). Thus there is no
such code gate to remove. An experiment may leave the callback/consumer
question `UNKNOWN` and use an own-action ledger for bounded empirical lineage;
that does not qualify the callback source or relax canonical control readiness.

For the first ledger cohort, remove only “callback/queue source proof” as a
prerequisite to attempting an otherwise-supported, explicitly authorized
ordinary UI action. Distinct source/destination pairs can support separate
concurrent intents when the campaign records and validates them as separate
attribution strata; this first cohort remains sequential while that
multi-intent design is unproven. Keep the capture's existing readiness gate intact. In
particular, `validate_fresh_intent` checks it at line 137, the final execute
path checks it again at line 1021, and complete coverage plus known force
collection is required for `collect_new_force_births`. Do not change
`control_readiness_gaps` or its use in the simulator.

Retain these safety and attribution gates:

| Gate | Why it stays |
| --- | --- |
| Pinned official client, owned host/profile/writer lease, bounded deadline | Ensures the intended client and controlled input surface. |
| `IN_MATCH`, `NETWORK`, stable `document_id`/`match_epoch`/player identity | Prevents crossing menu, reconnect, new document, or a different match. |
| Recent first observation of the current world sequence (current control bound is 1 s) | A stale displayed tick cannot support a fresh action intent. |
| Positively complete player-visible coverage; known force collection and identity, owner, endpoints, vector, progress, and confidence for any potentially matching track | Needed to prove a force ID is new and the source/destination pair is unique. The current full readiness gate already rejects unknown fields on every visible force. |
| Current visible own source, supported type/vector, known adjacency and target relation/inventory | Defines a legal, ordinary, selected action without guessing hidden endpoints. |
| Explicit deselection and the pinned ordinary `DeployForce` UI branch | A selected-source drag may instead edit a supply line; the input meaning must be known. |
| Current camera projection, safe canvas coordinates, endpoint hit tests | Prevents clicking a different UI target. |
| Existing no-Ruler/special-weapon/supply-line restrictions, source delay and unit/capacity checks | These are supported-action limits, not callback-source claims. |
| For this initial single-intent cohort, do not issue a second unresolved intent on the same pair until its fixed two-tick window closes | Keeps each newborn attributable to at most one durable intent. This is a cohort design choice, not a permanent restriction on studying overlapping or same-tick actions. A future layered cohort may admit multiple intents on distinct pairs, then separately validate same-pair and same-tick cases. |

Some fields in `control_readiness_gaps` concern global simulation completeness,
such as every tower's production/effect/delay fields and every visible force's
full progress/vector. They may eventually be replaced for a ledger-only
association by a reviewed pair-scoped validator, but not in this design's
first cohort. Keep the full current gate until that validator is independently
shown to preserve complete force identity and selected-action safety. Even
then, this would qualify only visible birth association, never full-world
simulation or trajectory readiness.

## Bounded dispatch cohort

Treat 30 as a proposed hard maximum for one future cohort, not a quota. Count every fsynced `ACTION_INTENT`
against the cap, including gestures with UI failure, timeout, or unresolved
result; retries consume another slot and require a new intent. Pre-register
strata before dispatch. Use empty-neutral capture and own-tower reinforcement
as the primary classes, each capped at 20 attempts, with an overall cap of 30.
Within each, record the already-observed ordinary vector class (single ordinary
type or mixed ordinary types) and cap each vector class at 20 as well. Do not
silently rebalance after seeing outcomes. These are upper bounds, not minimum
quotas; stop early when there is no eligible fresh candidate.

Keep current execution limits distinct from proposed cohort caps: the parser
accepts `--max-commands` from 1 through 6 and `--seconds` up to 180, but this
tool currently records one command (`command_index` 1) per invocation at
lines 1148, 1305, and 1320; the argument is a ceiling, not a 30-action loop.
The code does not establish a per-match limit of six. A future cohort would
need an explicit campaign ledger spanning distinct one-action receipts, each
within the existing 180-second run/host bound. Keep this first cohort to one unresolved intent at a time; a future layered design may admit concurrent intents on distinct pairs after its independent uniqueness rules are specified. Use only normal UI, own source, adjacent own or
positively empty neutral target, and ordinary deployable units 0–5; exclude
Ruler and special weapons/units 6–9, enemy/ally targets, upgrades, relay
configuration, and any input channel besides the official page mouse. No
candidate means zero dispatches. No automatic gameplay, retry loop, or
unbounded host session is implied.

## Acceptance and stop conditions

The useful outcome is a durable before/action/after ledger and conservative
`ATTRIBUTED`, `UNRESOLVED`, or `AMBIGUOUS` labels. A single action with no
unique birth is not evidence of no dispatch; it is an unresolved observation.
Stop the cohort on lifecycle/document change, stale sequence, incomplete
coverage, unexpected UI selection, any non-mouse input, duplicate candidate,
or insufficient lease/deadline. Preserve every rejection and UI failure. The
ledger records observed effects without promoting callback topology, server
application timing, combat rules, or a simulator trajectory.

## Implementation acceptance — 2026-10-03

The prepared implementation returns CANDIDATE_MATCHED for a unique lineage/pair
whose vector matches the durable intent. It is temporal correlation only:
source-inventory depletion versus deterministic production has not yet been
implemented as an association gate. The durable BEFORE_INTENT already preserves
the full source snapshot, but that does not itself validate conservation.
causal_attribution remains NOT_YET_VALIDATED_SOURCE_CONSERVATION and formal credit
remains zero. Intent/result identity and caller/epoch player identity must agree.
This partial implementation has zero live experiments and does not demonstrate
OWN_ACTION_PROVENANCE PASS or the proposed 30-action stratified campaign. The
next ledger implementation gate is an exact source-conservation check with
unknown production/arrival inputs refused, followed by real bounded experiments.
