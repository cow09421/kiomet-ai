# Action-local readiness cause review

**Verdict: R1 is a strong candidate, but the evidence does not establish explicit R1. Classify the prior blocked preparation as R3 unresolved at the action level. The action-local fix is not applicable under the stated gate.** This was a bounded read-only review; it made no production edits, commits, or live actions.

The execute preparation ended with `force:0:source,wait_deadline_exhausted`, created no event or action intent, and delivered no input. The pilot record reports 0 valid own-action trials and 0 dispatch attempts. The accompanying actual-state layer records the same readiness gap and an L4 refusal, `NOT_READY: force:0:source`. Its visible Force is Enemy-owned (owner 17), with unknown source and observed destination 17105164. This is direct evidence that an Enemy force field tripped the global readiness gate. Its relationship to any intended action cannot be proved because the action pair was not retained.

The actual layer’s canonical snapshot also contains known local state: player 43, match `67e39eb29a0e41d3aeb8cb9a89c26c65:p43:29ffd3701c1a46119020e9cd83c6df27`, tick 584, and observed/derived own and neutral tower records with typed inventory, deployable counts, neighbors, and positions. But the layer does not bind the failed preparation to a specific source/destination pair and does not preserve the raw selection evidence or a route certificate for that pair. Therefore it cannot prove the entire action-local premise on the same rejected sample.

The older preview with candidate `16908556 -> 16974092` cannot fill that gap. Its document and match are `99ed523d250b4a39ae3c676f57b3ce30` and `…:p43:23fdc1643f124b7f87ed71e0503127e9`, distinct from the actual rejection layer. That preview’s direct route certificate was qualified before-only, while `gesture_continuity` remained UNKNOWN. Those facts describe that preview’s route and attribution status only. They do not establish the rejected action’s route or intended endpoints. The later preview is a third match, reports no candidates, and remains blocked on `force:0:source` and `force:1:source` after 48 sample attempts.

The code explains why an unrelated force source can block an otherwise local action: [`control.py`](../src/kiomet_ai/v2/control.py#L31) checks all visible towers and every observed force; any force whose `source` is unknown adds `force:<index>:source`. Execute preparation calls this global gate during its readiness wait before scenario validation or selection, and before-intent checks call it again ([capture flow](../tools/v2_controlled_transition_capture.py#L983), [pre-intent gate](../tools/v2_controlled_transition_capture.py#L1027)). This makes R1 a plausible gate-level cause. R1 still requires proof that the same attempted action had known source, destination, route legality, units, and match continuity, which the retained receipt does not provide.

A successful before-only route certificate and UNKNOWN gesture continuity are different facts. The certificate’s `qualified=true` means the pinned local A* check supports a direct path for that snapshot; `gesture_continuity=UNKNOWN` leaves the attribution of an actual gesture or force to that route unresolved ([route certificate](../tools/v2_direct_route_certificate.py#L46)). In this rejected preparation there was no gesture and no action-bound route certificate, so route/action legality stays unproven rather than being inferred from another preview.

The later host lease margin is a separate R4-style preflight exclusion recorded in the pilot note. It does not explain the execute preparation’s `force:0:source` result. R2 is not the observed readiness gap, since the actual layer has known own and neutral tower facts; however, missing action-pair binding prevents ruling out a local action-specific issue. No R5 evidence is needed to explain the remaining uncertainty.

Sections 30–32 allow an action-local fix only after explicit R1. That condition is not met, so the bounded decision is **NOT APPLICABLE** and the readiness review stops here. No callback, queue, canvas, WASM, or input-entry research was reopened.

If Sol later chooses to implement action-local readiness after obtaining same-sample R1 evidence, the narrow conditions are:

- Bind source, destination, complete typed units, route certificate, lifecycle, tick, document, and match identity to one fresh snapshot.
- Continue to refuse when own source, own target, route legality, units, selection/command prerequisites, or match identity are unknown.
- Permit an unknown remote Enemy endpoint only when evidence shows it is unrelated to the bounded action and its local path.
- Keep strict world-level readiness for full-world simulation and differential claims.
- Add the six requested negative cases: each unknown action-local prerequisite refuses, while unrelated remote Enemy UNKNOWN alone does not block an otherwise complete action.

Source instruction: attachment sections 28–32. Evidence: [`paired pilot note`](V2_M2A_PAIRED_ENDPOINT_PILOT.md), [`paired pilot receipt`](V2_M2A_PAIRED_ENDPOINT_PILOT.json), the named compressed controlled-transition and paired-layer fixtures, and the three code files linked above.


## SHA-256 evidence manifest

Hashes are SHA-256 of the exact on-disk bytes for each path in `evidence_paths` in the JSON report.

- `2200f56b27d807e015758dd82407649c1a5d62730a528c01b262f1af3045504c` — `docs/V2_M2A_PAIRED_ENDPOINT_PILOT.md`
- `89b3b76f3707b0565c75e0d7478f6b886217dd4d3340d62855aa06691ef12712` — `docs/V2_M2A_PAIRED_ENDPOINT_PILOT.json`
- `2c8fccf9edb66af1ba8f0dac91e378d1555e22c1f998715ab480f316726b8c97` — `tests/fixtures/v2/endpoint-pilot-controlled-transition-78964b1c5f9b.json.gz`
- `4f6a3415ea3e8ee0357452f8a9e8d135669ed4e7f4f7dd8df3e2bfa8d88b3740` — `tests/fixtures/v2/endpoint-pilot-controlled-transition-2fafb60c2e7a.json.gz`
- `886ae57ca1e413793eac6b6328af12c1bb03c08e0c75ae7691b46aeb086dcc15` — `tests/fixtures/v2/endpoint-pilot-controlled-transition-a7c8a769c215.json.gz`
- `2f6dd9f7d686b34c49045c5e5490d293e7b1b98e7220acfeb54db84f8b7620ff` — `tests/fixtures/v2/endpoint-pilot-paired-layers-726f0775adde.jsonl.gz`
- `505e845f09c7ed50e42f32a759a7f1cba830874bb9a079219df258563a6a00d7` — `tests/fixtures/v2/endpoint-pilot-paired-layers-d9075298573c.jsonl.gz`
- `90868cb128b29d10122f665d58cacba874e5c960cf1b0d7f7e2eb8d24e5cae89` — `src/kiomet_ai/v2/control.py`
- `dcf8c3cb8901fde1f30756bcdb760f393330b08e6f0c3c5f9130ad7d50e73e04` — `tools/v2_controlled_transition_capture.py`
- `cb651091db5c0518402071beabbf4fc5ec85a02729428cd20288656dda08fc6f` — `tools/v2_direct_route_certificate.py`
