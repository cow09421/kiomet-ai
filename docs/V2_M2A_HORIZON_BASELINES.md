# Continuous horizon survival and simple baselines — M2A

Analysis-only. No production change, shadow endpoint, injected action, scenario or
state reset. Method endpoint-audit-method-v1; execution HEAD/dirty state, method/
tool/current-core/raw hashes and per-cohort counts are in the JSON. All six
recordings retain their development/holdout split. Baseline rules are fixed before
execution with no fit or holdout tuning. Old 13 replay cases are not this universe.

All 13,065 first-per-contiguous-scope/tick observations are inventoried. Legal
origins = 7,826 unchanged from_canonical successes; 4,858 NOT_READY and 381
ACTIVE_UPGRADE_OR_EMP failures remain the input-readiness exclusions. An origin
can be legal yet fail its very first step; it stays in the horizon denominator.
Horizon ends distinguish mismatch, simulator/observed-input refusal, and recording
end. No censor is converted to exact match or silently dropped. Every origin is
correlated with adjacent origins; counts are not independent trials.

Continuous prediction uses the original state once. Each tick executes default
step, then compares the exact observable full signature with the recorded endpoint.
Observed future states are used only for comparison; no predicted state is reset.
The first refusal or mismatch stops that trajectory. A gap is an unknown censor,
not a guessed intervening state. Max requested horizon is fixed at 20 ticks.

## All legal origins (same denominator 7,826 at every horizon)

| Horizon ticks | Exact survival | First mismatch by horizon | Unknown/unsupported censor | Recording-end censor |
|---:|---:|---:|---:|---:|
| 1 | 7198 (91.975%) | 15 | 611 | 2 |
| 2 | 6631 (84.730%) | 28 | 1164 | 3 |
| 4 | 5552 (70.943%) | 47 | 2222 | 5 |
| 8 | 3593 (45.911%) | 69 | 4155 | 9 |
| 20 | 1562 (19.959%) | 71 | 6172 | 21 |

Input readiness is 7,826/13,065 (59.900%); survival is conditional on legal input.
Whole-world one-tick comparable coverage remains 7,213/13,059, not 7,198/7,826.
The latter measures exact survival among legal origins and has a different unit.

## Legal origins whose next recorded edge is known active (denominator 1,274)

| Horizon ticks | Exact survival | First mismatch by horizon | Unknown/unsupported censor | Recording-end censor |
|---:|---:|---:|---:|---:|
| 1 | 1052 (82.575%) | 15 | 207 | 0 |
| 2 | 911 (71.507%) | 18 | 345 | 0 |
| 4 | 662 (51.962%) | 24 | 588 | 0 |
| 8 | 283 (22.214%) | 27 | 964 | 0 |
| 20 | 29 (2.276%) | 27 | 1218 | 0 |

The original known-active denominator is still 6,458. Only 1,274 of its before
states enter this legal-start curve; the remaining 5,184 cannot enter an unchanged
simulator forecast. The 207 active starts that refuse at tick 1 remain in this
curve, alongside 1,052 exact and 15 mismatch. This is not a replacement or
inflation of the 16.522% active comparable coverage metric.

By 20 ticks all-origin first stops include PRODUCTION_SUPPLY_LINE 5,656,
MOBILE_OVERFLOW_SUPPLY_LINE 36, UNKNOWN_POST_ARRIVAL_PATH 252, generic combat 26,
special production 20, observed NOT_READY 108 and upgrade/EMP 10. Other neutral
refusals, mismatches and recording ends remain listed in JSON. These are overlapping
starting windows stopped by events, not 5,656 distinct supply dispatch events.
Supply-line's long-horizon obstruction is much larger than its 131 active
one-tick first-refusal count suggests.

## Fixed simple baselines

Common populations are shared exactly with supported Simulator comparisons;
broader baseline-only populations are separately listed and cannot inflate
Simulator coverage. Reliable observation identities align before/past/after
fields; ambiguous identities and changed legs cannot enter velocity comparison.

| Metric and common population | Simple baseline | Simulator | Evidence of advantage |
|---|---|---|---|
| Ownership, 238,908 tower pairs | static owner 238,908 exact | 238,908 exact | None on this population |
| Force collection count, 7,213 edges | unchanged count 7,198 exact; absolute error 15 | same | None; no injected action |
| Movement progress, 1,317 force pairs | two-before-sample constant velocity 1,317 exact | 1,317 exact | None on continuing current legs |
| Nominal ETA estimator, same 1,317 pairs | subtract 250 ms, all exact | all exact | None; actual arrival error UNKNOWN |

Broader static-owner baseline: 416,527/416,611 pairs exact. Its 84 changed-owner
pairs across 83 transition patterns all fail, while the common Simulator
population has no changed-owner example. This makes its high overall accuracy
an inadequate combat/capture test. Broader constant velocity: 15,372/15,372
eligible continuing pairs exact. Broader ETA countdown: 15,803/15,803 estimator
pairs exact. No-action force-count baseline: 12,569/13,057 exact, absolute count
error 498. A birth and a disappearance can cancel in a count; count agreement
never proves event or entity correctness.

Constant velocity uses exactly the two distinct before observations, unchanged
owner/source/destination/composition and current UNIQUE_CONTINUATION. It never
uses the observed future delta to choose speed. ETA uses the current estimator
only; neither model gains actual arrival evidence from estimator agreement.
Winner, actual capture and actual arrival tick error remain UNKNOWN.

## Portable provenance and regression

V2_M2A_HORIZON_BASELINES.json references the hash-pinned
 tests/fixtures/v2/horizon-baseline-starts.jsonl.gz containing all 7,826 legal
origins and their fixed-horizon outcomes, first stops and starting activity.
Original raw recordings remain necessary for complete reproduction. Five focused
tests verify continuity without resets, different censor types, gap/input refusal,
strict before-only velocity prerequisites and duplicate identity refusal.
Final checkpoint analysis regression is recorded separately on final HEAD.
