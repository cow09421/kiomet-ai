# Kiomet AI v2 restart

Started: 2026-09-30 (Asia/Taipei). Owner: this agent only.
Branch: `v2-rebuild`; v1 base: `234cfad918381adfd2a48a183ca17d35b64970e0`.
The initial folder lacked `.git`; history was fetched and indexed without replacing files.

## Gates (no downstream work before PASS)

| Gate | Deliverable and acceptance | Time limit |
|---|---|---|
| M0 | Written player-information contract; auditable source/visibility/version boundary | before extraction |
| M1 | Immutable state + real extractor; 3 independent 10-minute matches; >=4 Hz, p95 age <=250 ms; >=1,000 stratified real comparisons, >=99% critical-field agreement; zero hidden information | 3 working days / 18 engineering hours |
| M2 | Deterministic integer-tick world; 1,000 one-tick + 100 real 5–10s trajectories, >=99% discrete agreement; zero king/elimination reversals; representative CPU total >=50,000 complete transitions/s | 40 engineering hours |
| M3 | MPC + multi-step search; same candidates/value as no-search; >=3 own decision points, >=128 distinct plans/scenarios; p95 <=250 ms; 200 held-out paired games, >=65% wins and 95% lower bound >50% | 30 engineering hours |
| M4 | Official UI closed loop; p95 observation-to-input <=750 ms; >=98/100 accepted, zero cross-match/stale-coordinate dispatch; 20 predefined public games plus 30 comparable games against >=5 confirmed humans, >=70% wins and lower bound >50% | 40 engineering hours |
| M5 | Only after successful M4: neural/GPU extension beats CPU >=60% over 300 pairs (lower bound >50%) or halves latency at same strength | 20 engineering + 48 GPU hours |

M1–M4 failure stops the project. M5 failure stops neural extension only.
Unknown evidence stays UNKNOWN; synthetic tests do not satisfy live gates.

## First session

1. Write M0 contract and immutable state, separate from v1 controller.
2. Locate the official client's actual player-visible structures; verify production version.
3. Build read-only extraction with per-field provenance, atomic snapshots and fresh session identity.
4. Measure real observation and compare against official UI. Record remaining gaps honestly.

Freeze v1 dashboards, spectators, toy simulator and old orchestration. No GPU, training,
search, full live loop or new evidence platform in this session. Reuse isolated browser
and verified pure decoders only. Production inputs are page-local official UI events;
never global input, injected packets, heap writes or semantic WASM commands.

## Current status

M0: written contract pending implementation verification. M1: IN PROGRESS.
M2–M5: NOT STARTED. See `docs/V2_M1_STATUS.md` for session evidence.
