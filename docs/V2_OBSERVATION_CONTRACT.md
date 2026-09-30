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

## Required state

Match, snapshot sequence, clock/provenance, own identity; visible towers with owner,
relation, type, typed units, deployability, capacity, production, visible graph,
position and visibility; visible moving forces with identity/path/owner/typed units,
launch/ETA and provenance; king, upgrade resources/state, ranking, effects/aura/EMP.
Unavailable fields remain UNKNOWN. Readiness requires verified match/update identity,
graph, units and command-relevant fields; partial state cannot silently enter search.

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
