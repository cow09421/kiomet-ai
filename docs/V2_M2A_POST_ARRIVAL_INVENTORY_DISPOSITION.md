# Post-arrival inventory disposition

All 45 originally scored capture cases are retained (13 inventory MATCH / 32 zero-inventory MISMATCH; original split unchanged). This is a retrospective diagnostic, not a new holdout or production rule.

## Primary arrival-tick accounting

Complete exact accounting: 43/45; positive-outgoing cases: 32, of which 31 account exactly. No-outgoing equality is reported separately as a tautological check.
Holdout: 19/21 complete exact; 11 positive-outgoing cases, 10 complete exact in 10 groups / 3 contexts. Frozen gate verdict: STRONG_CONTINUATION_PATTERN (conditional observational accounting; no prediction or causal claim).

## Time and provenance

Offset 0 is the arrival tick; offsets +1 and +2 are exact first-retained observations at consecutive ticks in the same scope. Existing `following` means +1. Later offsets are supplementary and cannot rescue primary arrival accounting.
Outgoing rows are visible signatures, not proven physical births. Duplicate signature multiplicity is preserved; observer IDs are supplemental only. Unknown plausible aliases or incomplete census make complete accounting UNKNOWN, while observed-only arithmetic remains visible.

## Results by split and case

The JSON report contains every case, per-offset target state and outgoing force list, before-context fields, accounting status, capacity/production/inbound/line facts, group tables, and raw-source hashes.

## Verdict

STRONG_CONTINUATION_PATTERN

## Result summary and stop decision

| Inventory group | Cases | Compatible new outgoing observed in 0..2 | Visible-only exact at arrival | Complete exact | Mismatch | Unknown |
|---|---:|---:|---:|---:|---:|---:|
| Original MATCH | 13 | 0 | 13 | 12 | 0 | 1 |
| Original ZERO | 32 | 32 | 32 | 31 | 0 | 1 |

All 32 ZERO cases first show the compatible outgoing at offset 0; none first appears at offset 1 or 2. The MATCH group has 12 cases with no observed compatible outgoing and 1 UNKNOWN absence determination. There are 44 complete consecutive windows; b1f7f9416e92:2396:0 ends at arrival, so future offsets remain UNKNOWN. Primary accounting remains independently evaluable there.

All 32 known outgoing owners equal the observed new target owner. All 32 visible outgoing sums equal the incoming vector, with zero observed-only false explanations. Complete positive accounting is31/32; the remaining case is UNKNOWN, not a mismatch. The 13 no-outgoing equalities are separate checks and do not add positive continuation support.

| Before context | MATCH 13 | ZERO 32 |
|---|---:|---:|
| Visible line fact UNKNOWN | 13 | 32 |
| Normal capacity | 6 | 8 |
| Pinned ordinary ground overflow | 3 | 8 |
| Capacity/clipping ambiguity | 4 | 16 |
| Production due | 0 | 0 |
| Inbound complete | 9 | 17 |
| Inbound incomplete | 4 | 15 |

MATCH spans 4 contexts; ZERO spans 5. All 45 have distinct `(context,target)` and transition groups, so no repeatedly scored tower dominates. The full JSON retains per-recording concentration and each target ID. These remain retrospective groups, not randomized independent trials.

The 2 complete-accounting UNKNOWN cases are 85391858b5d8:2261:0 (MATCH) and 7d56a775bc4c:482:0 (ZERO). Both have a same-owner compatible unknown-source force; one also has a before exact-vector alias. Their UNKNOWN sources and destinations remain unfilled. No source genealogy or automatic relay / multileg / opponent relaunch attribution is made.

Verdict STRONG_CONTINUATION_PATTERN / POST_ARRIVAL_CONTINUATION_SUPPORTED is limited to the conditional statement: observed newly outgoing composition explains current captured-tower inventory. NO_BEFORE_TRIGGER_FOUND in the frozen Dev-only field set; the capacity candidate performs 15/24 versus the zero-only baseline 21/24 and is not frozen. No old-holdout trigger optimization.

Production changes NONE. Owner-only Capture remains a frozen hypothesis and needs new post-freeze prospective passive evidence: >=10 qualifying groups across >=2 contexts, >=90% owner agreement, no unexplained high-impact mismatch. No new recordings, hypothesis revisions, or live dispatches; no new Grade A/B/provisional/formal credit. No deterministic relay forecast is implemented.

Stop this Supply-local question. NEXT P0: CONTROLLED / PASSIVE COMBAT under existing readiness. No second Supply archaeology, endpoint reopening, reinforcement expansion, Combat production, or planner.

Independent controls: 13 focused tests passed; synthetic guards grant no empirical credit. All final documents precede the final-HEAD `tests -k v2` run. Actual HEAD, branch, dirty status, source hashes and final PASS/FAIL/SKIP/ERROR/DESELECTED counts are bound by `runtime/research/v2/inventory-disposition-final-head-regression.json`. No documentation commit after that receipt. Push v2-rebuild only; main remains the v1 archive.
