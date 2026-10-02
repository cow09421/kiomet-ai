# Shield-retaining ordinary ground defense: pinned review

Status: bounded static rule review only. This does not enable the full combat
model or award trajectory/formal-validation credit.

Pinned client SHA-256: `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`.

## Scope and rule

For a known ordinary ground-only fight with no Ruler, special unit, Air unit,
or exogenous effect, let the arriving force contain `T` Tanks and `S`
Soldiers. Let `A = min(3, (T + S) // 2)` only when attacker morale is true and
defender morale is false; otherwise `A = 0`. Let `D = min(3,
defender_nonshield_ordinary // 2)` only when defender morale is true and
attacker morale is false; otherwise `D = 0`. The pinned initial signed score
is `+A - D`. For the retention guard, define the conservative bound
`B = 3*T + S + min(3, (T + S) // 2)`, regardless of the current morale flags.
When the incoming force is eliminated and a defender Tank or Soldier survives,
the number of defender Shields lost is

```text
max(0, 3*T + S + A - D)
```

This rule is limited to cases where defender Shield count is strictly greater
than `B`, so a Shield remains throughout, and the destination began with a
non-Shield ordinary unit so `Units::is_alive` recognizes the defender. The
destination Tower ID must be nonzero. The helper accepts fixed ten-byte unit
vectors with counts in 0..255. Its inputs are the current arrays at the start
of ordinary fight processing, after any earlier tower/tick work; this proof
does not infer or model capacity/reconciliation behavior. The defender's
type, owner, morale, and tower context remain fixed during the transition.
The arriving force contains only Tank/Soldier counts and is fully eliminated
by the end of combat.

## Pinned dataflow

The combat scratch setup stores the arriving-side `var11` pointer at
`scratch+388` and the defender-side `var13` pointer at `scratch+396`
(`0x1ac56..0x1ac64`). The `Units::reconcile` call at `0x1ac24..0x1ac3b` is in
the empty-defender transfer/capture path, not a universal pre-fight step; it
is not reached for this nonempty defending array. The ordinary caller runs its
Air selector before Surface (`0x1ad78..0x1ad88`,
`0x1ad8c..0x1ad94`; see also `V2_M2A_COMBAT_CALLER.md`). The pinned ordinary
field table marks Tank/Soldier as Surface participants and Shield as eligible
on Surface; this scoped fight has no Air participant.

`Units::iter_with_zeros` initializes its cursor to zero (`0x14e724..0x14e736`).
`UnitIter::next` calls the bounded enum iterator with limit 10
(`0x13b9f9..0x13ba01`); the iterator increments its cursor by one and stops at
the limit (`0x156846..0x156879`). The vendored enum labels the corresponding
indices Shield=0, Tank=4, Soldier=5; those labels are used only to name the
numeric entries, while behavior here is taken from the pinned WASM. Thus a
present, unheld Shield is selected before defender Tanks or Soldiers.

The signed damage accumulator is initialized once from the morale branch
(`0x1accc..0x1ad06`) and is carried through both field loops; each
`func2022` result is added to the same value at `0x1af48..0x1af4b`. The morale
cap is independently recorded in `V2_M2A_MORALE_CORRECTION.json`:
`min(3, count // 2)`, excluding Shield and single-use units.

The selector's sign chooses which side supplies the next combatant. For a
positive score, the caller selects from defender units at `scratch+396`
(`0x1aec4..0x1aee9`); for a negative score, it selects from arriving units at
`scratch+388` (`0x1adf8..0x1ae20`). At zero it queries both sides. `func2022`
uses the arriving array at `scratch+388` as its sign reference
(`0x1ad18..0x1ad24`); its pointer comparison selects `+1` when the selected
unit belongs to that array and `-1` otherwise (`0x109244..0x10925c`). Pinned
scalar damage is Shield=1, Tank=3, Soldier=1 (`Unit::damage`,
`0x126c57..0x126caa`; scalar table in `V2_M2A_ORDINARY_RULES.json`). A
defender Shield therefore reduces a positive score by one, while each selected
attacking Tank/Soldier contributes its pinned damage value.

