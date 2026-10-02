# Fresh project profile scene review

**Prepared review, executed once on 2026-10-02.** The current code uses one project-owned persistent Chromium profile path, `runtime/browser-profile`. A fresh directory at that same path gives the existing host a new browser session without changing the host, port discovery, observer, or game-command code. This may produce a fresh ordinary network join and new anonymous browser identity, but it cannot guarantee a quiet match, a different player ID, or a new server/world.

## Ownership and current state

The README names `runtime/browser-profile/` as the dedicated browser profile. Both `tools/v2_headless_research.py` and the headed `BrowserHost` launch against that project path. The host uses Playwright's `launch_persistent_context(profile, ...)`; `connect_dedicated` later reads that profile's `DevToolsActivePort` and verifies that the listener process has the same `--user-data-dir`. No caller-supplied profile or desktop Chrome path is involved in this workflow. See `README.md` around line 102, `tools/v2_headless_research.py` around lines 71–90, `src/kiomet_ai/v2/observe/extractor.py` around lines 22–33, and `src/kiomet_ai/browser.py` around lines 90–121 and 483–505.

At review time, `runtime/browser-profile` resolved inside this project's `runtime` directory and was not a symlink. The read-only ownership scan returned no Chromium process using that profile, and `runtime/research/v2/headless-host.json` was absent. These checks are point-in-time; repeat them immediately before any rename. No profile contents, cookies, tokens, or storage were read.

The directory is explicitly project-owned, but it may contain a user-authenticated Kiomet session. Preserve it intact. Do not inspect, clean, or delete its contents. If the resolved path or process ownership is ambiguous at run time, stop before moving it.

## Minimal reversible procedure

1. Recheck that no process matches the exact project profile and no host lease remains. Stop if either check finds an owner.
2. Rename the entire `runtime/browser-profile` directory to a new, unused archive name on the same volume, such as `runtime/browser-profile-archive-20261002-<unique>`. Keep it intact; do not overwrite an existing archive.
3. Start the existing `tools/v2_headless_research.py` at its normal expected path. `launch_persistent_context` creates a new profile at `runtime/browser-profile`; use its ordinary Play action for the requested fresh network join. Add the existing opt-in input-entry observer only if the later cohort requires it before page creation.
4. On terminal host exit, preserve the fresh profile too. To roll back, first verify no process or lease uses either path, rename the fresh profile aside, then restore the original archived directory to `runtime/browser-profile`.

The new profile avoids reusing the old browser's persistent anonymous/session state. The server may still return the same player, region, or long-lived world because the server's session selection is outside this local profile boundary. A new document/match identity must be observed from the ordinary join; it cannot be assumed from the directory change.

## Scope for the prepared cohort

This scene setup changes only local browser persistence. Keep the existing full-visible-world readiness and force-endpoint requirements unchanged. A fresh profile does not make unknown force endpoints known and does not qualify a pair by itself. The prepared cohort may use at most one normal wheel event and at most one reviewed friendly gesture under its existing gates; if readiness or candidate review fails, finish with zero gestures and preserve both profiles.

No profile was moved, no host was started, and no game or observer input was sent during this review.

## Recorded execution outcome

Root subsequently ran the bounded rotation and one normal wheel. The fresh host observed player 107 instead of 31, but required force endpoints remained unknown after 34 post-wheel samples. Both observer receipts remained DISARMED with armed_once false; there were no troop gestures. The host exited normally, the original profile was restored intact, and the fresh profile was preserved separately. See `V2_M2A_FRESH_PROFILE_SCENE_VALIDATION.json` for the complete experiment and fixture hashes. This diagnosis will not repeat profile or viewport retries. The preceding procedure and no-input statement describe the preparation review, not the subsequent experiment.
