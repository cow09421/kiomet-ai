# M2A ordinary arrival checkpoint

M2A IN_PROGRESS; M2 IN_PROGRESS; M3 NOT_STARTED. OLD M1 FAIL and M1B PASS remain unchanged. This is a PARTIAL semantic milestone, not M2 PASS. Main remains the v1 archive. Final committed HEAD, dirty status, counts and source hashes are bound by `runtime/research/v2/arrival-final-head-regression.json`, run after the last documentation commit.

Phase A: `d887edcf00292a77b2720674f114f4a9b74aecb5` analysis only.
Phase B: `83c004c` blocked paired pilot evidence only.
Phase C production: `8f8b61da4cf8df06e901cd08a292a4908b683019`.
Phase C bounded passive neutral evidence: `b110c53` (no production change).
No endpoint pipeline fix. No shadow completion. No M3, planner, sandbox, relay implementation or combat campaign.

## Endpoint decision

Edge-before Force census: ENEMY 29,450 / known 16,755 / unknown 12,695 / endpoint-local ready 16,755; SELF, ALLY, NEUTRAL, UNKNOWN_OWNER each zero. Known rate 56.893%, unknown 43.107%. Ready/blocked and current-leg-known/unknown match these counts, not whole-world readiness. Full retained population: 29,488 Force incidences / 13,065 snapshots, including six terminal observations; duplicate raw polls remain separately documented.

| Missing-endpoint derivation | Development | Holdout |
| --- | ---: | ---: |
| Eligible | 9,473 | 3,234 |
| Derived unique / true unique / false unique | 0 / 0 / 0 | 0 / 0 / 0 |
| Candidate set | 9,473 | 2,632 |
| Ambiguous | 0 | 0 |
| Unavailable | 0 | 602 |
| Unscorable | 9,473 | 3,234 |
| Unique rate | 0% | 0% |
| Unique accuracy / false-unique rate | UNKNOWN | UNKNOWN |

WEAK: no retained Force position or direction, no unique derivation. Zero-progress missing-endpoint rows (205 development / 66 holdout) do not prove stationary/parked actors. No readiness bug is established from motion UNKNOWN. The 267 reliable lineage tracks are long-lived. Future outcome and ETA inversion were not used to infer new endpoints.

PATH/FUEL: DISTINCT_BUT_CORRELATED, separate guards / same 380 blocked edges and 403 force witnesses each. Supply facts PARTIAL: current own-tower presence only, no enemy relay topology. Upgrade/EMP: 1,469 blocked edges with UNKNOWN cause; positively identified Upgrade 0 / EMP 0, not evidence that either true count is zero.

Paired pilot: 0 valid / 0 actual dispatch attempts; one execute preparation failed before input; two bounded official sessions. Own positive control unavailable. Same-session Enemy sampling: 66 paired snapshots, 178 Enemy Force incidences, 66 equal canonical serialization round-trips, no ambiguous same-sample owner/vector/progress maps. L0 UNKNOWN. L1 already lacks source; L2/L3 preserve it; L4 refuses it; L5 rejects. First upstream loss UNKNOWN. Outcome G / unresolved F; **UNKNOWN_BUT_RESEARCH_CLOSED**. Reopen only for a concrete production regression or false-unique counterexample, never another endpoint evidence study.

## Arrival production and limits

`ordinary_arrival_boundary` produces an immutable ordinary current-leg event after the shared one-tick movement threshold. It reports the next branch (`REINFORCEMENT_REQUIRED`, `CAPTURE_REQUIRED`, `COMBAT_REQUIRED`) and downstream censors; it never returns a replacement world state. The strict full-world step uses the same movement helper and retains its route/fuel/combat/merge checks and updates. Unknown route does not erase a supported arrival boundary and does not authorize a full settlement prediction.

Known relay, delay, special/King destination, unresolved visible simultaneous inbound and dynamic morale are excluded. Unknown inbound/line/terminal/fuel is explicitly censored. The independent review's public-helper unknown-delay gap was fixed by rejecting non-integer delay; a targeted test covers direct construction with None. Prior threshold reached also rejects duplicate new-event creation. Ordinary combat only enters COMBAT_REQUIRED; no combat result implementation or credit.

No SupplyLineEvent interface is needed to express this current-leg boundary: existing own-only presence plus explicit downstream supply censor is sufficient here. A relay event interface may be needed for future settlement/horizon work, but no route or automatic relay is added.

## Three reporting layers

### 1. Factor semantics

413 known due-arrival opportunities / 413 local input-ready. **295 / 413 (71.429%)** ordinary current-leg boundaries supported conditionally; all 295 downstream censored. Excluded 118 = 87 multiple-inbound + 18 active delay + 13 special destination. Censors overlap: unknown path 295, unknown fuel 295, unknown inbound 246, combat required 31, unknown reinforcement line 219. These are incidences and premises, not 295 certified events. Broad event accuracy UNKNOWN; historical full-settlement semantic support remains 0/413.

Movement 15,803/15,803 is ENGINEERING / REGRESSION BASELINE, also matched by constant velocity, not new milestone progress. Conditional production support 9,990/11,934, accuracy 9,978/9,990. Historical factor reports and Gates are not overwritten. New factor report and complete edge audit are archived separately.

