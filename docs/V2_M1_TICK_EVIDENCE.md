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

### 2026-10-01 transport ownership correction

QUESTION: why does the sequence advance after reconnect with closed WebSockets?

EVIDENCE: the pinned Transport supports HTTP polling as well as WS/WT. The
normal ClientSession::attach (0x114bf6) stores 44-byte owned entries with boxed
transport data at +24 and vtable +28; the session Vec is context +348/+352/+356.
Static vtables 1115032 / 1114972 / 1115092 resolve +20 to the actual WS / WT /
HTTP state getters. Their Rc state bytes are +40 / +77 / +155 respectively.
HTTP uses an eight-byte aligned RefCell, unlike the four-byte WS/WT RefCell.
The WS onopen closure 0xc4ebd writes state=1 at borrowed data +28. The HTTP
constructor also initializes its state=1; failure/close change the state.

transport-research-e0ac23c469ab: online uses owned WEBSOCKET state=1. Five
seconds offline freezes 53299 and switches the owned entry to HTTP_POLL. During
30 seconds reconnect, two WS objects close, but 108 Fetch responses/finishes
and owned HTTP_POLL state=1 accompany sequence 53299 -> 53439. No network
payload, URL, query credential or other player's private state was recorded.
This resolves the earlier apparent no-wire-data interval. The row cohort is
RESULT screen metadata, not an accepted match cohort.

The second World::tick_before_inputs caller at 0xd274e is explicitly within
OfflineHarness::send/resolve_query/enter_arena processing. It retrieves a
separate World from its arena map via func3539. Transport::new_offline writes
the u64 discriminator 2 (0x8d324); the normal network observation gate now
refuses that mode before any tower or force payload read. Canonical source_mode
records NETWORK separately, and the source-clock identity includes that mode.

CONCLUSION: the prior global WebSocket.prototype query was not a reliable
connection authority. The adapter now follows only the current official
session's typed owned transport state, including HTTP fallback. An orphan OPEN
socket cannot authorize a world snapshot; HTTP with no WS can do so. Global
socket discovery is reserved for explicit diagnostics, reducing normal polling
overhead. Exact server generation time and snapshot age remain UNKNOWN.

STATUS: PASS for this transport discrimination question; M1 remains PARTIAL.
Synthetic privacy checks cover closed-owned/open-orphan WS, HTTP fallback and
offline refusal. They do not replace live reconnection or M1 gate evidence.

Live IN_MATCH follow-up transport-research-d09322d9e473: 33 online reads,
50 offline reads with frozen sequence 55399 and DISCONNECTED, then 338 reconnect
reads with sequence 55399 -> 55539 and IN_MATCH. All connected reads share one
derived match epoch. This run resumed the original WS rather than HTTP; 153 total
received frames, no Fetch requests. Both observed reconnect behaviors now have
explicit evidence. The earlier 99044354e1d2 attempt failed because an HTTP
alignment padding word was mistaken for a 64-bit borrow counter; it is excluded.
The pinned helper func6763 proves the borrow counter is 32-bit for all three
layouts. A nonzero synthetic HTTP padding word now has its own refusal-boundary
regression check. Successful short samples 07e379dabfff have 147 accepted /30.160s,
4.874 Hz, extraction p95 7.10ms and derived age upper p95 250ms (145 bounded).
This is not a ten-minute gate cohort and does not establish exact age.

### Source scope and cadence follow-up

The second World tick caller is behind the explicit Transport u64==2 branch
at 0xcd1e0..0xcd1e8. In NETWORK mode, the displayed world's tick call is within
ServerState::apply, reached by the normal ClientBroker socket update. Its
transition window brackets a real client-world application, not a server
generation time, network RTT, frame time or assumed simulation period. Exact
updated_at_ms stays UNKNOWN. Only conservative host-monotonic bounds are used.

sampling-f413115a25e6 is an uninterrupted 600.058s network-life cohort with
one document/derived match epoch: 2,917 accepted snapshots, 4.861Hz, extraction
p95 9.591ms, 55,011 metadata reads and bounds on all 2,917 snapshots. Upper age
p95 265ms fails the 250ms threshold. It has 58,499 force progress changes, 1,054
multi-observation derived tracks, no visibility transitions and no independent
UI samples. This cannot pass M1.

The observer's new on-update sampler captures each actually changed world
sequence after its visibility cache is ready, as well as the existing 200ms
timer. It does not interpolate timestamps or discard unfavorable age samples.
sampling-c592ecd633ed (30.122s) accepted 238 snapshots /7.901Hz, extraction p95
7.15ms, 236 bounded ages with upper p95 235ms; this remains a short diagnostic.

