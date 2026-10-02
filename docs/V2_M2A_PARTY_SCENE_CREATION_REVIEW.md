# M2A party-scene creation review

## Finding

The single retained click on `Play with friends` opened `/play-with-friends/` in the same document and displayed radio choices `accept`, `public`, and `party`, an Invite Code field, and OK/Cancel. No choice or submit action was taken. Pinned static data labels the party branch as a party/configurable-party-server path and contains a “Party server limit reached” message. That makes Party + OK a likely online server-creation attempt with server-side effects; the exact submit callback and server result are not statically bound here. Treat it as a scene-creation action, not a local-only preview.

There is no static evidence in this bounded client review of a required account, an ad requirement, or a requirement to send a human an invitation before starting. Those requirements remain **UNKNOWN**. The available client source says that after a `SessionCreated` update the client sends `InvitationRequest::Create` so an invitation is available; this has no human recipient and does not prove that the Party submit succeeds or creates a session.

## Observed state and scope

Source: `runtime/research/v2/play-with-friends-options-20261002.json`.

- The URL path changed from `/` to `/play-with-friends/` after exactly one ordinary button click, with the same document-origin timestamp and no observer.
- The visible dialog heading is “Play with friends.” The recorded controls include `input#accept[type=radio]`, `input#public[type=radio]`, `input#party[type=radio]`, an Invite Code textbox, and OK/Cancel buttons.
- The retained action records zero selected choices, zero invite/copy actions, no join, and no observer. It grants zero formal credit. No party was created in this observation.

## Pinned client evidence

Artifact: `runtime/research/v2/fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.wasm`; static disassembly: `runtime/research/v2/disassembly.json` (`lines` array). The available source subset does not include `client/src/yew_ui/dialog/play_with_friends_dialog.rs`; that path appears only as a compiled source-location string in active data. No code was executed.

- `func3182` builds the dialog titled “Play with friends” via `NexusDialogPropsBuilder::title` at WAT lines 552921–552929. It translates the party option copy at lines 554524–554538 and configurable-party copy at 554879–554922. Active-data keys include `party_server` (`0x1098b1`) and `configurable_party_server` (`0x109914`), with copy “Invite friends to play with you on a custom party server” (`0x109954`).
- The same renderer translates “Party server limit reached. Try again later.” at lines 555357–555361 (`0x10998c`), “Invite code:” at 555184–555188 (`0x1099b8`), and the “Bots” setting at 555761–555765 (`0x1099c4`). The limit message establishes a failure/limit UI path but gives no quota value or account rule.
- `func3182` obtains a `use_client_request_callback` hook at lines 552240–552254 and builds UI callbacks. The bounded trace did not resolve the `party` radio plus OK closure to a concrete request or navigation call. The renderer has no direct `use_interstitial_ad` hook in its WAT call list; this does not rule out a gate elsewhere in the application or service.
- Retained client source `runtime/research/v2/kodiak-source/client/src/broker/client_broker.rs`, lines 96–106, handles `ClientUpdate::SessionCreated` by sending `CommonRequest::Invitation(InvitationRequest::Create)`. Its adjacent comment says this creates an invitation so the player need not wait for one later. This is evidence of a server invitation-creation request after a session exists, not a message addressed to a human. It does not establish that this dialog's Party submit reaches that state.
- The dialog labels and code paths do not establish a numeric party limit, whether sign-in is required, whether an ad is ever requested outside this renderer, or whether opening the party session starts a game clock immediately.

## Superseded next-step hypothesis and observed follow-up

The original proposed Party + OK probe was superseded by actual ordinary UI evidence: selecting Party changed OK to Play, and the controller refused its now-absent OK target. A subsequent controller also refused its obsolete dialog-URL selector. Finally, the current visible Play control joined the normal party page, but the old extractor rejected that official party route before any canonical sample. All failed attempts retained zero troop actions, observer arms, and formal credit. These probes used the existing dedicated profile; no additional fresh-profile reset was performed. This can create or attempt to create an online party session, may encounter a party-server limit, and may cause the client to request an invitation code automatically after session creation. It should not require sending a message to another person based on the evidence here. No server availability, quietness, privacy, or participant cap is established; do not treat the selection as a guaranteed private or empty scene.

This review made no live UI interaction, storage or credential access, server request, invite, copy, or game action. Formal credit remains zero.

The actual UI joined a six-uppercase-ASCII-letter official party route. The new shared route-admission helper accepts only this observed shape or the exact root URL while retaining the pinned client, source, memory, lifecycle and visibility guards. Party quietness and canonical readiness remain to be measured; actual invitation codes stay in ignored receipts and are redacted in published evidence.
