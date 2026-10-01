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
it does not certify path/command legality. At that checkpoint upgrade state/resources remained UNKNOWN; the later narrow sources below supersede that result.

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

FOLLOW-UP: a2d6821 resolves the transport ambiguity; see V2_M1_TICK_EVIDENCE.md.
The second tick caller is guarded by context u64==2 at 0xcd1e0..0xcd1e8 and
updates OfflineHarness's separate arena world. Network snapshots refuse tag 2.
HTTP fallback explains closed global WebSockets with advancing displayed state.
The observed sequence brackets normal network client-world application, not a
server generation timestamp. Exact source age remains UNKNOWN; conservative
client-application bounds and their coverage are reported separately.

## QUESTION: what are the player's upgrade resources?

EVIDENCE: public NonActor explicitly defines current-player active tower counts,
excluding upgrading towers. The pinned normal best-upgrade path func3492
(0x139d2c) passes context+592 to TowerType::has_prerequisites (0x1148c8), which
compares 27 u16 counts with TowerType::prerequisite (0xa7292). The latter is
evaluated only OFFLINE with whitelisted scalar instructions and static data.
Downgrade edges and nominal delays come from pinned static getter tables.
Only the player's aggregate counts are exported, never enemy aggregate fields
or hidden tower IDs. Own totals are not reconstructed from a partial viewport.

ui-comparison-7acdafd9b767: 13 selected towers, 22/22 coherent unit counts,
22/22 capacities, 13/13 visible relation colors. Eight prerequisite current
counts and eight requirements agree with the normal UI, including genuine 0/2
and 1/1 values. Unmapped translated labels are excluded, not silently guessed.
Single self Barracks [1,1,9,0,0,0,20] has the actual ruler and 20/20 shields.

CONCLUSION: upgrade_resources is OBSERVED typed active own-tower counts.
upgrade_candidates is DERIVED prerequisite presentation only; unlock status,
final command eligibility and cause of a delay remain UNKNOWN. Tower.upgrade
remains UNKNOWN. Meeting prerequisites never certifies a legal command.
STATUS: PARTIAL; this limited cohort does not establish 1,000-sample acceptance.

## QUESTION: can force motion be checked against independent normal execution?

EVIDENCE: v2_force_render_compare.py pauses only normal official execution; it
never invokes a WASM function. Speed entry 0x9896d and return 0x98b8e expose the
actual result local. Position entry 0x1036c0 and post-store 0x10375f expose the
official rendered Vec2. A typed, current legal snapshot is obtained before the
renderer borrows its broker. During the pause, comparison requires the same
document/player/world revision, active NETWORK mode, clear visibility cache,
both endpoints currently positive in Visible.refs, and unchanged matched force
owner/composition/progress/acceleration. The production borrow guard is unchanged.
Unmatched, hidden-endpoint, dirty or changed-revision cases are excluded.

force-render-comparison-c567fea66f9c: 20/20 normal-render speed reads match;
these early reads were not yet deduplicated and are reported as raw reads only.
force-render-comparison-c13b5b9fd217: 37/37 position reads, 30/30 unique force
world revisions match within 0.001 world coordinate. Maximum deviation was
0.000128992. Actual compositions included 9 soldiers, 12 soldiers and 5 tanks.
Unique keys conservatively collapse identical document/epoch/tick/current-leg/
composition/progress/acceleration records; pointers never become force IDs.
Rendering interpolation is used for position comparison only, never source age.

The initial dd8225caa135 attempt yielded zero comparisons because paused normal
rendering held an exclusive broker borrow. It is excluded, not a failed force
accuracy sample. This led to the pre-pause snapshot plus unchanged-state guard.
All debugger pauses are explicitly outside performance/freshness cohorts.

CONCLUSION: actual official force motion independently supports the pinned
derivation for these observed compositions. Mixed transport, complete force
composition, stable identity, launch time and full coverage are not established.
STATUS: PARTIAL.

## QUESTION: do rotating independent UI checks reach a useful scale?

EVIDENCE: ui-comparison-95dc42f35a60 performed 717 ordinary tower selections
over 50 rounds. Same-point mouse down/up opens information only; no dragging,
upgrading or tactical command is sent. DOM reads are bracketed by matching
selected tower and unchanged units/type/owner/relation/morale/delay. Own resource
checks additionally require unchanged own totals. World revision keys prevent
duplicate field counting. Unit fields: SELF:SINGLE 50/50, SELF:MANY 450/450,
NEUTRAL:MANY 331/331, ENEMY:MANY 400/400. Total 1,231/1,231. Separately,
capacities 1,231/1,231, colors 717/717, own prerequisite counts 400/400,
prerequisite requirements 400/400. Later world revisions are fresh DOM checks
even when a count remains at capacity; they do not add new entity types.

CONCLUSION: scaled independent tower-field comparisons agree. This is 717
entity selections, not 1,231 complete states. Ally was absent; force, visibility
and match-transition strata still require their own evidence. STATUS: PARTIAL.

## QUESTION: can official normal getters independently check force composition?

EVIDENCE: during a previously validated, currently visible Force::speed invocation,
the read-only tool stops at Units::available return 0xf92c2. Unit enum is local
$var1 and actual returned count is local $var3. It resumes through the same
normal speed invocation until return 0x98b8e; no live WASM call is injected.
Actual breakpoint locations must equal the requested pinned instruction offsets.
Later probes also check that each getter remains nested inside Force::speed.

