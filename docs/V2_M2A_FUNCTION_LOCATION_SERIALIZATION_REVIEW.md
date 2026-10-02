# CDP `[[FunctionLocation]]` serialization review

## Result

In the inspected V8 inspector implementation, the `[[FunctionLocation]]`
internal-property descriptor carries a `Runtime.RemoteObject` whose location
is serialized inline in its `value` field. The source shape is:

```json
{
  "name": "[[FunctionLocation]]",
  "value": {
    "type": "object",
    "subtype": "internal#location",
    "description": "Object",
    "value": {
      "scriptId": "<decimal script id>",
      "lineNumber": 1975,
      "columnNumber": 125
    }
  }
}
```

The coordinates here illustrate the source-derived expectation from the
separate column review; they are not asserted to be the installed browser's
runtime values. The `RemoteObject` is not expected to need an `objectId` in
this source path: `LocationMirror::buildRemoteObject` sets a `value`, and
V8's `bindRemoteObjectIfNeeded` returns immediately when that field exists,
before the object-ID binding path. This supports recognizing the inline
location dictionary without dereferencing it as a normal remote object.

## Source path and limits

In V8 revision
[`4aabde87beb513a35d085bf4dac730aac83055a4`](https://chromium.googlesource.com/v8/v8/%2B/4aabde87beb513a35d085bf4dac730aac83055a4/src/inspector/value-mirror.cc),
`ValueMirror::getInternalProperties` adds a `LocationMirror` under the name
`[[FunctionLocation]]`. `LocationMirror::create(function)` reads the
function's script id, script line, and script column. Its
`buildRemoteObject` constructs a protocol dictionary containing:

- `scriptId` as a decimal string;
- `lineNumber` and `columnNumber` as integers;
- a `RemoteObject` with `type: "object"`, `subtype: "internal#location"`,
  `description: "Object"`, and that dictionary in `value`.

V8's `InjectedScript::getInternalAndPrivateProperties` builds the internal
property value and passes it through `bindRemoteObjectIfNeeded` before
placing it in an `InternalPropertyDescriptor` with the `[[FunctionLocation]]`
name. The inspected V8 implementation of `bindRemoteObjectIfNeeded` skips
object binding when `RemoteObject` already has `value`, so this synthetic
location does not acquire an `objectId`. See the official V8 source at
[`src/inspector/injected-script.cc`](https://chromium.googlesource.com/v8/v8/%2B/refs/tags/10.5.188/src/inspector/injected-script.cc).

The protocol shape and subtype are V8 inspector implementation details. The
referenced `LocationMirror` and `InjectedScript` source snapshots are not
certified as one matching build or as the user's installed Chromium/V8
revision. An absent `[[FunctionLocation]]` can also be legitimate: the mirror
factory returns no location when the function has no script id or its line or
column is unavailable. Therefore, use this shape as a source-grounded
recognition rule with version/build caveats, not as proof that a particular
live closure is the captured shim. This review uses no browser execution,
live object inspection, callback invocation, private memory, or hidden actor
state.
