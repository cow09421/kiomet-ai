# External action injection replay — root acceptance

PRIMARY VERDICT: **MIXED**. Given the Grade-B manual-launch hypothesis, missing exogenous inputs explain all 13 audited first divergences. This does not establish the actual actor, command, queue or server application time. Extended world evolution remains unassessed beyond unsupported/input-unknown boundaries; no full trajectory passes.

Root independently executed the frozen tool and matched the candidate case results. The helper hash stayed unchanged during the independent run. All four original raw snapshot hashes match both the historical audit and trajectory report. Current simulator hashes are recorded separately from historical implementation drift.

| Measure | Result |
|---|---:|
| Total cases | 13 |
| Grade A / B / C at original boundary | 0 / 13 / 0 |
| Replayable with inferred action | 13 |
| Audited first-divergence tick repaired | 13 |
| Subsequent matching tick comparisons | 56 |
| All compared matching tick states | 112 |
| Complete primary trajectories | 0 |
| First predicted-state divergence after injection | 0 within compared prefixes |
| Partial / refused before endpoint | 13 |
| New formal accuracy/provenance credit | 0 |

These 112 comparisons overlap the original selected windows and are diagnostic Grade B, not new independent formal cases. Zero predicted-state divergence is not zero unresolved rollouts. All error-growth leaf counts and numeric differences in the compared prefixes are zero; error after each refusal is UNKNOWN.

## Per-case horizons and stopping boundaries

| Case | Cohort | Audited action tick | Compared / requested ticks | Ticks after first action | First unexecuted tick | Stop |
|---|---|---:|---:|---:|---:|---|
| 1 | 03d032d57e5b | 21325 | 10 / 26 | 4 | 21330 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 2 | daf86d0544b7 | 23900 | 10 / 23 | 7 | 23908 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 3 | daf86d0544b7 | 23994 | 10 / 21 | 9 | 24004 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 4 | daf86d0544b7 | 24061 | 10 / 28 | 2 | 24064 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 5 | daf86d0544b7 | 24168 | 10 / 27 | 3 | 24172 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 6 | daf86d0544b7 | 24359 | 10 / 26 | 4 | 24364 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 7 | daf86d0544b7 | 24457 | 10 / 28 | 2 | 24460 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 8 | daf86d0544b7 | 24524 | 6 / 23 | 3 | 24528 | SIMULATOR_UNSUPPORTED:SPECIAL_PRODUCTION |
| 9 | daf86d0544b7 | 24590 | 3 / 22 | 1 | 24592 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 10 | 85391858b5d8 | 31223 | 10 / 27 | 3 | 31227 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 11 | 85391858b5d8 | 31649 | 10 / 21 | 9 | 31659 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 12 | 85391858b5d8 | 31698 | 10 / 22 | 8 | 31707 | SIMULATOR_UNSUPPORTED:PRODUCTION_SUPPLY_LINE |
| 13 | 7d56a775bc4c | 46507 | 3 / 22 | 1 | 46509 | GRADE_C_EXTERNAL_ACTION_UNRESOLVED |

Primary windows require 20 ticks after the original divergence/action, totaling 21–28 ticks (5.25–7 seconds under the retained 250ms convention). Actual compared prefixes last only 3–10 ticks; the post-action portions last 1–9 ticks. The separate original first-20-tick indicator is also false for every case. Observed time cues are not server timestamps.

## Interpretation and next gate

H1 is supported locally for the 13 original birth boundaries: using the independently inferred vector in the existing launch API removes every corresponding state difference, including subsequent compared states. H2 (incorrect transition formulas despite actions) is not demonstrated: no compared predicted state differs. However, 11 rollouts stop on PRODUCTION_SUPPLY_LINE, one on SPECIAL_PRODUCTION, and one on a later Grade-C boundary whose no-action source step cannot be certified. These are unresolved coverage/input gates, not successful or incorrect predictions.

Per the user instruction, investigate the first shared production/input boundary before a 30-dispatch live campaign. Minimal own-action ledger tooling can be prepared without live input; its provenance, experiment count, and PASS remain unvalidated. Callback/queue/listener/canvas research is STOPPED absent a concrete ledger counterexample.

Launch terminal is explicitly None. Fuel 150 is only the existing manual-launch constructor assumption, not recovered hidden state or a terminal certificate. No observed state or force is patched into the running prediction. Later Grade-C events and unknown arrivals remain refused.

No M3, simulator core modification, new formal combat event or expanded performance claim follows. Historical air candidate 1/2 remains retained. See V2_M2A_CAUSAL_COVERAGE.json for stratified accuracy and explicitly unknown historical eligibility denominators.

## Artifacts

- Machine-readable accepted replay: `docs/V2_M2A_EXTERNAL_ACTION_REPLAY.json`.
- Independent conservation: `docs/V2_M2A_EXTERNAL_ACTION_CONSERVATION_REVIEW.json`.
- Frozen helper: `tools/v2_external_action_replay.py`.
- Independent source review: `docs/V2_M2A_EXTERNAL_ACTION_REPLAY_REVIEW.md`.
- Source-qualified regression runner: `tools/v2_regression_receipt.py`.

Two earlier offline tool attempts were interrupted/refused before a usable case receipt (memory retention, stale source-manifest variable). A separate Windows path-normalization refusal is preserved. None is counted as a simulator case failure or success.

## Shared rule-gap review

The first production refusal is due mobile production with less than two units of headroom, no Ruler, and supply_line_present=None. Eight of eleven occurrences are missing own-side fields in legacy recordings; three are enemy-side unknowns. This is an UNKNOWN required input, not a proved incorrect formula. The new own-only observation field can help fresh experiments; it cannot retrospectively fill these recordings or expose enemy routes.

The special-production refusal is due unit7 at visible enemy tower17367309. The later Grade-C case reaches UNKNOWN_POST_ARRIVAL_PATH; a new Tank track appears while the source vector stays unchanged, so a simple source-depletion launch is not established. Neither disappearance nor a new observer track proves an arrival or another command. Exact tower vectors, phases, capacities and boundary ticks are retained in the JSON.

An automatic review refused the subagent attempt to add two separate rule-gap reports, citing the delegated file scope. These findings are instead integrated into the explicitly requested replay artifacts; no additional rule-gap files were created.