Baseline-discriminating observed subset: 907 consecutive edges where owner or typed inventory changes (862 inventory / 83 owner, overlapping). Existing strict world simulator supported 131/907 (14.443%), correct 116/131 (88.55%), mismatch 15. Static owner+inventory baseline correct 0 by subset definition; not a prospective independent benchmark or causal event count. Current default horizon rerun reproduces the accepted strict behavior.

### 2. Event evidence

**New Grade A / formal game-semantic credit: 0. New accepted Grade B ordinary current-leg boundary evidence: 8**, across four contexts: four same-owner reinforcement boundaries (ENEMY relative to observer), four own empty-neutral boundaries. Own-action friendly trial evidence remains 0; no troop command was issued in the passive scene. Full reinforcement/capture credit 0. Historical accepted neutral capture remains regression-only and retains its previous credit.

The four before→arrival→following triples are 22670→22671→22672, 32781→32782→32783, 25874→25875→25876, 25926→25927→25928. Predicted arrival observation tick matches 4/4; target inventory delta matches incoming vector 4/4 with no due target production alternative; target owner matches through next tick 4/4. Force absence is corroborated by route/owner/vector and target change, not tracker ID alone. Next-tick inventory is observed in all four; following shield production in one context is separately consistent with the pinned phase rule. No permanent force consumption, action attribution, remaining fuel, future route or full merge outcome is asserted. Current acceleration is conditional on a unique retained pinned ETA estimate, not a new independent boost read.

Bounded official Party UI passive collection saved 175 canonical snapshots, ticks 11–91, with zero troop dispatch. Four fresh neutral boundary triples: 34→35→36 (16908553), 43→44→45 (16908552 and 16974088), 52→53→54 (17039625). All use visible source 16974089 and ordinary Shield15/Soldier4 vector; each has a single visible inbound to its distinct target. Progress 52/70/70/88 +2 reaches thresholds 54/72/72/90. Here acceleration is independently recorded OBSERVED false from the existing normal renderer field; ETA agreement is corroboration only. Empty owner0 becomes owner1 and the exact incoming vector, corroborated next tick: 4/4. Initially present forces have UNKNOWN launch provenance; normal Friends/Party/Play actions are not troop commands. Post-capture aura refresh/route/fuel remain outside complete-world credit.

Combined arrival observation tick and target-vector corroboration: **8/8**; owner/next-tick corroboration 8/8. These are eight distinct target boundaries but only **seven conservative world-transition groups**, because two new targets change in the same tick. All new neutral cases share match/player/source/composition, so they are not independent randomized trials or four action records. Together with the four old independent transitions across three other contexts, this meets the five-case / two-context goal conservatively. Four same-owner and four neutral boundaries also satisfy the preferred category counts at Grade B boundary scope; own manually dispatched friendly evidence remains absent.

Six offline candidates were retained. Two hit the threshold but change a different target unit type; due target production explains their delta and they are excluded. Two old party neutral boundaries lack the following tick and are not promoted. Four NEW live candidates are saved separately and qualify; no historical observation was repaired or promoted. The first passive scene setup failed on a Play button blocked by its dialog; resume was refused for insufficient lease margin before any UI action. One final finite host used the normal dialog Play successfully and recorded 20 seconds. No force gesture, readiness relaxation or input-entry observer. No further collection after the eight boundaries qualified.

### 3. Continuous horizons / competing risks

All 7,826 legal origins, no resets; overlapping origins are not independent trials. The 1/2 horizons and development/holdout/active populations remain in the JSON.

| Ticks | Exact | Mismatch | Input unknown | Supply | Arrival | Combat | Upgrade | Other | Recording end |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 5,552 | 47 | 69 | 1,946 | 132 | 18 | 8 | 49 | 5 |
| 8 | 3,593 | 69 | 94 | 3,738 | 210 | 26 | 10 | 77 | 9 |
| 16 | 1,728 | 71 | 104 | 5,540 | 246 | 26 | 10 | 84 | 17 |
| 20 | 1,562 | 71 | 108 | 5,692 | 252 | 26 | 10 | 84 | 21 |

Strict whole-world exact is a regression metric. A factor boundary does not turn a censored horizon into a complete exact forecast. Supply remains the dominant long-horizon censor (5,656 production + 36 overflow windows at 20); generic delay does not support choosing Upgrade over EMP.

## Decision and validation

ARRIVAL SEMANTIC STATUS: PARTIAL. OVERENGINEERING_TRIPWIRE: **CLEAR on eight accepted Grade B boundaries / seven conservative transition groups**, not on formal Grade A credit or synthetic tests. Five-case target met; complete-world settlement remains unknown. No historical Gate or formal counts are raised.

NEXT P0: **ordinary arrival settlement under before-certified terminal/line-free/fuel premises**, to turn the now corroborated current-leg reach into qualified reinforcement/capture outcomes. Prioritize a qualified own-friendly merge and neutral settlement with recorded before premises. Unknown relay is a settlement boundary, not a new endpoint archaeology task. Supply's large horizon burden is a candidate for the minimal visible-fact event interface if directly needed; full relay and generic upgrade implementation are not selected from unknown causes. Combat implementation remains undecided.

Targeted tests: 95 PASS across arrival API, real-event/live fixtures, exact archived actor provenance, factor analysis, horizon/risk mapping and simulator. Final complete `tests -k v2` runs on the final committed HEAD; source-manifest stability, failures/skips/errors/deselections and preserved old untracked notes are recorded in the final receipt. Push only v2-rebuild; verify main unchanged. No documentation commit after final regression receipt.
