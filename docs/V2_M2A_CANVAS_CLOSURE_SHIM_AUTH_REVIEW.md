# Canvas mutable-closure shim source authentication

## Result

The pinned JavaScript source identifies the exact `f` supplied by
`__wbindgen_cast_0000000000000004`: it is the generated JS adapter declared
at `runtime/research/v2/client.js` line 1976. Its source body calls the
matching named WASM export and converts the callback's JavaScript event to a
heap handle. The WASM export is function 4974 in the pinned disassembly. This
source chain establishes the generated closure ABI for the reviewed `listen`
path and identifies the static expected source location for `f`; it does not
establish a live closure instance or authorize invoking it.

The exact UTF-8 bytes of the declaration text from line 1976 through the
closing brace at line 1978, excluding the trailing line terminator, hash to
`aebf44f63962271f050769f1cea91db7da38985e5489d1db0f10f4cfe140e7d4`.
Including the trailing LF hashes to
`5aeba66a72e652c4018f55df7416d851b55b50cfbf9e2f714887c243faecf06d`.
The source file SHA-256 is
`05b51675785a3f6568f4d80562dabb4f59a6130504c7a04c7de9cf777c33094e`.
The hash of the source slice is reproducible, but the expected
`Function.prototype.toString` hash is **NOT CERTIFIED**: this review did not
execute the page or verify browser source-text normalization against the
runtime value.

The source slice being hashed is:

```js
function wasm_bindgen_6b69409326653860___convert__closures_____invoke___wasm_bindgen_6b69409326653860___JsValue______true__1_(arg0, arg1, arg2) {
    wasm.wasm_bindgen_6b69409326653860___convert__closures_____invoke___wasm_bindgen_6b69409326653860___JsValue______true__1_(arg0, arg1, addHeapObject(arg2));
}
```

## Static ABI chain

1. In the cast table, `__wbindgen_cast_0000000000000004` at lines 1869–1873
   passes `(arg0, arg1, f)` to `makeMutClosure`; its exact third argument is
   the line-1976 JS adapter below. The generated cast comment declares the
   closure mutable, with one `Externref` argument and a `Unit` return.
2. `makeMutClosure` at lines 2269–2295 constructs `{a: arg0, b: arg1, cnt:1}`
   and returns `real = (...args) => ... f(a, state.b, ...args)`. It restores
   `state.a` in `finally`. Therefore this path forwards the two captured
   values followed by the incoming callback argument to the exact adapter
   function above. This is source-level closure behavior; no closure was
   created or invoked for this review.
3. The pinned disassembly identifies WASM function 4974 as exporting
   `wasm_bindgen_6b69409326653860___convert__closures_____invoke___wasm_bindgen_6b69409326653860___JsValue______true__1_`.
   The line-1976 adapter calls that named export with `(arg0, arg1,
   addHeapObject(arg2))`. Function 4974 also exports two named variants
   suffixed `__5` and `__7`; those are not the symbol passed at cast 0004.
4. The existing pinned `listen` review establishes that this cast call passes
   a 12-byte control-envelope pointer as `arg0` and fixed adapter record
   `0x13e700` as `arg1`. The accepted callback-descriptor review maps that
   adapter record's function-table index 2504 to `func1359`. The envelope's
   `+4` word is callback-dispatch metadata; it is not an actor field. These
   premises are static only and do not identify the current runtime closure's
   `+4` value.

## Expected location and fail-closed boundary

The JavaScript source declaration begins at one-based source line 1976,
column 1 (zero-based line 1975, column 0) in the file whose SHA-256 is listed
above. That is the static expected start location for the adapter passed as
`f`. A V8 `FunctionLocation`/debugger `SourceLocation` coordinate and its
column derivation class were not observed or independently certified here.
Treat location metadata as **UNVERIFIED** and fail closed on any mismatch;
do not infer a function match from line alone.

This establishes source and ABI premises only. It does not inspect closure
state, globals, heap handles, callback captures, vtable contents, actors, or
game state; it does not invoke the callback, authorize a phase-B read, bind a
particular live listener, or add formal credit. The outer adapter and inner
callback remain distinct: `0x13e700` routes through `func1359`, while the
runtime inner closure vtable at envelope `+4` remains **UNKNOWN**.

The static chain relies on
[V2_M2A_CANVAS_LISTENER_ENVELOPE_BOUNDARY_REVIEW.md](V2_M2A_CANVAS_LISTENER_ENVELOPE_BOUNDARY_REVIEW.md)
for the `listen` call arguments and
[V2_M2A_INPUT_CALLBACK_DESCRIPTOR_REVIEW.md](V2_M2A_INPUT_CALLBACK_DESCRIPTOR_REVIEW.md)
for the fixed adapter-record/table mapping. It does not repeat their inner
callback-vtable producer analysis.
