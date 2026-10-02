# M2A Play-with-friends scene review

## Finding

The retained menu inventory shows a visible `#play_with_friends_button` labeled “Play with friends.” In the pinned WASM, a dialog-rendering path assigns that same text as a `NexusDialog` title and constructs invitation-choice copy for the nest, public server, and invite codes. This is strong evidence that the control enters an options/invitation dialog; the exact button-event-to-dialog edge is not resolved in this bounded static review. No evidence here shows that the top-level button itself immediately spawns a server or sends an invitation. That outcome remains **UNKNOWN**, rather than a proven absence of network activity.

## Retained menu observation

Source: `runtime/research/v2/menu-scene-selector-20261002.json`.

- The recorded URL is `https://kiomet.com/`; the inventory found `BUTTON#play_with_friends_button` with label `Play with friends`.
- The recorded action budget was one DOM inventory, zero clicks, no join, no observer, and no wheel or troop gestures. The result records no server/region selector among the visible controls and grants zero formal credit.
- The inventory also records `Settings` and `Go offline`; neither observation establishes a private or quiet server option.

## Pinned static evidence

Artifact: `runtime/research/v2/fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c.wasm`; WAT: `runtime/research/v2/disassembly.json` (`lines` array). These checks parse static data and inspect disassembly only; they do not execute the WASM.

- The active data includes the compiled source-path string `client/src/yew_ui/dialog/play_with_friends_dialog.rs` at address `0x104873`. This is a source-location clue, not source code.
- In `func3182`, WAT lines 552921–552929 translate the “Play with friends” string at active-data address `0x139d5f` (decimal immediate `1285471`) and pass the result to `NexusDialogPropsBuilder::title`. This establishes that the pinned client has a dialog titled “Play with friends.”
- The same function translates dialog copy “Accept an invitation from a friend” at lines 553090–553094 (`0x10973c`), “Invite friends to play with you in the nest” at lines 553681–553685 (`0x1097e8`), “Invite friends to play with you on the public server” at lines 553694–553698 (`0x109813`), and “Invite code” at lines 553918–553922 (`0x109847`). It also builds “Copy to clipboard” at lines 554253–554257 and 555536–555540 (`0x1098a0`).
- Nearby active data includes “Invite players to this server without them joining an existing team,” “Invite friends to play with you on a {mode} party server,” “Invite friends to play with you on a custom party server,” and “Party server limit reached. Try again later.” These strings support a subsequent invite/server-choice flow; they do not establish that merely opening the dialog triggers it.
- The active data also contains the `play-with-friends` route label at `0x13f00e`. Its presence alone does not establish that the menu button navigates to that route.

## Boundary and next bounded observation

The menu inventory did not click the button, and the static pass did not bind its event closure to `func3182` or prove the button's first-click network effects. Therefore the supported conclusion is “dialog/options path indicated; immediate spawn/send unproven,” not “click is guaranteed local-only.” No server, party, invite, or message was created or sent in this review.

If another UI observation is authorized, the narrow next step is one click on `Play with friends` in a fresh profile, record the resulting visible dialog and URL, and stop before choosing any invite, server, or copy action. If the question includes whether that first click contacts a server, record only request destinations and methods during that single transition; do not submit forms or start a host. This review itself made no live UI interaction and grants no formal credit.

## Subsequent bounded normal UI result

Root performed one ordinary click on the observed menu button in the restored dedicated profile, with no join and no observer. It navigated within the same document to `/play-with-friends/`, displayed the dialog title, and exposed radio controls `accept`, `public`, and `party`, plus Invite Code, OK, and Cancel. No radio, OK, invite, or clipboard action was taken. The host exited normally. This confirms the ordinary dialog route but does not prove the party creation semantics or first-click network effects. See `V2_M2A_PLAY_WITH_FRIENDS_OPTIONS_VALIDATION.json` and its three exact gzip fixtures.
