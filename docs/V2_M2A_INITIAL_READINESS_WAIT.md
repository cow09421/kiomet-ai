# M2A initial readiness wait

`tools/v2_controlled_transition_capture.py --execute --source ID --destination ID`
keeps its existing one-sample readiness behavior by default. The optional
`--wait-ready-seconds N` accepts only a CLI integer from 0 through 10. A
positive value applies only before the first endpoint selection; it does not
change preview mode, the selected pair, the command count, or any readiness,
scenario, line, inventory, freshness, observer, or security guard.

The bounded wait starts only from a known `IN_MATCH` / `NETWORK` identity and
stays on the same document, match, player, lifecycle, and source mode. It ends
when the sample is ready, the requested wait expires, the recorder's existing
`--seconds` deadline is reached, or that identity changes. A ready sample at
either deadline is rejected, even if it is otherwise ready. The recorded
elapsed time is the actual measured time and is not clipped to the configured
limit. Missing facts remain gaps; unknown facts are never filled with defaults.
After a ready sample, the explicit source and destination are validated again
from that current inventory, and the existing immediate preselection readiness
check still runs.

Every rejected initial sample is written and fsynced as an
`INITIAL_READINESS_REJECTION` before another sample is requested. A positive
wait also records one `INITIAL_READINESS_WAIT` receipt with its limit, attempts,
elapsed bound, final status, and final snapshot. These are preselection
diagnostics only. A readiness rejection after any selection remains governed
by the existing immediate refusal path; this option does not retry a selected
or armed action.

The pure async helper `wait_initial_readiness` accepts an extractor, injected
clock/sleep functions, and a durable-receipt callback. Its focused tests cover
gap-to-ready, timeout receipts, identity change, missing readiness facts,
zero-wait single-sample behavior, both total and wait deadline edges, and exact
integer bounds. No live host or UI input is part of these tests.
