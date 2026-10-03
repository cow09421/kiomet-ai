# Independent decision harness: goal-006 DEV scope

This is a generated development capability experiment, not a Planner comparison,
current-game validation, or Final-V/Final-L cycle. The frozen goal-006 contract
is in PREREG.jsonl. Source support is bound by LEDGER.jsonl and its commits.

The independently written tools evaluator does not import the production
Planner, v2 simulator transitions, or their predictive parameters. Its policy
interface contains detached immutable current visible towers, visible forces,
current tick, player, and a complete current visible legal deployment menu plus
WAIT. `start_tick` is the first next world update; the initial visible snapshot
has tick `(start_tick - 1) mod 65536`. The public world increments its tick
before processing towers/forces, then applies the chosen normal input. Scenario identity, stratum, reference outcomes, future opponent scripts,
and evaluator-only metadata are excluded. Future opponent intentions are latent
evaluation inputs and cannot change the initial policy view.

The support envelope is one closed generated chunk, exactly 120 logical ticks
(30 seconds at the public 4 Hz clock), public direct roads, no supply line,
Shield plus Soldier or Ruler, and explicitly supported tower types. Typed
ten-slot inventories retain their units; unsupported actors, unknown fields,
invalid Single/Many combinations, and unsupported possible interactions must
be rejected before evaluation. Choice alternatives cannot be removed to avoid
an unsupported transition. Normal deployments move all current mobile units.

Pinned reference: public SoftbearStudios/kiomet commit
`d3f0956f27f48f6cac9ac9991f948fa7f90ba77c`, plus the pinned Kodiak tick definition.
TowerType enum-wide attributes establish Ruler capacity 1 and Shield generation
every five seconds; Projector overrides Shield generation to three seconds and
has raw Shield capacity 10. Owned arrival overflow and current Ruler Shield
boost are separate from ordinary generation capacity. Soldier Many and Ruler
Single cannot coexist. Adding Ruler replaces Many; adding Soldier to Single
adds none.

Restricted combat is independently computed from public ordered-prefix
casualties, with attacking Shield removed only against towers. Opposite-edge
force combat retains Shield, skips same-owner forces, and uses the exact
source interval-overlap condition. Only a surviving non-Shield force wins a
force fight. A public LostRuler event becomes terminal at the following service
boundary; capturing an evacuated tower is not itself Ruler death. Unsupported
multiple collision ordering must reject the entire affected case.

Source reconciliation with deployed client `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`
is unproven. These static-source generated witnesses cannot certify its current
physics, a real action effect, baseline superiority, or the required representative
Final distribution. No old 45 Capture / 31 Combat corpus, live sessions, passive
recordings, or Final outcome exposure is used.

The two witnesses in each mandatory S1-S6 stratum and independent hand references
must be committed before the first outcome-bearing run. The evaluation freeze
and receipt bind exact code, fixture, source hashes, clean commit, environment,
commands, log hash, and result. Results remain pending until that run.
