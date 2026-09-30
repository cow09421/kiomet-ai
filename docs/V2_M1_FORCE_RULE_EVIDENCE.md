# M1 visible forces, pinned rules and typed ownership evidence

Status: PARTIAL, 2026-10-01 Asia/Taipei. No M1 PASS. Official client SHA-256
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`.

## QUESTION: can root discovery avoid a game-memory scan?

EVIDENCE: normal JS event closure types 1079544/1079504 hold an 8-byte
environment. Their Rc callback data has the queue and broker captures. The
pinned `func6798` at 0x15773f passes the captures to `func2181`; its queue-empty
wake calls `func4173` at 0x14031a. The resulting typed wake callback `func1921`
at 0x105e92 borrows ClientBroker Rc+8, whose data starts at Rc+12, and reads
the boxed context at data+56 and its vtable at data+60. Therefore the root slot
is broker Rc+72, not an arbitrary memory marker search.

Two independent normal-event closures converged on broker 1418256,
root slot 1418328 and root 1465912, with context type 1079724 and borrow count
zero. New documents and normal menu/result/new-match observations used this
path without a breakpoint. Runtime evidence: `root-chain-55539f7e8804.json`.

CONCLUSION: the production observer now follows typed live ownership only,
checking counts, borrow state and type markers each read. Broad diagnostic
root/reference scans are retired. Synthetic tests reject a stray root marker
without reading memory and reject fog/dirty-cache payloads. STATUS: PASS for
this bounded root-path experiment; cross-version support remains unavailable.

## QUESTION: which force data does the normal renderer reveal?

EVIDENCE: pinned tower stride 48, inbound Vec at +0 and outbound Vec at +12;
force stride 24, current reversed path at +4/+8, owner +12, Units +14, boost +21,
progress +22. Normal rendering uses inbound forces of visible towers and
outbound forces only when the destination is outside the current Visible refs.
The decoder follows that path, reads only the current leg, and exports endpoint
IDs only if they also belong to currently exported towers. Future routes and
fuel are not exported.

Pinned `Force::raw_tick` increments progress using `Force::speed`; remaining
leg duration derives from `Force::progress_required` at 0x11ccbd, including
boost's 4/5 threshold. ETA is a DERIVED nominal simulation duration, never an
arrival timestamp. Identity uses unique owner/visible-segment/composition and
tick/progress continuation. Pointers and vector indices are not identities;
ambiguous continuations remain UNKNOWN. First-seen is an observation time,
not launch time. Missing endpoints leave ETA UNKNOWN.

Two ten-minute research runs: 1,650 force-containing snapshots and 7,441 progress
changes in the first; 2,870 force-containing snapshots and 34,570 progress changes
in the second. The second had 1,114 derived tracks observed more than once and
up to 36 simultaneous visible forces. These measure tracking behavior, not
independent UI accuracy; the tracker itself uses the progress rule to match.

CONCLUSION: live visible-force extraction and conservative tracking are present.
Independent force-count/ETA/visibility verification is incomplete. STATUS: PARTIAL.

## QUESTION: does current production match the old public rule source?

EVIDENCE: it does not fully match. Tower byte +45 is a morale flag. The current
`Units::capacity` at 0x13d8d1 takes unit/type/morale, adding 10 to shield capacity
when morale is true. The normal UI states that a nearby ruler doubles production
and improves departing forces. In 15 selected visible towers the flag and UI note
agreed, including five SELF positives and ten NEUTRAL/other negatives.

Pinned `TowerType::raw_unit_capacity` at 0x9f412 and `unit_generation` at 0x9b841
were evaluated OFFLINE with only scalar branches and static WASM data loads.
No function of the live WASM was called. The checked-in version-bound tables
come from those evaluations. All 22 coherent capacity denominators in that
comparison agreed with base capacity plus observed morale. World tick code
at 0x1a683..0x1a69b halves generation intervals under morale, minimum one tick.
Delay +47 suppresses production and decreases by one per world tick. EMP can
also cause delay, so delay is not falsely labeled as an upgrade.

`Units::available` at 0xf9200 establishes Single count byte +1, unit enum byte +2,
shield byte +6; union padding is ignored. A self Village with bytes
`[1,1,9,0,0,0,15]` had 15/15 shields and the visible ruler icon/note. Tower units
now use the pinned Many/Single decoder. A visible self ruler proves current
life/location; absence never proves ruler death. Production facts describe
potential intervals, not guaranteed output at capacity or under unit priority.
Deployable currently means the verified mobile inventory from `Tower::force_units`;
it does not certify path/command legality. Upgrade state/resources remain UNKNOWN.

CONCLUSION: morale, capacity, potential generation, Single and visible ruler facts
are supported, with explicit remaining limits. STATUS: PARTIAL.

## QUESTION: can visible enemy/ally relation be queried legally?

EVIDENCE: current `Color::new` at 0x114ab0 passes World's player vector at root
+652/+656 to `World::have_alliance` at 0x13e89c. A player entry has stride 64;
alliance membership uses the exact hash/probe logic at 0x13f6b8/0xf5c41. Only
queries needed for the currently visible owner are performed; unrelated alliance
IDs and other player fields are never exported. A one-way request is not an ally.

The live panel colors for four SELF, five NEUTRAL and one ENEMY tower agreed;
the same run had 16 coherent unit-count comparisons, 16 matches. Bilateral
versus one-way membership and fog gates pass synthetic tests. No live ALLY case
has yet been verified. CONCLUSION: relations are DERIVED from the normal visible
color path; live ally coverage remains missing. STATUS: PARTIAL.

## QUESTION: do larger scenes sustain frequency and source-age bounds?

EVIDENCE: isolated headed rendering was about 10 Hz and rejected 1,151/3,000
reads while visibility was dirty. That ten-minute run accepted 1,849 snapshots,
3.081 Hz; extraction p95 10.44 ms and source-age upper p95 415 ms: FAIL.
An unmodified task-owned headless client rendered normally about every 8 ms.
Host wall-clock short steps differed from monotonic elapsed time by about 11 ms;
all canonical capture/first-seen/window timestamps now use host monotonic time.

Metadata-only source reads between world snapshots narrowed transition windows.
A 30-second run accepted 149 snapshots, 4.950 Hz; 148 had bounds and their upper
p95 was 235 ms. It is not acceptance evidence. The subsequent ten-minute run
`sampling-e390ca4881ef.json` accepted 2,870 snapshots in 600.086 seconds,
4.783 Hz; extraction p95 18.934 ms, 26,853 metadata reads and 2,868 bounded
snapshots. Upper source-age p95 was 266 ms: FAIL the 250 ms bound. This report
predated moving receipt time to completion of normalization; later reports
include that work. Exact authoritative source age remains UNKNOWN throughout.

No visibility losses/gains occurred in these two runs, so they do not satisfy
visibility-transition acceptance. No 1,000-sample stratified acceptance exists.
CONCLUSION: frequency improves, but freshness and full validation do not pass.
STATUS: PARTIAL.

## QUESTION: is the reconnect counter necessarily an authoritative source clock?

EVIDENCE: `lifecycle-research-e9f39abb1c72.json` and
`lifecycle-research-d9eb3b853e74.json` observed actual RESULT -> MENU -> official
JOINING -> IN_MATCH with the same player and root. Reload rejected the old observer
and created a new document epoch. Offline observations had a frozen tick and no
exportable identity. In the first ten seconds after reconnect, no queried WebSocket
was OPEN, yet the world sequence advanced. Periodic socket refresh alone did not
resolve it. The official client also supports WebTransport; a later query found
no live WebTransport objects and an open replacement WebSocket. This does not
prove which mechanism operated during that earlier interval.

World tick has callers in `ServerState::apply` and the large normal broker loop.
The second caller's source/target and buffering/prediction semantics still need
confirmation. Do not label the u16 sequence as authoritative milliseconds or
declare snapshot-age PASS from its transition bounds.

CONCLUSION: document/match boundaries improve; reconnect transport and exact
source-age authority remain unresolved. STATUS: UNKNOWN for that source-clock
question. This is the next highest-priority question, not a technical FAIL verdict.
