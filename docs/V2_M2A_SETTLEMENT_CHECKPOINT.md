# M2A unfiltered settlement checkpoint - 2026-10-03

Naive empty-neutral Capture is falsified as an exact owner-plus-inventory forecast. PROVISIONAL_CAPTURE=NO; PROVISIONAL_REINFORCEMENT=NO. No production source changed. Arrival expansion stops under the user's explicit section 46 falsification exception. This is a rejected candidate, not a formal M2 Gate FAIL: OLD M1 FAIL / M1B PASS / M2A IN_PROGRESS / M2 IN_PROGRESS / M3 NOT_STARTED.

## Unfiltered population and frozen rules

All 413 known due opportunities remain: 295 supported boundaries plus 118 exclusions (87 multiple inbound, 18 active delay, 13 special destination). Naive scored branches: 264 = 45 Capture + 219 Reinforcement. Scores: 29 MATCH / 235 MISMATCH / 149 UNSCORABLE, including the 118 exclusions and 31 combat candidates. Before-only raw branch candidates include 51 Capture and 317 Reinforcement; 45 other candidates include 31 supported combat and 14 boundary exclusions.

The initial rules were committed in 978100e, before unfiltered results. Each branch received one development-only premise revision, committed in ac98a7a before holdout scoring. No holdout rule tuning. Combat retained Force morale was pinned in 31f399c before outcomes. Development used three recordings; holdout used three different recordings. Previously seen live evidence is separate and cannot supply a fresh holdout.

| Rule / split | Match | Mismatch | Unscorable | Scored accuracy | Scored groups | Contexts |
|---|---:|---:|---:|---:|---:|---:|
| Capture development | 3 | 21 | 0 | 12.500% | 24 | 3 |
| Capture holdout | 10 | 11 | 6 | 47.619% | 21 | 3 |
| Capture total | 13 | 32 | 6 | 28.889% | 45 | 6 |
| Reinforcement development | 13 | 167 | 82 | 7.222% | 175 | 2 |
| Reinforcement holdout | 3 | 36 | 16 | 7.692% | 39 | 2 |
| Reinforcement total | 16 | 203 | 98 | 7.306% | 214 | 4 |

Groups are conservatively `(cohort, arrival_tick)`, not individual tower counts. They remain retrospective groups, not randomized independent trials.

## Current deposit versus downstream uncertainty

All 45 scored captures have the incoming owner; 32 have zero arrival inventory instead of the incoming vector. First difference is inventory_after in all 32. This rejects the combined naive forecast. It does not establish that capture ownership is wrong or reveal the physical cause of missing inventory.

Development counterexample 03d032d57e5b:187:0: ticks 20959 -> 20960 -> 20961; owner 10 / Soldier 5, source 13828326 -> empty neutral target 13893863. At arrival, owner is 10 and inventory is zero; a unique compatible Soldier-5 force is visible on 13893863 -> 13893864 with progress 0, then 2. It is compatible with immediate forwarding or opponent relaunch. No Action Ledger binds physical identity, so neither cause is certified. Exact deposit cannot be promoted from this record.

The development revision requires before-known terminal=true for exact deposit. This is a conservative candidate premise, not a discovered universal rule, and no terminal is known true in the 413. Final target-local and strict-world eligibility are both 0 cases / 0 groups / 0 contexts for both branches. Future route/fuel alone do not erase a proven local owner fact; current inventory stays unresolved where an immediate transfer could change it.

Even omitting terminal, the before-only local Capture proxy has 19 cases / 19 groups / 6 contexts: development 2/8 exact, holdout 5/11 exact, total 7/19. It independently fails the 90% gate. Reinforcement proxy eligibility remains zero because current local relay/supply effect is not resolved. No empty eligible population is called a success, and no observed disappearance is used to admit a case.

## Residual contexts and attribution

These counts overlap and describe before-context, not proved mechanic causes.

| Context | 32 Capture mismatches | 203 Reinforcement mismatches |
|---|---:|---:|
| Production due | 0 | 2 |
| Confirmed local relay | 0 | 0 |
| Relay/supply unknown | 32 | 203 |
| Possible unknown-destination inbound | 15 | 171 |
| Nonzero current source/target delay | 0 | 0 |
| Special destination | 0 | 0 |
| Normal capacity | 8 | 50 |
| Pinned ordinary ground overflow | 8 | 35 |
| Capacity/clipping ambiguity | 16 | 118 |

The two production-interaction rows (03d032d57e5b:1924:0 and :1984:0) retain their raw naive forecast disagreements but are CENSOR_PRODUCTION_INTERACTION for settlement attribution. Their production contribution is not reliably isolated; they are not proof of wrong settlement arithmetic. Capacity uses existing Tank +5 / Soldier +10 allowances, not speculative clipping or air/shield overflow.

## Observed Force status

`t` is before, `t+1` arrival, `t+2` following. These are signature-level observations, not physical genealogy or permanent consumption. TRANSFORMED means a compatible new-leg signature; disappearance is limited to the observed census.

| Population / offset | Disappeared | Continues | Transformed | Ambiguous | Unknown |
|---|---:|---:|---:|---:|---:|
| All 413 / t+1 | 57 | 12 | 215 | 128 | 1 |
| All 413 / t+2 | 56 | 14 | 213 | 128 | 2 |
| Scored Capture 45 / t+1 | 9 | 0 | 23 | 13 | 0 |
| Scored Capture 45 / t+2 | 9 | 0 | 22 | 13 | 1 |
| Prior accepted Grade B 8 / t+1 | 6 | 0 | 1 | 1 | 0 |
| Prior accepted Grade B 8 / t+2 | 6 | 0 | 1 | 1 | 0 |

