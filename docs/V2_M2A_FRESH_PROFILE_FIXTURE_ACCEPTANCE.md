# Fresh-profile fixture acceptance

Read-only acceptance review of the four staged gzip fixtures and
`V2_M2A_FRESH_PROFILE_SCENE_VALIDATION.json`. All four gzip streams decompress
successfully. Their raw and compressed SHA-256 values match the reviewed
working validation manifest exactly. The four gzip fixtures themselves are
unchanged; this acceptance note makes no claim about the manifest's staging
state.

| Fixture | Raw SHA-256 | Compressed SHA-256 |
| --- | --- | --- |
| `fresh-profile-preview-20261002.json.gz` | `449e97c98248a52edef08e6ac85fe438f50f50fca652f8349dfa0da5f5463163` | `904d1f8f01797d98b3f11d9e6324af02df549dce800e74b968867c682bc0f234` |
| `fresh-profile-one-wheel-20261002.py.gz` | `82ed01d3c496d322b0ee324ee36d6a6d327d5cee1e24c61614703d74bf7df727` | `b40b4498b7942487a57f75dee515ebaadcbc30fe17d22ebedb4d4eac399e468d` |
| `fresh-profile-one-wheel-20261002.json.gz` | `a2c9d9f208a28aadfef2c57b5cc079e2882834d3b1e5417aa0a890cc6b401dd3` | `8b523a8ada2cccfa6b92e8ff6456704af5f20f3a4d2ede12002fd6ba851c6dc5` |
| `fresh-profile-cohort-plan-20261002.json.gz` | `a28d2f7a1c4268b7cf63df9a884c5418f630276ff8cb3fe9c728b35f77d646f1` | `fcb5b8f66066b4ed99962f3158c2565e40da8c09b54c15b2e3c2af1bec76006b` |

The preview is `NO_ELIGIBLE_PAIR`, with input false, observer disarmed, no wheel
or troop gestures, 35 positively visible towers, 26 currently visible forces,
and five unknown force endpoints. The wheel receipt records one completed
ordinary +240 wheel and 34 post-wheel samples, with no sampling errors. The
before snapshot has nine force-endpoint readiness gaps. Every sample retains
35 towers and has six to eight such gaps; none is gap-free. Across the before
snapshot and 34 samples, all 266 endpoint-gap occurrences correspond to
positively observed visible Force records whose respective source/destination
Fact remains `UNKNOWN`. The final sample's seven gaps match the validation
manifest's `after_wheel_gaps` exactly.

The wheel receipt records zero observer arms and zero troop gestures. Both
observer snapshots are `DISARMED` with `armed_once: false`; the retained harness
contains only page movement and one wheel call, no click/down/up gesture. It
claims no simulated transition or formal credit. Thus the experiment supports
“profile rotation and one ordinary wheel did not resolve endpoint readiness”;
it does not establish whether the endpoints are fog-hidden or merely outside
the current view.

No sensitive candidate evidence was found in any fixture: recursive JSON key
checks and raw-text scans found no client-root, root-slot, hidden-actor, or
memory-slot candidate identifiers. The one-wheel harness internally calls the
existing `ClientExtractor` and serializes only canonical `GameState` snapshots,
camera values, tower counts, and readiness gaps. This aligns with `state.py`
requiring positive observed visibility for each retained Tower and Force, and
with `client_fae13.js` refusing to follow hidden actors. It does not serialize
the extractor's client-root candidates or any hidden actor records. No
sensitive metadata correction is indicated by this review.
