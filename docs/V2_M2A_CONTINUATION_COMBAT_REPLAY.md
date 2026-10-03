# Continuation-aware passive combat replay

**Outcome: INSUFFICIENT_INFORMATION**. This retrospective reanalysis adds no Grade A/B, formal Combat, or certification credit and changes neither formula nor production.

All 31 frozen cases were retained: 26 original MATCH / 5 original MISMATCH; qualification remains 4 / 27. Original development/holdout split remains 22/9.

The earlier passive replay had already inspected per-case post-arrival force visibility: **PREVIOUSLY_INSPECTED = YES**. This makes the current replay retrospective and not independent evidence.

## Primary same-tick continuation accounting

Primary uses only offset 0: predicted survivor vector must equal observed target inventory plus every newly observed compatible same-tick outgoing vector, with predicted owner matching observed post-combat owner. Partial retained inventory and multiple outgoing forces are included; oversized vectors remain counterexamples. Offsets +1/+2 are exploratory only.

Same-tick outgoing status 2×2: `{"MATCH": {"NO": 24, "UNKNOWN": 2, "YES": 0}, "MISMATCH": {"NO": 0, "UNKNOWN": 0, "YES": 5}}`.
Flip counts: `{"MATCH_TO_MISMATCH": 0, "MISMATCH_TO_MATCH": 3, "NONE": 24, "UNKNOWN": 4}`.
Qualified cases with known residual counterexample: 0; original MATCH cases truly flipped to MISMATCH: 0.

## Controls and limits

A and B controls use the shared detector and preregistered deterministic sampling. A positive actual-target outgoing in a noncombat event is reported separately from false pairing on its non-arriving decoy.
Control gate passed: False; blockers: `["CONTROL_B_AVAILABLE_LT_20", "CONTROL_REPORT_OVERALL_GATE_FAILED"]`.

The JSON artifact includes all 31 case rows, original status and split, unchanged qualification, predicted/observed vectors and owner, outgoing counts/sums, unknown/observed-only accounting, per-offset exploratory data, scope/tick provenance, flip direction, controls, and source hash receipts.

## Next prospective recording

A separate prospective passive recording specification can be finalized after this outcome. No broad recording run, live combat, production change, formula edit, owner-only production rule, or evidence-credit increase occurred.
