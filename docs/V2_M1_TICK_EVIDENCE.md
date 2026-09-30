# M1 source sequence research — pinned fae13d, 2026-09-30

## QUESTION: does the candidate represent world updates or rendering?

EVIDENCE:

- Public `common/src/world.rs::tick_before_inputs` advances `Singleton.tick`.
  `client/src/state.rs::apply` advances the world before marking visibility dirty.
- The actual official WASM SHA-256 is unchanged. Its named
  `World::tick_before_inputs` reads/increments/stores a u16 at world + 45084
  (store bytecode `0x19bb1`). The world base is context + 648; the read field is
  therefore context + 45732. The singleton presence discriminator is + 45720.
- The real WASM `ServerState::apply` corrects interpolation using -0.25 and
  0.6 at `0x10745`; the frame callback independently adds elapsed frame time at
  `0xd70d9`. This interpolation value is deliberately excluded as a source clock.
- `tick-research-6283fd732103.json`: normal 15 seconds, 470 metadata reads,
  tick 9988 → 10048, 60 observed transitions. There were 18 one-second pairs
  with visible typed-unit changes across the experiment.
- During 5 seconds of browser network offline mode: 158 reads, tick 10048
  unchanged; interpolation advanced 0.184 → 5.156 seconds. On reconnect, the
  world caught up: 10048 → 10127 with 57 distinct read-to-read transitions.
  Counter difference and observed transition count are intentionally different.
- Actual RESULT screen: `tick-research-461b9ec3a88d.json`, two 10-second phases,
  each 319 reads and 40 increments; active-state discriminator was 1 instead of 3.
  Result metadata remains legal; world payload reads were rejected.

CONCLUSION: a read-only observed world sequence, independent of frames. It is
not a timestamp and is not match-specific. It wraps at u16. Moving-force live
correlation, reload and complete lifecycle validation are still pending.

STATUS: PASS for the frame-independent sequence question; UNKNOWN for complete
M1 authoritative-clock acceptance. Numeric `GameState.tick` is OBSERVED; exact
`GameState.updated_at_ms` and exact snapshot age remain UNKNOWN.

## QUESTION: can source age be measured without inventing a timestamp?

EVIDENCE: a changed sequence must have been applied between the prior read's start
and the current read's finish. Normal JavaScript tasks cannot interleave a running
WASM state update. `SourceClock` retains that interval on repeated equal ticks,
invalidates it on identity/host-clock changes and refuses first-sample age.
The resulting interval is DERIVED. No tick-period multiplication is used.

Two 30-second real 5 Hz samplers produced 149 and 146 accepted snapshots,
4.938 / 4.848 Hz, extraction p95 9.83 / 10.21 ms. Conservative source-age upper
p95 was 416 / 400 ms. Exact age p95 remains UNKNOWN. These are preliminary
performance measurements, not formal gate runs.

CONCLUSION: update-time uncertainty can be bounded, but the current polling
interval is too coarse to demonstrate the required 250 ms percentile.

STATUS: PARTIAL. Do not reinterpret the upper percentile as an exact timestamp
or substitute extraction latency for state age.

## QUESTION: can old visibility be exported immediately after a world update?

EVIDENCE: the pinned `update_visible` (`0x53dc2`) consumes context + 45784 as
the visibility-dirty flag. It selects expanded visibility when context + 548
is not 3, or when the official cheats/B-key condition holds. `Color::new`
independently uses + 548 == 3 for the active player's relation.

CONCLUSION: positive cached references alone are insufficient during that gap.
The decoder now refuses all tower/force payload before reading any of them when
visibility is pending, active state is false, or expanded visibility is enabled.

STATUS: PASS for the explicit refusal rule; UNKNOWN for the full live
visible → hidden → visible acceptance matrix.

## Evidence limits

The first tick experiment ran on an extra restored official page in the isolated
task profile. The later result experiment used the recorded BrowserHost page.
Both were the unmodified official client, but they were separate player sessions;
they are not reported as one match. Extra restored task pages have been closed,
and ambiguous page selection fails closed. One later lifecycle experiment was
interrupted by its host's normal timeout; it is excluded from acceptance. The
replacement experiment owns its browser and streams evidence before teardown.

No force was launched, no game commands were injected, no memory was written,
and no physical desktop input was used. Runtime evidence files are ignored by
Git under `runtime/research/v2/`; this compact summary is the committed evidence.
