# M2A current Luna concurrency decision

Instruction: user attachment b91bfd1b-7b1c-4023-a47d-67228df01fb1.
This supersedes the earlier six-to-eight-worker target for the current phase.

CURRENT CONCURRENCY CAP: Sol + 3 Luna.
RECOMMENDED CONCURRENCY CAP: Sol + 3 Luna.
SOL BOTTLENECK: NO sustained review backlog demonstrated.
LUNA BOTTLENECK: NO evidence that worker-count capacity is the main blocker.
TASK PARALLELISM: MEDIUM.
CONFIG CHANGE: NONE.

## Actual workflow evidence

A/B: More than three valuable investigations exist in the task pool, and slots
have been filled through rolling dispatch. This establishes a backlog, not that
more than three tasks are continuously ready without dependencies.

C: This round followed provenance review -> builder -> independent review ->
bool/int boundary repair, and capture review -> relation repair -> independent
review -> expanded comparison contract -> retained-corpus replay. The replay
worker explicitly waited for final source, and its earlier batch was stopped
before output writes when source changes would invalidate the manifest. Additional
workers cannot remove these correctness dependencies.

D/F: Completed bounded findings have been reviewed and either admitted with
limits or sent back for a concrete repair. There is no demonstrated sustained
pile of unreviewed results. Integration and architecture decisions occasionally
sit on the critical path; their latency should be observed before adding workers.
No accepted-work-per-hour comparison between different caps has been measured.

E: Investigation, privacy review, queue tracing, corpus classification and local
verification form most independent work. Source-writing tasks are narrower but
concentrated in state.py, model.py, extractor.py and step.py. Writers have disjoint
ownership or run sequentially. That concentration limits useful write parallelism.

Three Luna are therefore the current cap, not a quota. Use two or fewer when a
worker would only wait for source or a decision. Keep rolling dispatch for ready
P0/P1 work. Reassess after a stable checkpoint or a phase with sustained independent
read-only work, using accepted results, review latency, idle time and conflicts.

## Configuration and evidence boundary

No Codex configuration was inspected or edited for this decision; no setting key,
hot-reload behavior or next-session increase is claimed. No session, browser,
sampler or worker was terminated to change concurrency.

The current four-total-agent tool limit is supplied by this session's runtime
instructions, independently of product documentation. Official Responses API
multi-agent guidance recommends three concurrent subagents for most workloads
and explains independent-task delegation:
https://developers.openai.com/api/docs/guides/responses-multi-agent.
That API guidance is context, not proof of a Codex desktop TOML key or hot reload.

M2 remains IN_PROGRESS. This management decision does not grant troop-input
authorization, change any gate, or permit M3.
