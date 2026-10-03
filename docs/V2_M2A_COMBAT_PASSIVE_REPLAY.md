# M2A Passive Combat Replay

The passive replay applies the frozen `fight_ordinary` candidate to all 31 `COMBAT_REQUIRED` current-leg boundary cases. The combat source hash matched the pinned value before scoring; no formula tuning or production promotion occurred.

**Verdict: PARTIAL** — 4 locally evaluable cases, 4/4 exact arrival projections (100.0%). The support bar is at least 20 evaluable cases and at least 90% exact agreement; the next evidence step is controlled evidence because the clean sample is below 10.

## Frozen inputs and population

- Formula: `src/kiomet_ai/v2/sim/combat.py` SHA256 `8b84726349cc52d718dc8f4fbc42416067ae2df9924cefbe88e899cd8d0edfd3`.
- Attacker morale: retained `force.accelerated` (unique pinned known-leg ETA inversion only when the visible flag is absent). Source tower morale is supplementary and is never substituted.
- Population: 31 unique raw cases (22 development, 9 holdout). The four prior ground/air corpus rows add 0 unique cases after deduplication; union = 31.
- Timeline: `before=t`, `arrival=t+1`, `following=t+2`, with matching source hash, scope, and consecutive ticks checked for every case.

## Raw formula outcomes

- All 31/31 candidates had sufficient ordinary fight inputs and produced a frozen formula result.
- Predicted owner matched the observed arrival owner in 31/31 cases.
- Surviving vector matched the observed arrival tower vector in 26/31 cases; full owner-plus-vector projection matched in 26/31.
- At the following snapshot, the t+1 projection still agreed in 24/31 cases. This is an observed follow-up comparison, not a t+2 combat forecast.
- Strict local evaluability: 4/31; 4/4 exact arrival projections in that subset.
- Five raw vector mismatches all retained correct owner predictions. In those cases the observed tower inventory was zero while a new-leg-compatible force was visible; force genealogy remains ambiguous.

## Contamination and force continuity

- Production due at the combat input tick: {False: 31}.
- Aura input uncertainty: {False: 31}.
- Multiple inbound context: {None: 24, False: 7}.
- Hostile pair relation: {'UNKNOWN_PAIR_RELATION': 9, 'KNOWN_HOSTILE': 22}.
- Special vectors: {False: 31}.
- Active delay, capacity uncertainty, and timeline continuity: {False: 31}, {False: 31}, {False: 31}.
- Force status at arrival/t+1: {'AMBIGUOUS': 26, 'DISAPPEARED': 5}; at following/t+2: {'AMBIGUOUS': 26, 'DISAPPEARED': 5}. Ambiguous new-leg cases do not prove physical genealogy or permanent consumption.
- Continuation uncertain in 26/31 cases; status bases at t+1: {'NEW_LEG_COMPATIBLE_OWNER_AND_SURVIVOR_VECTOR': 5, 'UNRESOLVED_FORCE_ENDPOINT_OR_VECTOR_ALIAS': 21, 'COMPLETE_CENSUS_ORIGINAL_ROUTE_SIGNATURE_ABSENT': 5}.

## Separate legacy candidates

| Cohort / tick / target | Event | Prior transition match | Dedup result | Combat projection |
|---|---|---:|---|---|
| daf86d0544b7, 23737, 17301775 | ground_combat_arrival | True | duplicate: daf86d0544b7:63:0 | SCORED / owner True / vector True |
| daf86d0544b7, 24586, 17301775 | ordinary_air_unit_combat_arrival | True | duplicate: daf86d0544b7:912:0 | SCORED / owner True / vector True |
| 7d56a775bc4c, 46518, 17760516 | ground_combat_arrival | True | duplicate: 7d56a775bc4c:572:0 | SCORED / owner True / vector True |
| 7d56a775bc4c, 46520, 17760518 | ordinary_air_unit_combat_arrival | False | duplicate: 7d56a775bc4c:574:0 | SCORED / owner True / vector True |

## Full pinned raw-file manifest

The six raw files below are inherited from the unfiltered settlement receipt. Every scored row maps to one of the three listed relevant files; all six expected and actual hashes in the pinned receipt match.

