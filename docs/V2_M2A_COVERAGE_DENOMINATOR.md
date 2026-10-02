# M2A coverage denominator and next P0 — 2026-10-03

STATUS: ACCEPTED current-core descriptive analysis / PARTIAL causal event truth. Next P0: **OTHER — CURRENT_LEG_PATH_INPUT_COVERAGE**. M2A / M2 IN_PROGRESS; M3 NOT_STARTED. No live collection, simulator rule change or new formal case in this round.

## Recording universe and independent reproduction

The unique union comprises six complete pinned observer recordings (three development, three holdout), about 2.35 GB. Every raw and corpus hash matches its historical data manifest. Root independently streamed and hashed their raw records, then independently reran the frozen Luna analyzer. All metric totals and 13,059 edge records agree; unordered diagnostic observer-ID lists were normalized only for reproduction comparison. Luna independently reviewed the schema, activity, priority and normalization. These preselected legacy sessions are not a random sample of whole-game behavior.

There are 14 historical core-manifest hash differences. This is accepted analysis of the explicitly hashed **current** core; it does not claim historical-core-identical output. Simulator code was unchanged in this round. Method preregistration commit: ac19b028a175b183a0c44293f3c38297af3e60a5. Analysis execution HEAD and dirty paths, current hashes, historical differences and all pins remain in the JSON.

Raw records 26,108 → first retained observations 13,065; repeated same-scope tick polls 13,043. Six initial observations have no incoming edge. ALL denominator **13,059**, including two observation gaps. Same-scope consecutive subdenominator **13,057**. Neither biased 13 birth windows nor raw/corpus duplicates define this universe. Wrap-aware adjacency and scope changes retain their gap rows.

Activity is decided from raw visible semantic values before simulator conversion: tower/force units, ownership, progress, type, delay and known effects/line facts. Tick, elapsed clock, host time, IDs, confidence and provenance alone are excluded. A reliable known semantic change proves activity despite other unknown fields. Unknown activity remains in the report rather than being removed by API readiness.

## Coverage and accuracy have different denominators

| Population | Observed denominator | Comparable API-supported | Exact match | Mismatch | Rejected | Coverage | Accuracy among comparable |
|---|---:|---:|---:|---:|---:|---:|---:|
| ALL | 13,059 | 7,213 | 7,198 | 15 | 5,846 | 55.234% | 99.792% |
| ACTIVE_KNOWN | 6,458 | 1,067 | 1,052 | 15 | 5,391 | 16.522% | 98.594% |
| ACTIVE_UNKNOWN | 61 | 0 | 0 | 0 | 61 | 0% on unknown-activity rows | UNKNOWN |
| INACTIVE | 6,540 | 6,146 | 6,146 | 0 | 394 | 93.976% | 100% |

ALL exact-match share is 55.119%; known-active exact-match share is 16.290%. The same-scope consecutive coverage is 7,213/13,057 (55.242%). Only one gap is known active, so its consecutive subdenominator is 6,457. The tight active coverage interval using actual execution is **1,067/6,519 to 1,067/6,458 = 16.368%–16.522%**. It varies only whether the 61 unknown-activity rejected rows are active. The analyzer also retains an explicitly hypothetical looser bound; no hypothetical execution is credited here.

Comparable means prediction and both endpoint states are supported and can be compared. There are 7,237 completed prediction steps, including 24 later endpoint refusals; those 24 do not inflate comparable coverage. The legacy `NOT_ATTEMPTED_GAP` execution-stage value is a catch-all for unsuccessful execution setup/steps, not a claim that all its 5,822 rows are observation gaps. Semantic refusals are REJECTED, not missing-record COVERAGE_GAP (the latter count is zero). All rows remain in ALL.

| Cohort | Split | ALL edges | Known active | Unknown activity | ALL comparable coverage | Known-active comparable coverage |
|---|---|---:|---:|---:|---|---|
| 03d032d57e5b | development | 2393 | 2290 | 44 | 217/2393 (9.068%) | 163/2290 (7.118%) |
| 7d56a775bc4c | holdout | 1076 | 1057 | 1 | 152/1076 (14.126%) | 135/1057 (12.772%) |
| 85391858b5d8 | holdout | 2398 | 1105 | 11 | 1443/2398 (60.175%) | 252/1105 (22.805%) |
| b1f7f9416e92 | holdout | 2396 | 102 | 1 | 2126/2396 (88.731%) | 59/102 (57.843%) |
| daf86d0544b7 | development | 2398 | 1814 | 3 | 954/2398 (39.783%) | 407/1814 (22.437%) |
| fe678ebb30ce | development | 2398 | 90 | 1 | 2321/2398 (96.789%) | 51/90 (56.667%) |

## Mutually exclusive first-blocker rule and overlapping diagnostics

Priority is the actual pinned execution order, with no retrospective choice of the most appealing error:

