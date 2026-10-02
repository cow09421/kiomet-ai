# Factorized coverage and all-blocker bounds — accepted analysis

Root independently reproduced the full 13,059-edge analysis; Luna A independently
reviewed it. The whole-world known-active baseline remains 1,067/6,458 (16.522%)
comparable, 1,052/1,067 (98.594%) exact. Factor results have different units and
conditional assumptions; none replace that baseline or earn formal credit.

| Factor | Input readiness / opportunities | Semantic support / input ready | Accuracy / comparable projection |
|---|---:|---:|---:|
| tower_local | 416,675/416,675 (100.000%) | 413,055/416,675 (99.131%) | 412,694/412,994 (99.927%) |
| force_local | 16,755/29,450 (56.893%) | 15,624/16,755 (93.250%) | 31,143/31,224 (99.741%) |
| movement | 16,755/29,450 (56.893%) | 16,755/16,755 (100.000%) | 15,803/15,803 (100.000%) |
| production | 11,934/11,934 (100.000%) | 9,990/11,934 (83.710%) | 9,978/9,990 (99.880%) |
| arrival | 413/413 (100.000%) | 0/413 (0.000%) | 0/0 (UNKNOWN) |
| ownership | 416,665/416,675 (99.998%) | 238,908/416,665 (57.338%) | 238,908/238,908 (100.000%) |

Tower-local accuracy compares isolated no-force tower projections. Force-local
accuracy counts source/destination tower projections per supported isolated force
step, not full force signatures. Movement is pure current-leg progress, aligned
only to reliable unique continuing identities with unchanged endpoint/owner/units.
Production opportunities are due-period local arithmetic candidates, not proven
production events. Unknown interaction and external action remain unresolved.
Ownership input readiness uses local owner fields independently of distant force
endpoints; its semantic/accuracy numerator is the supported whole-world tower-pair
subset. Additional conditional ownership projection counts are retained separately.
Arrival's known-leg due opportunities exclude an UNKNOWN upstream candidate
population; 100% readiness on an identified conditional population is not global
arrival readiness. Actual arrival/capture/winner accuracy remains UNKNOWN.

## All-blockers: same 6,458 known-active edges

First-refusal attribution is preserved. Every gate also has one of BLOCKED, CLEAR
or NOT_EVALUABLE_DUE_TO_UPSTREAM_UNKNOWN; potential applicability is evidence,
not a fourth truth status. Confirmed blocking evidence cannot be overwritten by
unknown later evidence. Downstream absence of evaluation is never CLEAR.
Before and after-input endpoint gaps retain their own stage and force index.

| Gate | BLOCKED | CLEAR | NOT_EVALUABLE |
|---|---:|---:|---:|
| endpoint | 4802 | 1656 | 0 |
| upgrade_emp | 1469 | 4989 | 0 |
| supply_line | 574 | 5884 | 0 |
| special | 15 | 1649 | 4794 |
| movement | 0 | 1656 | 4802 |
| arrival | 0 | 1656 | 4802 |
| combat | 44 | 1650 | 4764 |
| unknown_path | 380 | 1597 | 4481 |
| relation | 0 | 1656 | 4802 |
| fuel | 380 | 1597 | 4481 |
| other | 69 | 1640 | 4749 |
| after_input_endpoint | 0 | 6447 | 11 |
| comparison | 15 | 1052 | 5391 |

Exact mismatch comparison residuals have UNKNOWN causes. Rejected/unexecuted
comparison residuals remain NOT_EVALUABLE, even when all statically visible guards
could be cleared. No external actor is inferred from a residual.

## Counterfactual bounds, not recovered endpoints

Bounds evaluate the 5,391 currently rejected/unexecuted known-active edges.
The 1,052 existing SUCCESS and 15 MISMATCH edges are already comparable and are
excluded from new-unlock counts. The whole-world denominator remains 6,458.
Endpoint exclusive certified count: 0.
All family exclusive counts are in JSON. These certify a blocker set, not lawful
repairability. No endpoint value is filled or inferred in this checkpoint.

| Hypothetically resolved gates | Guard-support bound, edges |
|---|---:|
| endpoint | 0–3192 |
| upgrade_emp | 0–343 |
| supply_line | 0–126 |
| special | 0–4 |
| movement | 0–0 |
| arrival | 0–0 |
| combat | 0–0 |
| unknown_path | 0–0 |
| relation | 0–0 |
| fuel | 0–0 |
| other | 0–8 |
| after_input_endpoint | 0–0 |
| comparison | 0–0 |
| endpoint + upgrade_emp | 0–4396 |
| endpoint + supply_line | 0–3606 |
| endpoint + combat | 0–3192 |
| endpoint + special | 0–3200 |
| endpoint + movement | 0–3192 |
| endpoint + arrival | 0–3192 |
| endpoint + unknown_path | 0–3192 |
| endpoint + relation | 0–3192 |
| endpoint + fuel | 0–3192 |
| endpoint + other | 0–3205 |
| endpoint + after_input_endpoint | 0–3192 |
| endpoint + comparison | 0–3192 |

| Greedy newly resolved gate | Conservative marginal bound | Cumulative bound |
|---|---:|---:|
| endpoint | 0–3192 | 0–3192 |
| upgrade_emp | 0–4396 | 0–4396 |
| supply_line | 0–4922 | 0–4922 |
| combat | 0–4922 | 0–4922 |
| special | 0–4935 | 0–4935 |
| movement | 0–4935 | 0–4935 |
| arrival | 0–4935 | 0–4935 |
| unknown_path | 0–4935 | 0–4935 |
| relation | 0–4935 | 0–4935 |
| fuel | 0–5311 | 0–5311 |
| other | 0–5380 | 0–5380 |
| after_input_endpoint | 0–5380 | 0–5380 |
| comparison | 0–5380 | 5380–5380 |

Marginal intervals use max(0,new lower−previous upper) to
max(0,new upper−previous lower). They can be wide and are not additive point
estimates. Upper assumes unknown residual gates clear; it is not a promise of
comparability or exactness. Actual newly comparable lower=0, actual causal upper=
UNKNOWN. In particular 4,766 first endpoint refusals are not 4,766 unlocked edges.
The comparison-gate intervention is hypothetical suppression of an unresolved
residual, not a simulator fix or an admissible causal explanation.

Shadow NOT_RUN: positive lawful B–E endpoint recovery is absent. No shadow coverage,
accuracy or next-blocker waterfall is manufactured. This static all-blocker surface
is separate from the unrun second-stage shadow experiment.

All inputs, rules, raw/source hashes, development-before-holdout final execution,
per-cohort factor counts, gates, local probes and full 13,059-row audit are in
V2_M2A_FACTORIZED_COVERAGE.json and its pinned fixture. Analysis defects discovered
in review were corrected and all six cohorts rerun; no outcome-driven parameter
fit was performed. Holdout results are descriptive, not newly unseen confirmatory
proof. No production source or transition formula changed.