Ordinary casualty handling is deferred: `func1347` removes the prior held
ordinary unit before recording the newly selected one
(`0xe4790..0xe47eb`). The final selector phase orders the defender first when
an unused defender unit exists (`0x1af53..0x1af8e`). A selected Shield reduces
the score by one and deferred consumption removes the prior held Shield; the
arriving side's final sentinel-10 consume removes its last held Tank/Soldier
(`0x1b01c..0x1b03c`, `0x1b082..0x1b0a2`). Since the before-count is strictly
greater than `B`, the available Shield count cannot reach zero during this
bounded sequence, so selection does not advance to defender Tank/Soldier.
Each positive point after the morale offset accounts for one Shield loss,
yielding `max(0, 3*T + S + A - D)` while at least one Shield remains.

## Defender survival and ownership boundary

For this narrow case, no tower ownership change occurs in the pinned
post-combat path. The attacker array is empty and the defender has an ordinary
Tank or Soldier, so the attacker's `Units::is_alive` is false and the
defender's is true (`0x1afe3..0x1aff3`; implementation
`0x1048e5..0x10495c`). The scratch byte compared with 27 by the final guard is
set to 27 at `0x1ac4c..0x1ac50`; it is not destination TowerType. Therefore
`var4` is zero at `0x1aff9..0x1b00b`, and `eqz(var4)` branches directly to
combat result 1 at `0x1b00f..0x1b012`. The later sign-based status selection at
`0x1b0e4..0x1b0ee` is bypassed. Result 1 branches to the end of the combat
outcome block at `0x1b14f..0x1b154`, before the owner setter
(`0x1b21d..0x1b223`). The earlier empty-defender transfer path containing a
setter (`0x1abaf..0x1ac24`) is not taken because the defender array is
nonempty. Therefore the defender remains owner.

The later world postlude can call `Units::add_units_to_tower` at
`0x1b43e..0x1b45b`; after the stated elimination, its arriving array is all
zero and the implementation skips each zero count (`0x10ea5a..0x10ea95`). No
defender Tank/Soldier is selected while a Shield remains, and the postlude
adds no units from the empty arriving array, so those defender counts remain
unchanged under these preconditions.

## Illustrative expectations and limits

The rule gives a one-Shield loss for four arriving Soldiers against a defender
with 20 Shields and 12 Soldiers when defender morale alone is active, and a
three-Shield loss for two arriving Tanks against the same defense and morale.
These are illustrative arithmetic expectations only, not independent evidence
or fitted validation cases.

This review excludes Air IDs 1–3, single-use/special IDs 6–8, Ruler ID 9,
attacker Shield, tower destruction, attacker survival, and any state where a
Shield is depleted. It does not prove from visible before-state alone that
the pinned combat pair and current morale flags are the ones selected for a
particular world tick; cached King aura refresh timing and intervening world
effects remain separate gates. It also does not establish unrestricted
combat, attacker-winning capture, post-capture production/capacity, or
complete-world simulation eligibility. Full-fight winner/capture logic
remains a separate unknown and the ordinary combat model remains default-off.

## Integration and acceptance

Root and an independent Luna accepted the bounded selector, deferred-consumption,
conditional morale and result-1 owner-preservation proof. The implementation uses
the stronger conservative B guard above. It is exposed only by
`Scenario(shield_retaining_combat=True)`, appended after existing scenario fields
to preserve their positional order. The caller additionally restricts exact
positive owner/id and integer Tower kinds 0..26. Neutral/Ruins targets remain
outside this implementation. The existing enemy-relation and whole-world gates
remain; the narrow flag never falls back to either broader combat model even
when other flags are set. A fully defeated arriving force needs no future path
or fuel because it is removed on the proved defender-survival branch.

The two retained development worlds match the prior local expectations under
the new isolated rule. They remain development evidence, without external-action
isolation or expanded formal credit. Root ran all v2 Python regressions: 293
passed, 1363 deselected. The initial full run had one setup error because the
selected basetemp parent directory did not exist; creating that workspace-local
parent and rerunning the full suite produced the successful result. No simulator
failure was hidden or counted as a passing formal transition. Default normal,
ground and ordinary combat remain disabled; M2 is not complete.