1. Scope/tick discontinuity rejects first; invalid raw/schema parse failure is a coverage gap.
2. Convert the before state. Readiness fails before stepping; within NOT_READY, clock/match continuity has priority over unknown current-leg endpoints, then other inputs. Preserve the raw NOT_READY code plus all before gaps. Semantic model refusals remain REJECTED.
3. Run the default step with no actions, supply/terminal/combat premises. Its first UnsupportedState guard in source order wins: global/pair prerequisites, tower iteration (neutral/upgrade/overflow/production guards), then force iteration (movement/arrival/combat/path guards). Thus tower order can mask a later force blocker. This is an API first-failure attribution, not a unique causal diagnosis.
4. Only after a supported step, convert the after state; retain after-input gaps separately. Compare exact observable full-state signature only when both endpoints support comparison; assign exact match or mismatch.

Each edge has exactly one primary result. Every normalized readiness reason and bucket counts once per edge per stage, even if many forces lack that field. Raw occurrences are separately retained and may be larger. Isolated tower/force probes are sampled, overlapping diagnostic counts only; they cannot turn a rejected whole-world edge into a pass. The compressed edge audit retains both complete gap arrays and probe rows.

### Actual known-active first blockers

| Primary blocker | Active edges | Share of 6,458 active | Share of 5,391 rejected active |
|---|---:|---:|---:|
| UNKNOWN_PATH / NOT_READY | 4766 | 73.800% | 88.407% |
| OTHER / ACTIVE_UPGRADE_OR_EMP | 385 | 5.962% | 7.142% |
| SUPPLY_LINE / PRODUCTION_SUPPLY_LINE | 128 | 1.982% | 2.374% |
| OBSERVATION_GAP / NOT_READY | 47 | 0.728% | 0.872% |
| UNKNOWN_PATH / UNKNOWN_POST_ARRIVAL_PATH | 42 | 0.650% | 0.779% |
| OTHER / NEUTRAL_UNIT_DECAY | 8 | 0.124% | 0.148% |
| COMBAT / UNVERIFIED_NORMAL_COMBAT | 6 | 0.093% | 0.111% |
| SPECIAL_PRODUCTION / SPECIAL_PRODUCTION | 4 | 0.062% | 0.074% |
| SUPPLY_LINE / MOBILE_OVERFLOW_SUPPLY_LINE | 3 | 0.046% | 0.056% |
| OBSERVATION_GAP / OBSERVATION_GAP | 1 | 0.015% | 0.019% |
| OTHER / NEUTRAL_DOWNGRADE | 1 | 0.015% | 0.019% |

The top three blocker families are current-leg endpoint input (4,766; 73.800% active / 88.407% rejected active), upgrade/EMP (385; 5.962% / 7.142%), and supply-line (128 production + 3 overflow = 131; 2.029% / 2.430%). Post-arrival continuation is separate: 42 known-active first refusals, not the 4,766 current-leg endpoint gaps. Clock/continuity 47 plus one actual observation gap remain separate. All 15 comparable mismatches have reliable new-track candidates, with UNKNOWN actor/cause; they are neither proved human actions nor proved rule bugs.

Supply-line first refusals total 524 across ALL, but only 131 are active. Ranking the ALL count would overstate supply-line priority. Endpoint blockers can mask later mechanics, so the chosen P0 must report newly exposed refusals after any accepted repair.

| Requested primary class | ALL | Known active | Share of 6,458 active |
|---|---:|---:|---:|
| SUPPORTED_AND_ACCEPTED | 7198 | 1052 | 16.290% |
| SUPPORTED_BUT_MISMATCH | 15 | 15 | 0.232% |
| REJECTED_SUPPLY_LINE_UNKNOWN | 524 | 131 | 2.028% |
| REJECTED_UNKNOWN_PATH | 4826 | 4808 | 74.450% |
| REJECTED_UNKNOWN_FUEL | 0 | 0 | 0.000% |
| REJECTED_COMBAT | 6 | 6 | 0.093% |
| REJECTED_SPECIAL_PRODUCTION | 4 | 4 | 0.062% |
| REJECTED_SPECIAL_UNIT | 0 | 0 | 0.000% |
| REJECTED_KING_ELIMINATION | 0 | 0 | 0.000% |
| REJECTED_OBSERVATION_GAP | 92 | 48 | 0.743% |
| REJECTED_UNKNOWN_RELATION | 0 | 0 | 0.000% |
| REJECTED_OTHER | 394 | 394 | 6.101% |
| EXTERNAL_ACTION_UNACCOUNTED | 0 | 0 | 0.000% |
| UNKNOWN | 0 | 0 | 0.000% |

EXTERNAL_ACTION_UNACCOUNTED is zero as an independently authenticated primary cause. Its 15 new-birth candidates are an overlapping diagnostic on SUPPORTED_BUT_MISMATCH. Zero first refusals for fuel/special unit/king/relation do not prove those mechanics are absent or supported; an earlier blocker may mask them.

## Gameplay layers and event-truth limits

These rows are **overlapping observed pattern incidences**, not independent causal events. Production due is a clock opportunity, not actual production. Unit increases may involve production or arrival; disappearance and ownership changes do not establish arrival, battle or capture. Their accepted/rejected/mismatch counts still retain every corresponding candidate incidence.

