# M2A input-entry evidence boundary

The optional headless host installs `input_entry.js` through the installed
Playwright context init-script API before creating the controlled page. Only
initial exact `about:blank` pages are tolerated; none is used for game control.
The host verifies the observer's loading-at-install cue, disabled status and
document time origin before normal Play. Loading state alone is not proof of
registration order. The default host does not install or query this observer.

The observer is disabled until explicitly armed once per document. It registers
window capture listeners before page scripts and reads through the existing
pinned visible-world decoder, using already discovered memory/owner handles.
It performs no semantic WASM call, game-memory write, synthetic game event,
preventDefault or stopPropagation. Shared memory is excluded. The pinned WAT
declares ordinary linear memory without shared/atomic operations. The broker
source calls game `peek_mouse` synchronously on release before MouseState::apply;
late listener ordering was not proved, so late installation is refused.

Arming requires the host's pre-start evidence. Capture accepts only one trusted,
unmodified left-button down/up on the expected canvas and coordinates. It stores
at most two immutable snapshots, event/browser clock cues and canvas geometry.
The caller must drain down before release, drain up, then take the final receipt.
Errors invalidate proof while ordinary event dispatch continues. Root metadata
remains private for existing SourceClock identity; actor research pointers are
removed. Durable public journals must persist canonical state, not root pointers.

`ClientExtractor.adopt_captured_world` consumes the exact buffered payload without
reading memory again. Use host monotonic brackets around each event/drain and
consume down before movement/release, with the same extractor and trackers.
Browser epoch/performance/event timestamps remain separate. The API rejects
overlapping or retrospective brackets, including fractions of a millisecond,
future receipts, identity changes, partial/offline worlds and concurrent reads.
Normalization errors restore tracker state. Document changes and lifecycle gaps
remain invalidating and cannot revive a prior match through rollback.

The opt-in bounded recorder now verifies the authenticated lease, source digest
and document, arms/drains the observer, and adopts DOWN before movement and UP
before post-release sampling. Its pure endpoint helper checks each unique
visible projected center, stable camera/canvas and explicit deselection. The
observer rejects reset-sensitive blur/leave/touch/pointer-lock/visibility/keyboard
events; final reset-free history and document guards must qualify. The offline
auditor requires ordered endpoint checks and a VALID receipt containing that
history, compares duplicate displayed ticks, and never resets its original BEFORE
baseline to an entry frame. Cleanup after any post-DOWN error may dispatch a real
release and remains INVALID_OR_PARTIAL.

P0 real-event validation and handler-time route continuity remain required.
Endpoint evidence cannot establish the saved source phase, intervening capture
callback effects or actual path consumed by the game. Server application time remains
UNKNOWN. A trusted input alone does not prove server acceptance or earn credit.
Current finite live admission/preflight tests kept the observer disabled and sent zero troops.
The first finite host's missed status inspection remains PARTIAL; the subsequent
inline status check passed disabled startup admission. Synthetic protocol tests
do not establish armed real-event data or server input acceptance.

The reusable direct-route helper claims BEFORE_SNAPSHOT_ONLY. Only separately
proved event continuity can associate it with the real gesture. Existing relay,
fuel, relation, combat and dynamic aura guards still apply. The frozen one-arrival
capture retains its independently reviewed before/first-post stability proof.
No new arrival, reinforcement, combat or trajectory credit follows from this work.
