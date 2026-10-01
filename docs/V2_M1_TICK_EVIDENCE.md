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

### QUESTION: do active lifecycle payload or GameActorUpdate tail contain a clock?

Pinned receive decodes the active NonActor lifecycle case at 0x51a80..0x51a88
by writing tag 3 to stack+436 and branching past every variant payload decoder.
NonActor starts at stack+400; this tag maps to typed context+548 after normal
application. Tag 3 therefore has no typed variant payload from which to obtain
a timestamp. Inactive/dead variant storage is not a legal active field and was
not inspected in live memory. Initial/unavailable case writes tag 5 at 0x51c05.

The candidate GameActorUpdate tail at stack+392 is produced at 0x51a47 by
func3817. That function returns two i32 words: the Vec pointer (+4) and length
(+8), after its container allocation helper. Its caller decodes a collection
length at 0x519d4..0x519f5, initializes capacity/pointer/length at stack+12880,
and passes it to func3817. func3682 calls the allocation path with element size
0 and alignment 1; func1545 performs allocator/deallocator operations, not time
conversion. Normal ServerState::apply copies the 80-byte actor update to
stack+640 and uses its tail length at stack+716 as a decrementing loop count
at 0xdb2e..0xdb81 while moving singleton state. This is a zero-sized-element
collection descriptor, not a decoded u64 generation timestamp. No candidate
value or hidden actor payload was read or exported from live memory.

CONCLUSION / STATUS: FAIL for both of these particular timestamp hypotheses.
This typed decode/use proof is stronger than absence of a timestamp name, but
does not by itself establish that every other legal source is absent. The
canonical server-generation time and authoritative snapshot age stay UNKNOWN.

### QUESTION: what is the remaining scalar in the direct Game actor update?

The pinned decoder's Game branch begins at 0x4d832. At 0x4d848 it reads an
Option presence byte; when present it decodes a u32 at 0x4d862 into stack+324,
and stores the 0/1 discriminator at stack+320 (0x4d86f). The nine subsequent
8-byte collection descriptors occupy stack+328 through +399; their conversion
helpers have explicit element sizes 12, 36, 2, 44, 24, 2, 2, 12 and 0.
The resulting actor update is 80 bytes, followed by the 136-byte NonActor.

Normal ServerState::apply copies this actor update to stack+640. Its optional
scalar tag is checked at 0x10422..0x10431, a world-derived value is accumulated
from actor content and the Singleton tick, and 0x105a1..0x105ac compares the
result with the decoded u32 at stack+644. This establishes checksum semantics,
not time semantics. The generated public ActorUpdate macro also defines only
checksum plus completes/inboxes/removals collections for each actor, consistent
with the production layout; the exact current decoder/use path is the primary
evidence because the reference checksum type differs from the old Kiomet source.

CONCLUSION / STATUS: FAIL for interpreting the remaining direct Game scalar
as generation time. No direct Game wrapper timestamp is present in this decoded
layout. This does not promote receipt time, RTT or an actor tick into one, and
does not assert complete absence across every transport or UI metadata path.

### QUESTION: can an ACK supply a causal generation-age bound for each Game?

Pinned Frame::write at 0xc9d5e branches separately into data and control
variants. Data calls write_data at 0xc9da2/0xc9db6/0xc9dca with a kind, pointer
and length. write_data (0x14b8d3..0x14b8ea) writes only the varint header
(length<<2)|kind and copies the specified bytes. The control ACK branch
0xc9e23..0xc9e96 writes a control code, optional acknowledgement sequence,
optional state byte and a rounded/saturated processing-duration byte. The
duration is encoded as min(255, min(65535, duration+2)>>2), not a generation
timestamp or Game identity. Receive separates control with header&3==3 and
parses data length with header>>2 (0x47c00 onward). Its ACK handling at
0x47f17..0x48039 matches a send sequence to a local send-time entry and updates
the previously documented RTT estimate.

CONCLUSION / STATUS: FAIL for treating this ACK as a per-Game generation-age
certificate. Its echoed send sequence and processing interval do not identify
which Game was generated after that send, even when frames share a transport
delivery. No causal association between that ACK and a specific Game generation
has been established. No raw packet or hidden actor bytes were read for this
proof. Other lawful source hypotheses remain possible; server age stays UNKNOWN.

### QUESTION: is normal receive's f64 time a remote clock through a JS binding?

The current official /client.js is 117,757 bytes with SHA-256
05b51675785a3f6568f4d80562dabb4f59a6130504c7de9cf777c33094e.
Its import __wbg_now_88621c9c9a4f3ffc directly returns Date.now(); the other
now import invokes now() on its supplied JS object. Pinned now_ms at
0x11c893..0x11c8ef obtains window's performance object (func5200), invokes
that object's now at 0x11c8cc, and falls back to local Date.now at 0x11c8db.
Its ten direct call sites are 0x55297, 0x55515, 0x55e9d, 0x7f235, 0x7f258,
0x7fe28, 0xc12e1, 0xddf11, 0xde14c and 0x10c4d9. In particular HTTP polling
uses it to compare/store local polling times, while the socket callback stores
it at its local stack+40 before event-data handling at 0xc131c. No value from
account claims, packet bodies or hidden actors was inspected in this tracing.

CONCLUSION / STATUS: FAIL for interpreting this binding/receive-time path as
remote generation time. The JS implementation establishes its local clock
origin; neither Date fallback nor performance receipt time supplies missing
Game generation semantics. This is a finite source-path result, not a claim
that every possible lawful source has been exhausted.

### QUESTION: do HTTP Date or x-held certify Game generation time?

transport-headers-6eca31133777 observes 151 official-domain Fetch responses
during one bounded reconnect, with Date in one-second textual resolution.
No body, URL, credentials or other header values were stored. Each response's
Game association remains UNKNOWN. The online-only a2e592adaeab has zero HTTP
responses because the owned session had returned to WebSocket; it is not a
successful HTTP comparison.

The later 375a9c52106e reconnect cohort has 147 responses, 28 with x-held
values (1..238, median 16.5), and no x-paged header. Missing x-held values are
not filled with a measured zero. Pinned static data at 1203744 spells x-held;
1203750 spells x-paged. The normal HTTP future reads x-held via Headers.get
at 0x55765, parses a floating-point number, and stores it at its +72 field
(0x55bd1). Later 0x55de9 retrieves it and 0x55e9d..0x55ec0 subtracts it from
local now_ms minus local request-start time. This is a transport wait-duration
correction for RTT, with clipping at 0x55ecd onward, not a decoded Game clock.
x-paged is separately read at 0x55bfc and stored as a presence flag at 0x55c50.
Its absence in this cohort is not a proof that all responses contain one Game.

The public reference
[server socket](https://github.com/SoftbearStudios/kodiak/blob/83f62d2aacd94647dbc97d1bd4764fbfc17cdf55/server/src/socket/socket.rs)
queues CommonUpdate<GameUpdate> through an unbounded channel at line 64,
then receives, encodes and sends it at lines 226..245. Generation, queueing and
transmission are therefore distinct in that reference. It does not establish
the private current HTTP server's x-held measurement boundaries or a bound on
time between Game generation and waking its response task.

CONCLUSION / STATUS: FAIL for using Date or x-held directly as Game generation
time. UNKNOWN for a causal per-Game age bound: neither this client-side duration
use nor response metadata establishes the necessary generation/wakeup mapping.
No measured header is promoted into canonical updated_at_ms or snapshot age.
