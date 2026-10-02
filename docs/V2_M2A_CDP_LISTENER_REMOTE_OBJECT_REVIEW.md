# M2A CDP listener RemoteObject availability review

## Finding

The cohort-2 metadata receipt fails before any scope reads because its
listener-identity predicate requires each `DOMDebugger.getEventListeners`
row's `handler` to be a function RemoteObject with an `objectId`. The saved
receipt has no handler rows, so it cannot establish whether the pinned browser
omitted those RemoteObjects or whether an identity/source mismatch caused the
refusal.

Chromium's current Blink implementation shows a concrete conditional
explanation: `getEventListeners` unwraps the target's `objectId` and carries
that object's group into listener serialization; `BuildObjectForEventListener`
sets both `handler` and `originalHandler` only when the carried group is
nonempty. With an empty group, the listener row can still contain its event
type, source location, and capture metadata while omitting both handler
RemoteObjects. This makes an empty-group explanation plausible for the helper,
whose `Runtime.evaluate` canvas lookup at `canvas-callback-scope-metadata-2-20261002.py`
does not specify `objectGroup`. It is not certified for the browser that
produced the receipt: its Chromium/CDP version and the exact `Runtime.evaluate`
object-group behavior are unavailable.

Do not weaken the current predicate or substitute `originalHandler`. Protocol
schema marks both fields optional, and the helper needs an identified
effective handler function for its pinned source and closure checks. The
metadata attempt remains fail-closed, with no scope reads and no callback
binding evidence.

## Source evidence

The primary Chromium source inspected was
[`inspector_dom_debugger_agent.cc`, refs/heads/main, blob `b23a7ffe69de2276b6450f4d927a791ce6d27a25`](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/third_party/blink/renderer/core/inspector/inspector_dom_debugger_agent.cc):

- Lines 439–462 unwrap the target object and pass its `object_group` to listener
  construction.
- Lines 493–523 populate listener metadata, then gate both `handler` and
  `originalHandler` serialization on `object_group_id.length()` at lines
  513–519.

The checked-in protocol describes `DOMDebugger.EventListener.handler` and
`originalHandler` as optional RemoteObjects, and `DOMDebugger.getEventListeners`
has no `objectGroup` parameter of its own. See the [official protocol schema](https://chromedevtools.github.io/devtools-protocol/tot/DOMDebugger/#type-EventListener)
and [`getEventListeners`](https://chromedevtools.github.io/devtools-protocol/tot/DOMDebugger/#method-getEventListeners).
The [Runtime.evaluate schema](https://chromedevtools.github.io/devtools-protocol/tot/Runtime/#method-evaluate)
lists `objectGroup` as optional. The protocol alone does not state that omission
will yield an empty group in every browser build.

The helper's `_object` call at lines 103–113 sends `Runtime.evaluate` with
`returnByValue: false` but no `objectGroup`. Its listener lookup at lines
127–135 then calls `DOMDebugger.getEventListeners` with the resulting canvas
`objectId`; no explicit group is passed to that command. The identity predicate
at lines 171–180 rejects a missing handler object ID. The receipt records
`OFFICIAL_CANVAS_HANDLER_IDENTITY_MISMATCH`, zero callbacks, and zero scope
reads.

DevTools frontend at revision
[`ffe9886f26de53c26da1a10d26ce2836dacd850b`, `DOMDebuggerModel.ts`](https://chromium.googlesource.com/devtools/devtools-frontend/+/ffe9886f26de53c26da1a10d26ce2836dacd850b/front_end/core/sdk/DOMDebuggerModel.ts)
also converts absent payload handler fields to `null` (see `eventListeners`,
around lines 70–90). That is consistent with the optional schema, not evidence
about the browser version used for this run.

## Minimal follow-up diagnostic

If a future authorized run has an already-owned eligible host, preserve the
pinned site, source hash/location checks, page ownership, and read-only bounds.
Resolve the canvas through `Runtime.evaluate` with a fresh, nonempty,
task-specific `objectGroup`, then call `DOMDebugger.getEventListeners` on that
canvas object as before. Record only whether `handler` and `originalHandler`
RemoteObject IDs are present per expected event; do not inspect, invoke, or
publish their IDs. Release that one group after the bounded inspection. Keep
the current identity predicate unchanged; a positive result would explain
the group-dependent omission mechanism for that browser, while a negative
result would leave the failure cause unknown. No host run or code change is
part of this review.

## Scope and status

Static primary-source review only. No live host, callback/scope inspection,
actor read, page interaction, guard change, or code edit was performed. The
browser version remains unknown; the group-dependent omission is a conditional
explanation, not certification of the prior failure's cause or any listener
topology/callback binding.
