# V8 FunctionLocation column derivation for the generated shim

## Result

For the generated named adapter at `runtime/research/v2/client.js:1976`, the
source-derived V8 expected `FunctionLocation` column is **125** (zero-based),
the opening parenthesis before `arg0`. It is not column 0 at the `function`
keyword, the function-name start, or column 144 at the `{` body opener.

The derivation follows V8's upstream implementation chain: the ordinary
function parser records the function-scope start after matching `(`;
`ParserBase::position()` returns the current scanner token's beginning;
`Function::GetScriptColumnNumber()` converts `SharedFunctionInfo::StartPosition()`
to a zero-based column; and the inspector's internal-properties implementation
uses those Function API line/column values to construct `[[FunctionLocation]]`.
The exact V8 revisions consulted are listed below. The installed browser's
Chromium/V8 revision is not available in this static review, so the `1975:125`
CDP-style coordinate is an upstream-source expectation, **not a certified
runtime value**. Keep metadata checks fail-closed and do not claim that a live
closure is this `f`.

## Derivation against the pinned JavaScript

The source file has SHA-256
`05b51675785a3f6568f4d80562dabb4f59a6130504c7a04c7de9cf777c33094e`.
Its adapter declaration begins at one-based line 1976. On that exact source
line, the character offsets are:

| Token | Zero-based column |
| --- | ---: |
| `function` keyword | 0 |
| Opening `(` before `arg0` | 125 |
| Function-body `{` | 144 |

In the reviewed V8 parser source, `ParseFunctionLiteral` successfully checks
`Token::LPAREN` and then sets the function scope's `start_position` from
`position()`. V8's parser-base accessor defines `position()` as
`scanner_->location().beg_pos`, i.e. the beginning of the currently matched
token. For this function declaration, that is the opening parenthesis. The
separate function-token position is passed into `NewFunctionLiteral`, but
the V8 API column getter does not use that token-position field: it calls
`Script::GetColumnNumber(script, shared->StartPosition())`. The script-column
conversion returns the column directly, without adding one.

The CDP internal-properties path in the inspected V8 snapshot is
`V8Debugger::internalProperties` in `src/inspector/v8-debugger.cc`. For a
function value, it calls `buildLocation` with `function->ScriptId()`,
`function->GetScriptLineNumber()`, and `function->GetScriptColumnNumber()`,
then appends the property name `[[FunctionLocation]]` and that location object.
This connects the parser/API derivation directly to the inspector property;
it is not merely an inference from debugger stack frames. A later V8 inspector
implementation at revision
[`4aabde87beb513a35d085bf4dac730aac83055a4`](https://chromium.googlesource.com/v8/v8/%2B/4aabde87beb513a35d085bf4dac730aac83055a4/src/inspector/value-mirror.cc)
routes `getInternalProperties` through `LocationMirror::create(function)`.
That later implementation is corroborating source history, not evidence that
the installed browser uses it. In the inspected snapshot, when the inspector
exposes this function's location against the unchanged external `client.js`
source with zero offsets, the derived zero-based CDP-style result is line
1975, column 125. Script identity, source hash, and exact function source
should still be checked independently; the column alone is not an identity
proof.

## Source revision and uncertainty

Primary V8 implementation references consulted:

- [`Parser::ParseFunctionLiteral`](https://chromium.googlesource.com/v8/v8/%2B/4e6b8eb339b0dbb65376d88a158274fc5d79d32e/src/parsing/parser.cc), V8 source revision `4e6b8eb339b0dbb65376d88a158274fc5d79d32e`: function scope start is set from `position()` after the `LPAREN` check.
- [`ParserBase::position`](https://chromium.googlesource.com/v8/v8/%2B/e10607a3ff1b9d7fcceca68ab8e40e09c612259b/src/parsing/parser-base.h), V8 source revision `e10607a3ff1b9d7fcceca68ab8e40e09c612259b`: accessor returns `scanner_->location().beg_pos`.
- [`Function::GetScriptColumnNumber`](https://chromium.googlesource.com/v8/v8/%2B/aee471b2ff5b1a9e622426454885b748d226535b/src/api/api.cc), V8 source revision `aee471b2ff5b1a9e622426454885b748d226535b`: it queries the script column at `shared()->StartPosition()`.
- [`DebugStackTraceIterator::GetFunctionLocation`](https://chromium.googlesource.com/v8/v8/%2B/364f4e94fc9cf01d73e497f81319b0ae07b75876/src/debug/debug-stack-trace-iterator.cc), V8 source revision `364f4e94fc9cf01d73e497f81319b0ae07b75876`: it constructs the location from the Function API's script line and column.
- [`Script::GetColumnNumber`](https://chromium.googlesource.com/v8/v8/%2B/9ac8b20086f95f1158a1901eefe12e25fd0333e4/src/objects/js-objects.cc), V8 source revision `9ac8b20086f95f1158a1901eefe12e25fd0333e4`: it returns `info.column` without the `+1` applied to line numbers.
- [`V8Debugger::internalProperties`](https://chromium.googlesource.com/v8/v8/%2B/8b1399fa94d82d9e9572974324bc05b824e7017e/src/inspector/v8-debugger.cc), V8 source revision `8b1399fa94d82d9e9572974324bc05b824e7017e`: for function values, it passes the Function API's script id, line, and column to `buildLocation`, then places that object under `[[FunctionLocation]]`.
- [`ValueMirror::getInternalProperties`](https://chromium.googlesource.com/v8/v8/%2B/4aabde87beb513a35d085bf4dac730aac83055a4/src/inspector/value-mirror.cc), V8 source revision `4aabde87beb513a35d085bf4dac730aac83055a4`: the later inspector implementation uses `LocationMirror::create(function)` for the internal function location.

These are official upstream source snapshots, not a single build revision
proven to match the user's installed browser. The runtime may use another V8
revision or debugger path. This review uses no runtime metadata, live host,
global/object inspection, callback invocation, hidden actor read, semantic
WASM execution, or formal credit.