| Cohort file | SHA256 | Manifest match |
|---|---|---|
| `runtime/research/v2/snapshots-03d032d57e5b.jsonl` | `a235af084be0cfa7279023a7b25c72840f946828ede4f89a0779bcbc1ac5e1c9` | True |
| `runtime/research/v2/snapshots-7d56a775bc4c.jsonl` | `6ce53f98c943ada9cd9d6317002f8ec833c33b5c3a3aad5feda8bdb5922a0929` | True |
| `runtime/research/v2/snapshots-85391858b5d8.jsonl` | `84ffabba28f1ce370cabf40988f5c78b753ea737845ffe2065d0d34d2ae43cb1` | True |
| `runtime/research/v2/snapshots-b1f7f9416e92.jsonl` | `d50a936e051ebf788d63b34f37e088642884567a00777708a55aac48bd618937` | True |
| `runtime/research/v2/snapshots-daf86d0544b7.jsonl` | `2bd8f553f205a608f8c47b4816ef67541b27fa393e1c0ba17bd9dd4ebccea144` | True |
| `runtime/research/v2/snapshots-fe678ebb30ce.jsonl` | `58f58292e37727388942bd1e0fd67a00ddcd669511f555542cafa39ef8c3d92b` | True |

## Case results

| Case | Split | Winner | Owner match | Vector match | Evaluable | Main blocker | t+1 force | t+2 force |
|---|---|---|---:|---:|---:|---|---|---|
| 03d032d57e5b:304:0 | development | ATTACKER | True | False | False | MULTIPLE_INBOUND_UNKNOWN, PAIR_RELATION | AMBIGUOUS | AMBIGUOUS |
| 03d032d57e5b:1245:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| 03d032d57e5b:1363:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| 03d032d57e5b:1438:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| 03d032d57e5b:1515:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| 03d032d57e5b:1622:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| 03d032d57e5b:1678:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| 03d032d57e5b:1837:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN, PAIR_RELATION | AMBIGUOUS | AMBIGUOUS |
| 03d032d57e5b:1917:0 | development | ATTACKER | True | False | False | MULTIPLE_INBOUND_UNKNOWN, PAIR_RELATION | AMBIGUOUS | AMBIGUOUS |
| daf86d0544b7:55:0 | development | DEFENDER | True | True | False | PAIR_RELATION | DISAPPEARED | DISAPPEARED |
| daf86d0544b7:63:0 | development | DEFENDER | True | True | True | — | DISAPPEARED | DISAPPEARED |
| daf86d0544b7:912:0 | development | DEFENDER | True | True | True | — | DISAPPEARED | DISAPPEARED |
| daf86d0544b7:1512:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| daf86d0544b7:1678:0 | development | DEFENDER | True | True | False | PAIR_RELATION | AMBIGUOUS | AMBIGUOUS |
| daf86d0544b7:1869:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| daf86d0544b7:1986:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| daf86d0544b7:2049:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| daf86d0544b7:2105:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| daf86d0544b7:2121:1 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN, PAIR_RELATION | AMBIGUOUS | AMBIGUOUS |
| daf86d0544b7:2236:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| daf86d0544b7:2291:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| daf86d0544b7:2346:0 | development | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| 7d56a775bc4c:424:0 | holdout | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| 7d56a775bc4c:456:0 | holdout | ATTACKER | True | False | False | MULTIPLE_INBOUND_UNKNOWN, PAIR_RELATION | AMBIGUOUS | AMBIGUOUS |
| 7d56a775bc4c:550:0 | holdout | ATTACKER | True | False | False | PAIR_RELATION | AMBIGUOUS | AMBIGUOUS |
| 7d56a775bc4c:572:0 | holdout | DEFENDER | True | True | True | — | DISAPPEARED | DISAPPEARED |
| 7d56a775bc4c:574:0 | holdout | DEFENDER | True | True | True | — | DISAPPEARED | DISAPPEARED |
| 7d56a775bc4c:744:0 | holdout | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| 7d56a775bc4c:861:0 | holdout | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |
| 7d56a775bc4c:951:0 | holdout | DEFENDER | True | True | False | MULTIPLE_INBOUND_UNKNOWN, PAIR_RELATION | AMBIGUOUS | AMBIGUOUS |
| 7d56a775bc4c:1027:0 | holdout | ATTACKER | True | False | False | MULTIPLE_INBOUND_UNKNOWN | AMBIGUOUS | AMBIGUOUS |

All unevaluable rows remain in the raw formula results. Strict local blockers are unresolved simultaneous inbound context and, for foreign-versus-foreign pairs, the absence of an observed hostility relation. The four clean cases do not meet the minimum sample size for support.
