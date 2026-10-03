# Continuation-aware combat diagnostic checkpoint — 2026-10-03

Legacy bounded task outcome: **INSUFFICIENT_INFORMATION**. This is retrospective
diagnosis, not a Goal-mode confirmatory Gate result. The newer Goal contract
supersedes the old milestone-based next-P0 ranking.

Preregistration commit: `9cb39cb`; control identities committed before scoring:
`005501b`. Frozen formula SHA256:
`8b84726349cc52d718dc8f4fbc42416067ae2df9924cefbe88e899cd8d0edfd3`.
Formula revisions 0; compatible-definition revisions 0. Ordinary implementation
bugs were repaired against the same committed definition before accepted scoring.

All 31 unique cases retained, development22/holdout9, original MATCH26/MISMATCH5.
Qualification remains4 qualified/27 unqualified, with every prediction and
qualification recomputed through the existing scorer and asserted unchanged.

| Original | Offset0 outgoing YES | NO | UNKNOWN |
|---|---:|---:|---:|
| MATCH | 0 | 24 | 2 |
| MISMATCH | 5 | 0 | 0 |

MISMATCH_TO_MATCH3; MATCH_TO_MISMATCH0; NO_CHANGE24; UNKNOWN4.
Complete accounting: EXACT27 / MISMATCH0 / UNKNOWN4.
Qualified complete accounting: EXACT4 / MISMATCH0 / UNKNOWN0.
Observed-only inventory+outgoing equality31/31 is a separate conditional result.
The two unknown original mismatches and two unknown original matches retain
plausible aliases; no amount fitting, subset selection, clipping, or fake zero.
Offset+1/+2 is exploratory only and cannot rescue the primary score.

CONTROL A: N100, known background positives0 (0%), NO93, UNKNOWN7.
Conservative positive+unknown bound7%; PASS. CONTROL B: N50 actual noncombat
targets, compatible outgoing YES40 (80%), NO7, UNKNOWN3. Actual noncombat
continuation is not a false pairing. Only11 distinct non-arriving paired decoys
were available: positive0 (0%), NO7, UNKNOWN4; bound4/11=36.36%. The other39
sampled events have no certified decoy and were not replaced. B FAIL: fewer than
20 available decoys and inadequate conservative specificity evidence. Both
controls and replay bind the identical shared-detector source hash. This control
failure alone forces the frozen INSUFFICIENT_INFORMATION exit; 3/5 complete
rescues also falls below the frozen4/5 support requirement.

PREVIOUSLY_INSPECTED SAME-TICK OUTGOING: YES, with a precise scope caveat.
All31 previously had generic arrival/following force-status inspection. Only the
five nonzero attacker-survivor cases entered the old source=target new-leg scan;
these are precisely the five original mismatches, already marked
NEW_LEG_COMPATIBLE_OWNER_AND_SURVIVOR_VECTOR. The other26 were not previously
given exhaustive outgoing accounting. Diagnostic independence is reduced,
especially for the five mismatch explanations.

Owner31/31 remains existing descriptive evidence. OWNER_ONLY_COMBAT production
rule NONE. New Grade A0 / Grade B0 / formal Combat0 / certified Combat0.
Production changes NONE; all17 core source hashes unchanged from65e9b46.
No live input or new recordings. No Endpoint, Supply, Planner, qualification
relaxation, reachability exclusion, or uncertainty architecture changes.

The old task recommends improved-field prospective passive recording rather
than another old-corpus replay. Any future specification must freeze formula,
qualification/hostility/inbound completeness, offset0, the compatible detector,
selection, scoring, N, and stops before recording. Preserve visible position,
direction/progress, endpoints when visible, owner/vector/relation, all visible
inbound/outgoing, before/after target state, tick/sequence and full identity.
Reachability exclusion and field-level knowledge are future design requirements,
not current implementations. No new recording has been started. Under the newer
Goal contract this is a deferred candidate, not the automatic next engineering P0.

Full31 rows and raw source receipts: V2_M2A_CONTINUATION_COMBAT_REPLAY.json.
Controls/sample identities: V2_M2A_CONTINUATION_COMBAT_CONTROLS.json and
V2_M2A_CONTINUATION_COMBAT_CONTROL_SELECTION.json. Reproduction: run controls
with `run_controls()` first, then `.venv/Scripts/python.exe -B
tools/v2_continuation_combat_replay.py`; the CLI refuses a detector hash mismatch.

All final diagnostic documents precede the evaluated commit. Its actual HEAD,
branch, preserved two-note dirty status, hashes, commands and full `tests -k v2`
counts are bound by
runtime/research/v2/continuation-combat-final-head-regression.json.
The evaluated commit is not a claim that later Goal work has the same HEAD.
Remote main must remain234cfad918381adfd2a48a183ca17d35b64970e0.

Historical milestones: OLD M1 FAIL / M1B PASS / M2A IN_PROGRESS /
M2 IN_PROGRESS / M3 NOT_STARTED; Endpoint UNKNOWN_BUT_RESEARCH_CLOSED.
Current Goal Gates are V, L and Invariant; no Gate movement is claimed here.
