# Current-leg endpoint lineage — accepted analysis, 2026-10-03

Verdict: NEEDS_MORE_EVIDENCE. No production fix or shadow completion is admitted.
Analysis baseline HEAD: ebffa6407069b83ea87211416a4e37d769d0bd95.
Root independently reproduced the full audit; Luna C independently reviewed it.
Source and raw recording hashes, stage records, cohort owner/class/age tables and
every blocked entity are retained in the JSON report and pinned gzip fixture.

The fixed 4,766 endpoint-first-blocked edges reproduce as 4,755 BEFORE and 11 AFTER
input refusals. The AFTER cases audit the next observed state's force index and
identity, not the previous state's index. There are 12,356 entity-edge incidences
and 267 unique reliable observer tracks, not 12,356 distinct physical forces.
All incidences are ENEMY; SELF, ALLY, NEUTRAL and UNKNOWN_OWNER each have zero.
Consequently this sample cannot answer whether a known own UI launch loses its
endpoint. SELF ownership alone would not prove a known user intent.

| Cohort | Split | Known-active edges | Blocked edges | Entity incidences | Newborn | Persistent | Long lived | Unknown age |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 03d032d57e5b | development | 2290 | 1859 | 5851 | 115 | 116 | 5616 | 4 |
| 7d56a775bc4c | holdout | 1057 | 719 | 1948 | 40 | 40 | 1867 | 1 |
| 85391858b5d8 | holdout | 1105 | 793 | 1242 | 28 | 26 | 1188 | 0 |
| b1f7f9416e92 | holdout | 102 | 36 | 36 | 1 | 1 | 34 | 0 |
| daf86d0544b7 | development | 1814 | 1323 | 3243 | 91 | 86 | 3066 | 0 |
| fe678ebb30ce | development | 90 | 36 | 36 | 1 | 1 | 34 | 0 |

All cohort incidences are ENEMY and A_RAW_ABSENT at the earliest retained canonical
observer-output boundary. Aggregate ages: NEWBORN 276, PERSISTENT 270, LONG_LIVED
11,805, UNKNOWN_AGE 5. Long-lived incidences comprise 95.54%; transient newborn
warmup alone does not explain the retained missing endpoints. First blocked age
on unique tracks is a different denominator: 265 newborn and two unknown.
The largest two cohorts account for 3,182/4,766 blocked edges (66.76%): SAMPLING /
COHORT EFFECT RISK remains explicit.

A_RAW_ABSENT=12,356; B_EXTRACTOR_LOSS=C_GAMESTATE_LOSS=D_SIMSTATE_LOSS=
E_PROVENANCE_OR_READINESS_REJECT=F_TRUE_INFORMATION_CEILING=G_UNCLASSIFIED=0.
**A is a retained-boundary classification, not proof of pre-extractor raw absence.**
These recordings serialize canonical observer output. Contemporaneous pre-extractor
raw and separate extractor artifacts are UNKNOWN. Current deserialize/Force field
roundtrips preserve the retained fields; refusing-stage SimState conversion is
NOT_RUN, not conversion loss. FIRST_LOSS_LAYER upstream remains UNRESOLVED.
The nominal 100% A–F retained-boundary classification does not meet a claim that
90% of true pipeline root causes are identified. B–E recoverability is UNASSESSABLE;
zero positive B–E evidence does not establish the <=20% stop condition. F=0 does
not establish any normal-player information ceiling. No stop condition is proved.

Known-to-unknown same-ID continuity cases: 0. The tracker signature contains
endpoints, so an endpoint change can alter observer identity. This zero is limited
to reliable retained same-ID continuity; it does not prove physical continuity.

Blocked entities per edge: mean 2.59253, median 2, p75 4, p90 5, p95 6, maximum 11.
One entity: 1,606 edges (33.696%); two: 1,124; three or more: 2,036.
Unknown remote entities can refuse a whole-world edge while local arithmetic
remains conditionally evaluable. They do not by themselves certify local causality.

Own Action Ledger pilot: NOT_RUN_OPTIONAL, zero trials, zero formal credit. No
owned active host lease was retained; this offline checkpoint did not bootstrap
a new pilot. Raw/extractor/GameState/SimState preservation for SELF intent remains
UNKNOWN. This is not evidence that lawful pilot collection is impossible.

Shadow: NOT_RUN because no lawful B–E recovery is positively established.
Production endpoint repair: NO_GO under the admission gate; endpoint diagnosis:
NEEDS_MORE_EVIDENCE. Future minimum evidence is a paired normal-player observation
and known own intent, with document/match/player/tick identity and before-only
endpoint provenance. Do not infer future routes or widen hidden-state research.

Machine report: V2_M2A_ENDPOINT_LINEAGE.json.
Complete fixture: tests/fixtures/v2/endpoint-lineage-entities.jsonl.gz.
No new formal action, arrival, capture, reinforcement, combat or coverage credit.
