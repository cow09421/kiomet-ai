# Bounded normal-UI input capture — pending user authorization

Purpose: record command inputs before a real transition, instead of reconstructing
opponent launches from the after-state. No Search or persistent Live Agent.

Maximum: two fresh ordinary official-client matches. Per match, at most one initial
Ruler relocation and six ordinary-unit reinforcement/exploration commands.

Every command must use the ordinary UI, a positively visible own source, a known
adjacent destination, and explicitly recorded units. Destinations are restricted
to own towers or observed empty neutral towers. No enemy or allied destination,
upgrade, supply-line configuration, special weapon, packet injection, direct
semantic WASM call, or actor heap write. Lack of a legal candidate ends that run.

The initial Ruler move is proposed because an initial HQ containing its Ruler
cannot produce the ordinary mobile inventory needed for reinforcement tests.
Ruler movement/capture remains unsupported where aura or ownership rules are
unverified: recording such an event does not earn simulator accuracy credit.

Before input: save canonical snapshot identity, positive visibility, current
owner/type/units/neighbors, camera projection, selected UI evidence, intended
path and units, client SHA and host monotonic timing. Recheck identity and
legality immediately before releasing the ordinary UI gesture.

After input: retain every raw accepted snapshot, lifecycle/transport metadata,
normal UI result, and command timing. Do not infer exact server application tick
from the local click time. Establish force lineage conservatively; ambiguity,
unrecorded input, fog, unknown fuel/path, or unsupported mechanics stays unknown.

Validation: uninterrupted five-second rollouts; compare every complete visible
intermediate state; preserve all exclusions and failures. Known prior commands
may provide scenario inputs only after their own independently recorded before
intent and unambiguous acceptance/lineage checks. After-inferred commands remain
calibration-only. No lowering of any M2 gate.

This plan is not permission to send commands. The previous M1-stage request
explicitly said “不要自動派兵 / 不要自動攻擊”. Await an explicit answer about the
bounded M2 tests above before executing any troop gesture.
