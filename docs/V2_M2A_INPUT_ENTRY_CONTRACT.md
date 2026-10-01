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

P0 integration still required: arm/drain in the bounded recorder; verify the
authenticated lease, source digest and document; match each endpoint to its own
entry snapshot's unique visible projected center; require stable camera/canvas
geometry; certify selection=None and route facts at release entry; record and
compare all intermediate complete worlds. Server application time remains
UNKNOWN. A trusted input alone does not prove server acceptance or earn credit.
Current live admission tests keep the observer disabled and send zero troops.
The first finite host's missed status inspection remains PARTIAL; the subsequent
inline status check passed disabled startup admission. Synthetic protocol tests
do not establish armed real-event data or server input acceptance.

The reusable direct-route helper claims BEFORE_SNAPSHOT_ONLY. Only separately
proved event continuity can associate it with the real gesture. Existing relay,
fuel, relation, combat and dynamic aura guards still apply. The frozen one-arrival
capture retains its independently reviewed before/first-post stability proof.
No new arrival, reinforcement, combat or trajectory credit follows from this work.