a9d60c91270f: 30 distinct world revisions of a currently visible five-tank force,
30 complete ten-unit vectors, 300/300 independently returned count fields agree.
No duplicate force world revisions occurred in this cohort. This proves the
observed Many composition, including actual zeros; it does not prove all Many/
Single force cases. A follow-up soldier filter initially produced zero cases;
entry re-arming favored the first rendered tank force. The tool now preselects a
visible target and seeks within the same frame before comparing any outcomes.

CONCLUSION: actual official normal getter results can independently validate
composition for legal visible forces. STATUS: PARTIAL, further strata pending.

## QUESTION: is non-owned deployable inventory unknown or a known zero?

EVIDENCE: pinned normal drag rendering at 0xd9d53..0xd9d66 rejects zero owner
or an owner different from ClientCore.player_id before Tower::force_units at
0xd9d70. Public ordinary manual drag has the same source ownership restriction.
The pinned mobile-inventory getter remains separate from route legality.

CONCLUSION: with a positive observed player ID, a currently observed neutral,
enemy or ally tower permits zero units belonging to this player's source action.
Unknown/missing player identity remains UNKNOWN. Own source stock uses the pinned
getter. Delay does not arbitrarily zero existing units; route validity, ranged
distance and command timing remain separate unresolved eligibility checks.
STATUS: PASS for source ownership distinction; full deployable-route semantics PARTIAL.

## QUESTION: can own persistent upgrade resources be distinguished from unknown?

EVIDENCE: pinned UI props builders at 0xd6991/0xd699a and 0xd776a/0xd7771
clone own Unlocks at root+46240. Unlocks::clone (0x14d9db) copies keys+32 and
clones the byte-enum set. Contains (0xec716) addresses keys at ctrl-(slot+1);
normal full slots have control byte <128. The adapter validates bounded power-of-two
capacity, set count, enum range and uniqueness, and does not read random hash seeds.
Live 412e589d030d observed keys=3 and an empty owned unlock set. Synthetic privacy
checks distinguish known zero/empty from invalid storage and count disagreement.

CONCLUSION: own persistent keys and unlocked types are OBSERVED resources. They
are separate from ad/rank-dependent effective lock policy and final command legality.
Zero Tower.delay proves no active delay-based upgrade, while nonzero delay remains
UNKNOWN in cause because EMP can produce it. STATUS: PASS for these narrow sources.

## QUESTION: can a visible upgrade cause be tracked without conflating EMP?

EVIDENCE: pinned Chunk::apply_0 0x7d4de writes the new type+46, calls
TowerType::delay at 0x7d4e5, and writes nominal delay+47 at 0x7d4e8. Generation
sets delay=0 (0x7d609); neutral decay/capture walk downgrade types; the normal
EMP branch writes max(existing,240) at 0x1b10c and does not change type.
Tracker requires a direct upgrade transition across one observed revision, a
positive unchanged owner, prior zero delay and new nominal delay. Only consecutive
matching countdowns retain the cause. Visibility, missed revisions, ownership,
identity, clock gap and abnormal delay invalidate it. It never reads actor inputs.

Offline reprocessing of three original legal capture files (79047ae0c5ea) found
15 starts and retained 2,868 delay facts; 333 remain unknown. These are not new
live independent comparisons. Live a84933df9cb7 captured Village(26) to
Headquarters(11), start tick 15472. Across 52 coherent normal info-panel reads,
the direct child progress bar's actual width matched (1-delay/nominal)*100,
within 0.00002 percentage points. A Reactor cohort (32f3180246b6) had 29/29
progress comparisons with unknown initial cause, which remains unknown.

CONCLUSION: observed type transition plus exact countdown provides a conservative
DERIVED active-upgrade fact. A progress bar by itself proves delay visualization,
not cause. STATUS: PASS for these demonstrated transitions, full effects coverage PARTIAL.

Further independent normal Force::speed nested getter cohorts: 9ac718c8fdb9
contains 30 distinct twelve-soldier vectors, 300/300 getter fields; 06d675aad308
contains 30 distinct four-bomber vectors, 300/300. No injected live WASM call,
no hidden endpoint reads, and no debugger samples in performance cohorts.

## QUESTION: can Units::available's argument address identify its original force?

The failed direct-getter cohorts 83d3f2a9f42b and 356d561ee6e5 supply zero
independent cases. Static pinned evidence resolves the pointer hypothesis:
Force::speed directly queries enum 2 at 0x98987, then (when zero) builds
Units::iter_with_zeros at 0x98998. That iterator explicitly calls Units::clone
at 0x14e72c, storing a copy at its result+8. Its getter adapter func5444 calls
Units::available at 0x14e782 using that cloned iterator object. Thus those getter
arguments are not the original force+14 address. Subtracting 14 cannot identify
the force. The unrelated direct call at 0xcd9bf is a tower-production loop,
not a force-render identity certificate.

CONCLUSION / STATUS: FAIL for the address-identification hypothesis. Retired
the unvalidated direct-getter mode; retain the validated units mode, which first
captures a legal Force::speed invocation and observes nested getter returns
only inside that invocation. No claim of new live Single coverage follows from
this static proof. d4a9b156ae26 independently verifies ten distinct source ticks
with two/four choppers, ten complete vectors and 100/100 getter fields.