The separate previously seen live scene was scanned fully: 175 raw states / 81 distinct scope-tick states / 80 consecutive edges, all four due captures exact, in three groups / one context. All four are DISAPPEARED at both offsets. They are outside the 413 and holdout; new formal credit zero. Previously accepted eight boundaries remain eight, across seven groups / four contexts; no full settlement credit.

## Production gates and controls

Capture NO: holdout 47.619%, high-impact inventory residuals, zero final eligible groups. Reinforcement NO: Capture prerequisite failed, holdout 7.692%, zero final eligible groups. Do not fit an owner-only alternative on the already inspected holdout. No Force deletion or state-changing settlement was added.

Negative controls: 10 actual development before-ineligible cases plus 18 isolated public-input mutations; 28/28 correctly refused, zero false accepts. The synthetic terminal=true positive is a guard test only, with zero empirical credit. Outcome owner/inventory/Force mutations cannot make before-only eligibility pass.

## Passive combat and readiness

Combat: 31 primary cases (22 development, 9 holdout). Ground 2 + air 2 historical rows are all aliases: 35 submitted rows / 31 unique, zero new independent legacy cases. Frozen raw projections are 26 MATCH / 5 MISMATCH; owner agrees 31/31. Qualified subset is 4 MATCH / 0 MISMATCH / 27 unqualified; dev 2/2 and holdout 2/2. Unknown pair hostility in 9 and incomplete inbound in 24 overlap. Five inventory residuals all have new-leg-compatible forces; attribution remains ambiguous. Following agreement 24/31 is corroboration, not a t+2 forecast. COMBAT_REPLAY_PARTIAL: fewer than 10 clean cases requires controlled evidence. No formula tuning or production Combat.

Readiness actual reason is force:0:source; R1 is only a candidate because the rejected sample lacks a bound intended action pair and route proof. Primary classification R3_ROUTE_OR_ACTION_LEGALITY_UNPROVEN. Different-match qualified previews cannot repair that absence. Action-local fix NOT_APPLICABLE. Valid trials 0, dispatch attempts 0, new Grade A 0. Endpoint UNKNOWN_BUT_RESEARCH_CLOSED; callback/queue/canvas/WASM/input archaeology remains stopped.

## Baseline and competing risks

The retrospective owner/inventory-change subset is still 907 observed, 131 supported / 116 correct before and after. New Capture 0, Reinforcement 0, production Combat 0. Static baseline 0 is a consequence of retrospective subset selection, not a prospective benchmark victory.

All 17 core hashes match the accepted horizon report; the following unchanged results reuse that report rather than claim a fresh run. Each row retains all 7,826 legal origins.

| Horizon | Exact | Mismatch | Input | Supply | Arrival | Combat | Upgrade | Other | End |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 5552 | 47 | 69 | 1946 | 132 | 18 | 8 | 49 | 5 |
| 8 | 3593 | 69 | 94 | 3738 | 210 | 26 | 10 | 77 | 9 |
| 16 | 1728 | 71 | 104 | 5540 | 246 | 26 | 10 | 84 | 17 |
| 20 | 1562 | 71 | 108 | 5692 | 252 | 26 | 10 | 84 | 21 |

Supply 5692 = 5656 production + 36 overflow origin windows, not distinct events. No new SETTLED cases; existing 295 boundaries remain boundary-only, including 31 COMBAT_REQUIRED and 219 unresolved reinforcement lines.

## Capabilities, credits, stop and next P0

New production game-semantic capability: none. New evidence capability: complete unfiltered frozen replay, explicit inventory counterexamples, Force-status audit, and passive combat qualification. Provisional Capture credit 0 / Reinforcement 0; new Grade A 0 / Grade B 0 / certified 0. Historical formal counts unchanged 1053/1053; historical single capture fixture and combat/reinforcement formal counts are unchanged.

OVERENGINEERING_TRIPWIRE TRIGGERED: no state-changing provisional branch. The user's explicit falsification exception applies; Arrival expansion stops rather than starting a third evidence-methodology round. This does not declare M2 FAIL.

Ranked next P0: (1) controlled ordinary combat evidence, because only four cases qualify and the formula remains frozen; (2) bounded Supply-local current-inventory diagnosis, addressing the 5692 horizon burden without a generic supply engine; (3) bounded strategy review under current inventory/continuation uncertainty. No next task is started by this checkpoint, and no planner/MPC/belief implementation is authorized here.

## Final verification binding

Root integration acceptance: 45 targeted tests passed (7 replay + 14 combat + 24 controls). All final documents, including this checkpoint, must be committed before the complete `tests -k v2` run. The actual final HEAD, branch, dirty status, source hashes, PASS/FAIL/SKIP/ERROR/DESELECTED counts are bound by `runtime/research/v2/settlement-final-head-regression.json`. Do not reuse the prior 456-pass receipt for this HEAD, and do not commit documentation after the final receipt. Push only v2-rebuild and verify main remains 234cfad918381adfd2a48a183ca17d35b64970e0.

Only two pre-existing untracked notes are deliberately preserved: V2_M2A_REGISTERED_MOUSE_QUEUE_CONSUMER_REVIEW.md and V2_M2A_TS_CAPACITY_CONTEXT_REVIEW.md. Machine-readable results, source hashes and per-case production-attribution censors are in V2_M2A_SETTLEMENT_CHECKPOINT.json; detailed source reports are V2_M2A_UNFILTERED_SETTLEMENT.json, V2_M2A_COMBAT_PASSIVE_REPLAY.json, V2_M2A_SETTLEMENT_NEGATIVE_CONTROLS.json and V2_M2A_ACTION_LOCAL_READINESS_REVIEW.json.
