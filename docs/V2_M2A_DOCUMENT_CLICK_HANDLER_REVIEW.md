# M2A document click handler review

## Scope and verdict

This is a static source review of the exact saved listener source
`tests/fixtures/v2/listener-source-7aa7f8a0357267423b6a42499e6cfb4ab34bed6c84bce4ee5134ed9f20662df1.js.gz`.
The decompressed source is 1,083,904 bytes and hashes to
`7aa7f8a0357267423b6a42499e6cfb4ab34bed6c84bce4ee5134ed9f20662df1`, matching
the document `click` row in `V2_M2A_LISTENER_SOURCE_VALIDATION.json` and
`V2_M2A_LISTENER_INVENTORY_VALIDATION.json`. No browser, live page, runtime,
memory, or handler invocation was used.

The saved callback is PageManager's one-shot document bubble listener. It does
not inspect the event or its target, and does not call `preventDefault`,
`stopPropagation`, or a navigation method. On its first invocation it removes
itself, marks the one-shot flag, and flushes callbacks held by its
`awaitUserInteracted` queue. The queue may contain arbitrary callbacks whose
registration and effects are not established by this source review. The click
therefore cannot be cleared as harmless for the canvas input path. Keep
click-route and possible queue effects **UNKNOWN**; retain the broad listener
inventory.

## Exact registered handler and branch

The validation inventory binds a `click`, `use_capture: false` listener to the
document at script 38, line 1, column 344469, with the source hash above. In the
captured source, PageManager's `#of()` installs `this.targetDocument.addEventListener("click",this.#hm)`
at character offsets 343524 onward. The target is `this.targetDocument`; the
registration uses the default bubble phase and is not conditional on event
target, button, or link status. The field `#hm` is bound to `#pm` at offsets
340138 onward.

The callback body is `#pm(e){this.#Ef()}` (offset 344534 onward); it does not
read `e`. `#Ef()` at offsets 347291 onward has one branch: if `#Fm` is false,
remove this same document listener, set `#Fm = true`, then call `#Hm.flush()`.
If `#Fm` is already true, it returns without flushing. The body contains no
world-state write, asynchronous scheduling primitive, event cancellation,
default-action cancellation, URL/history write, or direct navigation call.
Another path, `#Ks()` after scroll-depth processing, also calls `#Ef()`; thus a
prior qualifying scroll can remove the listener before a later click. The
captured inventory establishes it was registered at inventory time, not that
it will still be present at a future event.

`awaitUserInteracted(e){this.#Hm.add(e)}` (offset 348080 onward) is the only
local call site that adds callbacks to this queue. The queue object is
constructed as `new h._()` in PageManager's field initializer (offset 340406).
In module 83469, export `_` is class `a`, extending queue class `o` (offsets
201400–203400): `add` stores callbacks until flush; `flush` has default
`yieldStrategy = "direct"` and invokes the stored callbacks synchronously in
queue order; subclass `a.flush` runs at most once, and an `add` after that
flush invokes its callback immediately with the saved arguments. PageManager
calls `flush()` with no arguments. This establishes synchronous queue dispatch
only. It does not establish which callbacks are queued, what their bodies do,
or whether they enqueue asynchronous work or mutate game-related state.

No same-source call to `awaitUserInteracted` appears beyond the method
definition. The listener inventory's source location and hash establish which
callback is registered, but do not establish queue membership or prove that
the callback queue is empty. No conclusion about an ad-status effect, a game
world write, or a later continuation is supported without tracing concrete
registered callback producers and their effects. Limit this review to this
handler and its queue dispatch; it does not bind the other document/body/canvas
click listeners to application callbacks.

## Canvas, links, buttons, and defaults

The listener has no canvas-versus-link/button/ad branch: any bubbling click
that reaches the document takes the same `#Ef()` path. A click from the canvas
can therefore flush the queue just as a click from a link or button can. The
captured listener record places the official canvas on an ancestor chain that
is separate from the document listener; DOM ancestry alone does not exclude
the bubble path. The nearby body capture listener is separately present in
the inventory and remains semantically unbound.

This handler itself leaves browser defaults available. A link's navigation or
a button's activation/form behavior is not canceled here; whether another
listener changes that behavior is unresolved. A bare canvas click has no link
or form default by virtue of being a canvas, but that fact would not prevent
the document handler or its callback queue from running. To exclude the queue
effect for a proposed canvas gesture, BEFORE evidence would need to prove that
no `click` reaches this document listener (for example, a guaranteed absence
of click synthesis for the exact input sequence or a reviewed earlier
propagation stop), or prove that the callback queue is empty and cannot be
populated before the gesture. The current artifacts prove neither. DOM facts
such as target tag, ancestry, `href`, form association, and hit target can
constrain default navigation/activation, but cannot exclude this target-blind
document callback.

## Consequence

The handler source retrieval resolves its previously unknown control flow but
does not qualify click as harmless or certify the mouseup-to-game route. Keep
the registered document click in broad topology rejection and preserve the
existing shared-memory and listener guards. No input, guard change, formal
event, or core fix is proposed.
