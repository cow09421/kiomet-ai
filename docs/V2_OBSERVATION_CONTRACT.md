# M0 Observation Contract v2

This contract supersedes v1's blanket ban on structured client observation, as
explicitly authorized by the 2026-09-30 restart instruction. It does not relax fog
or private-information restrictions.

## Allowed boundary

Read-only structured observation of the unmodified official Kiomet client:
DOM, JavaScript structures, WASM memory and client structures representing facts
the ordinary player is entitled to know now. Public source is layout/semantic
reference only; it is not proof that a production field is player-visible.

Every exported entity needs positive visibility evidence from the client's current
visibility/presentation path. Merely existing in memory, being downloaded, being
owned by an opponent, or having been visible earlier is insufficient. Do not
export hidden neighboring identifiers via roads or force paths. Last-known facts
belong in a future belief layer, never in current observed state.

Every important field is OBSERVED, DERIVED or UNKNOWN, with source and sample
time. Unknown uses `None` plus UNKNOWN, never fabricated zero/neutral/empty.
An observed empty collection is distinct from an unavailable collection.
Derived capacity/production/ETA/deployability require explicitly validated rules;
no derivation by total-unit subtraction or undocumented offsets.

## Coherence and freshness

Take all memory reads synchronously in a single page task. Reacquire memory views
after growth; validate every pointer/count/tag. Do not persist pointers across
frames, reloads or matches. Pin each production adapter to a client SHA-256 and
verified layout. Unknown version or visibility layout yields no decision-ready
state. No live-debugger pauses count as normal observation samples.

Identity combines browser session, document generation and actual match lifecycle;
do not substitute a timestamp for verified lifecycle transitions. Sequence numbers
increase only for accepted snapshots. Client observation time, last confirmed game
update time and host receipt time are distinct. Polling repeatedly must not refresh
unchanged/stalled authoritative data. Report update age as UNKNOWN when unavailable.

Snapshot capture, source windows, fact observation and first-seen times use
`host_monotonic_ms`. Browser epoch milliseconds remain a separate fact. Host
wall time is excluded from age arithmetic: measured Windows wall-clock steps
can differ from elapsed time by about 11 ms over short reads. State receipt is
when normalization/tracking completes, so downstream age includes that work.

The production root locator follows pinned normal-event closure ownership:
JS closure state -> event Rc capture -> ClientBroker Rc -> boxed context. It
validates live counts, borrow state and type markers on every read; it does not
scan game memory for a marker. Document reload reacquires all object handles.

The pinned `World.Singleton.tick` is a u16 world sequence, not a timestamp and
not a match identifier. Its OBSERVED numeric value does not certify every M1
semantic/visibility case. The exact `updated_at_ms` remains UNKNOWN without a
real point-time source. Consecutive reads that observe a sequence transition may
produce a DERIVED `source_update_window_ms = (previous_read_start, current_read_finish)`.
This interval contains the client world application; server generation and
transport delay are outside its scope. It is not the update's exact time. Report
`age_bounds_ms` and their conservative upper percentile separately. No assumed
250 ms period or interpolation clock may shrink that uncertainty. A stalled
sequence ages its existing window. Document/match/clock discontinuity invalidates
the window; a first sample cannot claim known source age.
An application-age bound alone cannot clear canonical decision readiness's
freshness requirement while authoritative update time remains UNKNOWN.
Host read endpoints use floor-quantized integer milliseconds. The stored window
contains the application's integer-clock time; continuous elapsed-age bounds
expand each end by 1 ms to cover endpoint quantization. An old reported upper
percentile of 250 ms becomes a conservative 251 ms, not a threshold pass.

Reject current world payload while the official visibility cache is pending, while
the official active-state condition is false, or while expanded visibility is
enabled. Metadata-only lifecycle observation may continue; it exports no tower or
force payload. A derived match epoch combines document identity, player identity,
official join boundaries and observed menu/result transitions. An unobserved gap
that could conceal a match transition makes identity UNKNOWN. Pointers never form
canonical entity identity.

Connection authority follows the pinned ClientSession's owned transport Vec and
typed WS/WT/HTTP state getters, matching its primary-selection state=1 condition.
Any global OPEN WebSocket is insufficient: old objects can remain reachable and
the official session can switch to HTTP polling. Transport tag=2 is OfflineHarness;
reject it before world payload access and record NETWORK/OFFLINE source_mode.
An online state alone does not establish freshness; stalled sequences retain old
age bounds. Network event timing is diagnostic and never a source timestamp.

## Required state

Match, snapshot sequence, clock/provenance, own identity; visible towers with owner,
relation, type, typed units, deployability, capacity, production, visible graph,
position and visibility; visible moving forces with identity/path/owner/typed units,
launch/ETA and provenance; king, upgrade resources/state, ranking, effects/aura/EMP.
Own currently visible upgrade_locks may be DERIVED from the pinned normal UI
ad/rank/level/permanent-unlock predicate, including its optional basis downgrade.
Claims-backed rank remains UNKNOWN without reading account claims. A proven false
AND term may resolve an unlocked flag; unresolved targets stay UNKNOWN. UI lock,
prerequisite satisfaction and final command eligibility are separate facts.
Unavailable fields remain UNKNOWN. Readiness requires verified match/update identity,
graph, units and command-relevant fields; partial state cannot silently enter search.
PLAYER_VISIBLE_COMPLETE is a derived entity-coverage certificate: every current
positive sensor slot has a decoded generated actor under the normal active,
connected, non-expanded visibility gates. A missing slot remains PARTIAL. This
certificate covers the player's visible set, not hidden actors or the whole world;
it does not certify unknown field values, age or general decision readiness.

## Input isolation and verification

No physical mouse movement, keyboard capture, SendInput, PyAutoGUI, pynput,
SwitchDesktop, packet injection or heap mutation. Official UI page-local events are
the production path. Research never dispatches semantic WASM commands as execution.
Lifecycle evidence later distinguishes PROPOSED, DISPATCHED, CLIENT_ACCEPTED,
FORCE_OBSERVED, ARRIVED, EFFECT_CONFIRMED, FAILED and UNKNOWN. A source quantity
change alone never proves acceptance or movement.

## M1 evidence

Only real independent live matches and independent UI/visibility comparisons count.
Target: three 10-minute matches, >=4Hz and p95 update age <=250ms; >=1,000 stratified
critical-field comparisons >=99% agreement; zero hidden-info contamination.
Offline fixtures and adapter unit tests verify contracts only. No PASS without the
complete live evidence. Stop at 18 engineering hours / three working days if unmet.