| Observable layer | Candidate edges | Comparable | Rejected | Mismatch | Pattern coverage | Full-state accuracy among comparable |
|---|---:|---:|---:|---:|---:|---:|
| production_due_potential | 2474 | 899 | 1575 | 2 | 36.338% | 99.778% |
| production_or_arrival_candidate | 659 | 118 | 541 | 2 | 17.906% | 98.305% |
| force_appearance_candidate | 646 | 15 | 631 | 15 | 2.322% | 0.000% |
| movement_observed | 6118 | 983 | 5135 | 4 | 16.067% | 99.593% |
| arrival_or_disappearance_candidate | 604 | 0 | 604 | 0 | 0.000% | UNKNOWN (0 comparable) |
| capture_or_owner_candidate | 83 | 0 | 83 | 0 | 0.000% | UNKNOWN (0 comparable) |

| Causal gameplay class | This-round truthful event denominator / coverage |
|---|---|
| Production only | UNKNOWN in full recordings; due-phase potential is separately reported, and conditional replay scores three deterministic production ticks |
| Movement only | Conditional replay certifies 53 scored movement-only ticks; full-universe movement patterns mix with other effects |
| Launch / external action | 646 track-appearance pattern edges; independently authenticated external-action denominator UNKNOWN |
| Ordinary arrival | 604 disappearance/arrival patterns; actual causal arrival count UNKNOWN |
| Friendly reinforcement | UNKNOWN, not an assertion of zero occurrences |
| Ground combat | UNKNOWN; six first generic-combat refusals are not six labeled ground battles |
| Air combat | UNKNOWN, not an assertion of zero occurrences |
| Capture / ownership change | 83 ownership-change patterns; certified capture count UNKNOWN |
| Supply-line related | 524 ALL / 131 active primary refusals; true supply dispatch event count UNKNOWN |
| Special production | Four first refusals, all known active; observed causal event denominator UNKNOWN |
| Other | 394 ALL / 394 active other semantic first refusals; actual event denominator UNKNOWN |
| Rejected / unsupported | 5,846 ALL / 5,391 active, retained rather than silently filtered |

True event coverage is therefore PARTIAL/UNKNOWN. A single overall event percentage would merge ambiguous causal labels and overlap; it is not reported as an accuracy result. This does not prevent a measured tick/active denominator or primary-blocker decision. Historical formal fixtures stay unchanged and are not counted as new evidence here.

## Decision metrics

Comparable visible ownership pairs: 238,908/238,908 agree. Tower inventory vectors: 238,893/238,908 exact, aggregate tower-inventory L1 error 44. Fifteen unaccounted newborn-force mismatches remain separately visible; tower-only L1 is not total troop or battle residual error. There is no certified capture/winner outcome in these comparisons.

Current-leg motion ETA estimator versus observer ETA estimate agrees on 1,359/1,359 pairs. This is estimator agreement, **not actual arrival ETA accuracy**. Actual arrival tick error, capture result, winner and authenticated server action legality remain UNKNOWN. The temporal replay separately verifies visible adjacency for 13 inferred shapes, with no server acceptance claim. High endpoint ownership accuracy is mostly stable ownership and cannot stand in for combat validation.

## Next P0 and prerequisites

Choose OTHER / CURRENT_LEG_PATH_INPUT_COVERAGE from the actual active ranking. The next bounded task is an offline audit of source/destination unknown reasons, observer field completeness and whether a reliable current visible endpoint was discarded despite existing-data evidence. Scope excludes inferred terminal routes, hidden-state extraction, new live collection and callback/queue/canvas research. If the endpoint truly is unobservable, preserve Unknown and report the ceiling; do not fabricate a value or relax the API gate. Any later bounded repair must freeze eligibility and rerun this same denominator, disclosing coverage gains, mismatches and newly exposed supply/combat blockers.

Own Action Ledger stays preregistration-only. See V2_M2A_ACTION_LEDGER_PREREGISTRATION.md: next-round pilot ≤5 then freeze window; 40 formal trials (15 clean / 15 adversarial / 10 variants), false_unique = 0 and clean ≥14/15, exact source conservation and complete unique visible force inventory mandatory. Duplicate/same-tick intent assignments and automatic-line interference cannot become falsely unique. UI failure alone does not prove rejected/no-effect. No trial is run in this phase.

## Portable audit and final validation

V2_M2A_COVERAGE_DENOMINATOR.json contains cohort summaries, raw/current hashes, aggregate diagnostics, root acceptance and a hash reference to tests/fixtures/v2/coverage-denominator-edges.jsonl.gz. The gzip contains all 13,059 complete edge rows, without duplicating the 2.35 GB raw recordings. Existing runtime recordings remain required for full reproduction.

Final full v2 regression must run after the final accepted-files commit. Its execution HEAD must equal final HEAD and source hashes must remain stable. Receipt path: runtime/research/v2/replay-coverage-final-head-regression.json. This path is an execution receipt, not a predeclared PASS. Older 371-test receipt is STALE for this task. Do not commit documentation after the final run, which would change HEAD.
