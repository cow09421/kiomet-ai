# M2A optional presence and capture review

STATUS: accepted bounded contracts and candidate semantics; M2 IN_PROGRESS.
Pinned client SHA:
fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.

## Decisions

ACCEPT: own-only optional supply-line presence, missing-value UNKNOWN semantics,
OBSERVED provenance enforcement and exact positive-integer identity checks.
Independent review found bool/int alias acceptance; Luna repaired canonical,
compact-state and normalizer boundaries. Root reviewed those diffs and ran the
four new focused test files: 46 passed. Live independent positive-line Boolean
accuracy remains unestablished. Malformed Some vector-shape evidence is incomplete;
no private path reads are added to characterize it.

ACCEPT: capture replaces stale tower relation. Current-player capture predicts
SELF, zero-owner NEUTRAL, foreign capture uses valid arriving ALLY/ENEMY relation
or UNKNOWN. The independent reviewer exercised actual step captures and confirmed
that default-off combat guards remain. This is state coherence, not combat PASS.

ACCEPT WITH SCOPE: current canonical pipeline preserves each visible destination's
inbound vector order. Adapter vector index enumeration, ForceTracker row retention,
canonical append order and step enumeration agree. Pinned World::tick_before_inputs
0x1a975..0x1a9eb uses ascending queue index and stable compaction; raw_tick call is
0x1a9ae. Root sampled that excerpt. Do not sort by tracker ID, owner, source or ETA.
Order between different destination towers is not proven by this evidence.

ACCEPT WITH SCOPE: neutral initialization at Chunk::apply_0 0x7d5e4..0x7d5ef
stores i64 -9223372036854775808 at tower+20; little-endian upper u32 gives the
Tower+24 None sentinel. Root inspected that initialization. Owner setter
0x13b009 preserves it on old-owner-zero transfer and clears it on nonzero-owner
transfer. Combined construction/setter evidence supports absent-line prediction
for the guarded pinned capture path; the old-owner clear branch alone was
insufficient evidence. It is static pinned-client evidence, not live verification.

## Comparison and remaining limits

The comparison now includes tower capacity/production/graph/position/relation,
force acceleration/relation and per-destination inbound order, alongside existing
inventory/owner/type/delay/morale/world sequence/ruler fields and known optional
presence. A swapped same-destination queue must fail despite equal multisets.
Terminal route, fuel, observation provenance and tracker IDs are not compared as
observable compact-state facts. Historical signatures omitted this context;
old signatures remain historical. Current extended-contract replay is admitted
in V2_M2A_MANAGER_VALIDATION.json: formal 1052/1052, ground candidate 1054/1054,
ordinary candidate 593/594; all static-output counts zero, original mismatch
retained. These limited results do not establish full combat accuracy.

Ground and ordinary combat remain default-off hypotheses. Dynamic aura, ruler
death/elimination, uncertain continuation/fuel, special weapons and unrecorded
actions remain refused. The 785 cohort's 202 event candidates are independently
scenario-ineligible; no admission based on after-state agreement.

The hover research tool has offline syntax verification only for its latest
revision. Its latest live execution did not run because automatic approval review
hit a usage limit. No alternate-agent/tool workaround was attempted. Older four
negative screenshots provide context only and do not establish a positive-line
case or independent accuracy credit. No troop gestures have been sent.
