# M2A force endpoint preview review

The 2026-10-02 immediate preview cannot distinguish an endpoint outside the current viewport from an endpoint hidden by fog. The retained sample deliberately drops endpoint IDs unless the endpoint is also a positively observed tower. Its missing endpoints therefore remain `UNKNOWN`; the preview is not eligible for a force gesture.

The saved receipt is `runtime/research/v2/friendly-immediate-preview-20261002.json` (preview `b8635f548b35`, SHA-256 `637e649e743590f35b5592332f71a1560c57d3d859af525c98a06d85716ed4bf`). It reports `PLAYER_VISIBLE_COMPLETE` with 50 positive sensor slots and 50 decoded towers, while control readiness still has `force:0:source` and `force:2:destination` gaps. In the force rows, force 0 is an enemy tank group with its destination, tower 18874640, observed and its source unknown. Force 2 is an enemy bomber outbound from observed tower 18874642 with its destination unknown. Both rows are currently visible through the normal renderer. Force 1 has both current-leg endpoints observed.

## Why the endpoint location is unknown

The pinned decoder walks positive `Visible.refs` slots and skips zero-ref fog slots before reading tower payloads. It then builds `visibleIds` only from those decoded towers. For each currently rendered force segment, it emits the source or destination ID only when that ID belongs to `visibleIds`; otherwise it emits `null`. The force provenance distinguishes a normal inbound vector from an outbound vector to a non-visible endpoint, but does not say why the endpoint is non-visible. See `src/kiomet_ai/v2/observe/client_fae13.js` around lines 145–180 and 190–236.

The canonical `PLAYER_VISIBLE_COMPLETE` certificate means every current positive sensor slot decoded to a tower. It explicitly does not certify the whole world or resolve unknown force members. The receipt retains only the known endpoint positions; the fast preview does not persist `camera_candidate`, and the hidden endpoint IDs and coordinates are intentionally absent. The canvas metadata is 1280×900, which is not enough to project an endpoint that has no observed coordinate. We therefore cannot classify either missing endpoint as merely outside the viewport or as fog from this evidence. See `docs/V2_OBSERVATION_CONTRACT.md` around lines 99–112.

The renderer may expose a force when only one current-leg endpoint is visible. That visibility proves the force itself is on the ordinary rendering path, not that both endpoint towers are currently player-visible. The output labels `normal renderer: visible tower inbound` and `normal renderer: visible tower outbound to non-visible endpoint` are consistent with that limit.

## Existing viewport evidence

The prior camera probe used one ordinary page-local wheel event with `deltaY=240` at canvas center. A was already complete and remained at 30 positive refs / 30 decoded towers after one event, so it did not demonstrate coverage repair. B remained partial after two such events, with 32 positive refs and 29 decoded towers. The second zoom increased the camera zoom value from about 22.84 to 28.77; the camera transform divides world displacement by that value, so this is a zoom-out. The prior result says normal zoom alone did not repair B. See `docs/V2_M2A_FRIENDLY_CAMERA_VALIDATION.json`, `runtime/research/v2/friendly-camera-probe-20261002.py`, and `src/kiomet_ai/camera.py`.

Those runs measured tower-set coverage, not whether a particular force endpoint became visible. They provide no basis to infer that another zoom will reveal these endpoints. Panning also has no target coordinate because the endpoint coordinates were withheld, and the existing evidence does not establish a bounded ordinary pan gesture. Do not pan toward a guessed hidden location.

## One bounded preflight for a later cohort

If another finite host is scheduled, allow at most one additional ordinary wheel event in the entire preflight: `deltaY=+240` at the canvas center, before observer arming. Record a canonical baseline, the camera candidate, positive-ref/decoded-tower counts, and the force endpoint facts. After that single event, collect ordinary samples for at most four seconds and rerun the same full-coverage and control-readiness checks.

Proceed to the existing candidate review only if the fresh sample has no unknown force endpoint gaps and all existing identity, freshness, ownership, inventory, supply-line, projection, and route gates pass. If either endpoint gap remains, stop with zero observer arms and zero troop gestures. Do not add another wheel event or substitute a pan. A newly decoded endpoint may be described as visible after the viewport change only when the fresh canonical sample positively includes its tower; otherwise retain `UNKNOWN`. If the endpoint gap clears but no friendly candidate qualifies, stop without arming.

This is one final bounded diagnostic because earlier camera validation already spent three ordinary wheel events across its probes without establishing coverage repair. It is not a promise that the endpoint is viewport-limited. A persistent unknown after the single event remains ambiguous between fog, viewport culling, and other current-endpoint availability limits.

The existing 33/33 complete preview and subsequent recorder refusal described in the cohort history remain subject to the same rule: unknown force members block readiness even when tower coverage is complete and friendly candidates were listed. Keep the full-visible-world readiness scope; candidate discovery does not authorize skipping a force gap.

## Outcome

No host, input, observer, or runtime files were changed for this review. The immediate preview remains a zero-input, zero-credit refusal. The next cohort has a finite preflight ceiling of one normal zoom-out event, followed by a hard stop if force endpoint readiness is still unknown.
