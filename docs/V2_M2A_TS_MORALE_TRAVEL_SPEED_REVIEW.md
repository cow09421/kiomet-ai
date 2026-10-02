# Soldier travel speed and morale

## Finding and scope

For a caller-qualified manual `DeployForce` from an own tower with a known
morale byte, the pinned source separates the force's progress increment from
morale's acceleration effect. `Force::speed` derives the per-tick progress
increment from the force composition. `Force::raw_tick` adds that value to
the current progress byte. `Force::progress_required` separately reads
Force+21: when it is `1`, it lowers the current segment's progress threshold
according to the accelerated branch. `Tower::deploy_force` copies the source
tower byte at +45 into Force+21. Thus, for a known-morale-true own manual
launch, acceleration on the initial segment is predictable from the
before-state; morale does not itself change `Force::speed`.

The launch-lineage audit establishes that a normal manual `DeployForce`
starts with progress 0 and fuel 150 and takes the current deployable inventory
from `Tower::force_units`. With only four Soldiers in the eligible ordinary
composition, the composition-derived movement class is Soldier's normal
speed (2); morale true controls the accelerated progress threshold. This is
an initial-segment source result, not a prediction of arrival time or later
position.

## Source basis

- `docs/V2_M2A_LAUNCH_RULE.md` records the manual command lineage, source
  Tower+45 to Force+21 copy, initial progress/fuel, and all-deployables
  inventory construction.
- `Force::speed` (`runtime/research/v2/Force__speed.txt`, function 690) reads
  the Force unit counts and composes the movement speed from unit classes; it
  does not read Force+21 or Tower morale.
- `Force::raw_tick` (`runtime/research/v2/Force__raw_tick.txt`, function
  1845) adds `Force::speed` to Force+22 progress before evaluating the
  threshold.
- `Force::progress_required`
  (`runtime/research/v2/Force__progress_required.txt`, function 2689) reads
  Force+21 at `0x11ccf0..0x11ccf8` and uses the accelerated branch only for
  that threshold calculation.
- `docs/FORCE_UNITS_SOURCE_SEMANTICS.md` identifies Soldier as normal speed
  and Tank as slow speed.

## Remaining unknowns and limits

The source result applies only when the action is already identified as a
manual `DeployForce`; it does not identify arbitrary UI drags or automatic
dispatch. Future route continuation through supply lines, remaining route,
arrival timing across later segments, and fuel consumption remain unknown.
The certified before-state does not reveal hidden actors or future route
changes. No after-fit inference, live observation, core change, guard change,
or formal/empirical event is added.
