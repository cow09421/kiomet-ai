# External-action replay red-team review

**Review scope:** Static review of the frozen replay tool and tests plus read-only inspection of the candidate receipt; no code or tests were run. **Reviewed final hashes:** `tools/v2_external_action_replay.py` SHA-256 `181ca48809d00247fbc8b73871dbd4ae9ac8c50cf9ed16fdfffd8d5958b617c6`; `tests/test_v2_external_action_replay.py` SHA-256 `5305aa7e78f4e634525fc49d389737c8f1eac2684b1afc683b2c6034512c85c8`.

## Findings

The source-integrity gate works with Windows and slash-separated manifest keys. Before calling `replay_case`, `run_replay` compares every retained snapshot's raw SHA-256 against both the prior audit's `source_sha256` and the trajectory report cohort's `raw_sha256`. Any mismatch produces 13 Grade-C, zero-simulation, non-replayable rows; that branch does not call `replay_case`. The final candidate receipt reports every required snapshot digest matching. Its source/core manifests also report simulator source drift against historical report hashes; this is diagnostic context, while replay calculations use the current simulator. The raw snapshot gate prevents replaying replaced observation files.

The replay path contains no observed-after-state patch: each branch advances only its own prior predicted state, and the observed state is passed to comparison. Inferred births receive Grade B only; the report explicitly records zero Grade A and zero formal credit. Force and endpoint visibility must be `OBSERVED`, and transitions stop on changed document/match/player scope or nonconsecutive world ticks. Unknown, duplicate, incomplete, or inconsistent force evidence remains Grade C. A short observation window is `PARTIAL`/`OBSERVATION_GAP`; `full_trajectory_match` requires the entire requested horizon. The primary horizon reaches at least 20 ticks after the mismatch/action tick, with the original first 20 ticks retained as a separate secondary indicator.

The no-reset test gives observed states values 100 and 200 while the prediction advances 1→2→3; its step-call assertion confirms the next step starts from the prior prediction (2), not observed state (100). The ten focused tests cover malformed force IDs, unobserved force visibility, exact versus inexact source conservation, short-window partial status, changed match scope, and a source-hash mismatch that asserts `replay_case` is not called.

In the inspected candidate receipt, all 13 cases have Grade-B birth evidence and one injected action at the audited mismatch offset; each `error_growth` includes that audited mismatch sequence. This supports saying the observed birth was injected and compared at that boundary in every case. It does not support a full-window result: requested horizons are 21–28 ticks, while each case compares only 3–10 ticks before stopping on simulator `PRODUCTION_SUPPLY_LINE` (11 cases), `SPECIAL_PRODUCTION` (1), or an unresolved external action (1). All 13 are `PARTIAL`; there are zero full matches and zero first divergences within those partial comparison prefixes. Those zero counts must not be read as full-horizon agreement.

## Remaining test coverage note

Remaining coverage is nonblocking for this diagnostic tool: the hash test exercises an audit-hash mismatch but does not separately test a trajectory-report-only mismatch, and the scope test changes `match_id` while document/player changes are not individually covered. These guards are present in the implementation. No change is proposed in this review.

The evidence supports the bounded replay as a diagnostic comparison only. It does not establish Grade-A action provenance, general action acceptance, route/fuel behavior, or complete trajectory accuracy beyond the retained cases.