reload-reacquisition-7b1063300c33 proves fresh memory ownership after normal
reload with old reader rejection and two document acquisitions. The numeric
root address was reused, but the handle was fresh. Automatic official resume
kept the same Ruler; a new document epoch is not evidence of a new game life.
An earlier reload attached an empty event-owner collection too early; attach
now rejects that incomplete initialization, releases handles and retries through
ObservationSession. It does not retain an empty discovery forever. Global
navigation events plus a periodic origin check remove redundant per-source-read
round trips; the synchronous memory task still checks its own document origin.

snapshots-0fa5e8439ec1 was interrupted by the owned host's normal deadline and
is excluded from acceptance. New samplers preflight host duration and record
source manifests; closed-browser teardown is best effort and cannot hide results.

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

### QUESTION: can transport/session metadata certify server state age?

The production ClientSession::receive at 0x47f9a..0x48039 measures a local
receive-minus-local-send duration, subtracts a server processing duration and
stores a 3/4 old + 1/4 new RTT estimate. This is an EWMA, not a worst-case bound
for the creation/transmission of a particular World update. The pinned WS
rtt_ms trait implementation at 0x154d96 stores None. Normal ServerState::apply
receives only state/update pointers; its interpolation correction (0x10745)
continues to be excluded. Static production metadata did not reveal timestamp
field names or a NonActor formatter; absence of a name alone is not proof of
absence of all possible sources. This hypothesis produced no new timestamp source.

Public engine reference commit 83f62d2aacd94647dbc97d1bd4764fbfc17cdf55
[CommonUpdate schema](https://github.com/SoftbearStudios/kodiak/blob/83f62d2aacd94647dbc97d1bd4764fbfc17cdf55/common/src/protocol/updates.rs)
has Game(GU) without an outer creation timestamp. Its SessionCreated.date_created
is session metadata, not a per-game-update clock. The production client framework
contains newer ClientSession functions than that public reference, so this public
schema alone does not establish complete current-production absence.

CONCLUSION / STATUS: UNKNOWN for a legally observable server-generation timestamp.
Client application bounds and EWMA/receipt/frame/session clocks cannot clear
canonical authoritative freshness readiness. No source was promoted based on
these unsuccessful alternatives; M1 remains PARTIAL.

### QUESTION: is the new transport's bootstrap u64 a server clock?

Pinned ClientSession::new calls mint_bootstrap at 0xb0df2. mint_bootstrap
(0x151a3d) obtains the local random generator (func1157), draws a nonzero u64
through func1804 (0x100d06..0x100daf), then releases the generator reference.
The RNG initialization reaches getRandomValues at 0x97855. This initialization
uses the RNG state/refill path, not Date/performance time or a received world
update. The return object is copied from stack+8, so the minted stack+256 value
is the final session+248 local bootstrap. It must not be confused with the
peer bootstrap at session+256: receive compares/replaces that peer value at
0x48324..0x48355 and 0x48467..0x48472, and uses a change to forget/rebind streams.
The peer value's creation algorithm is not established by the local RNG proof.
Neither bootstrap value is exported or inspected
from live memory. Session receive also validates transport sequence continuity
at 0x47e91..0x47eb9; that sequence is not a millisecond world-generation time.

CONCLUSION / STATUS: FAIL for the local-bootstrap timestamp hypothesis. The
peer bootstrap remains an opaque stream-generation marker with no demonstrated
world-tick/time mapping. This closes this particular
source branch; it does not prove that every possible legal production source is
absent and does not independently authorize declaring M1 technically impossible.

session-clock-71082f680622 separately verifies normal receive var0 equals the
pinned context root in three invocations. Without exporting either bootstrap,
boolean-only classification rejects conventional Unix seconds/milliseconds/
microseconds/nanoseconds in 2010..2040 for both values. No peer clock encoding
was promoted from this test. Debugger pauses are excluded from performance.

### QUESTION: does a newly applied sequence guarantee a young Game update?

delayed-apply-259d89778b11 pauses normal ServerState::apply's Game-only branch
at 0xd627, after the Game update already exists. Its state argument equals the
typed context+512. No packet, actor payload or update bytes are inspected.
The experiment resumes normal execution after a recorded 1,031 ms interval;
the Game branch's normal end at 0x10745 has sequence 32819, versus 32818 before.
Both stored endpoints were originally floor-quantized, so subtracting 1 ms
recovers a conservative lower bound of 1,030 ms. Later tool runs round event
receipt up and resume send down. This held update therefore precedes application
by at least 1,030 ms,
although the sequence has just changed. This is a causal lower bound, not an
estimated network delay, assumed tick period or canonical snapshot age.

CONCLUSION / STATUS: FAIL for deriving young server data from a fresh application
alone. The experiment demonstrates the distinction on the unmodified client;
it does not measure ordinary p95 age, identify every possible timestamp source,
or assign this held update's age to a later snapshot. Normal execution was
resumed and all breakpoints removed. M1 authoritative age remains UNKNOWN.
