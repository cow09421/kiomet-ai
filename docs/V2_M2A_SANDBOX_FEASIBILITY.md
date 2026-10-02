# Kiomet source sandbox feasibility

**Research date:** 2026-10-03. **Status:** `NOT_BUILT / NOT_RUN`.

## Finding

An isolated sandbox looks feasible in principle: the official `SoftbearStudios/kiomet` repository has separate Rust client, common, and server code, and its README describes running a local server at `https://localhost:8443/`. `SoftbearStudios/kodiak` supplies the shared Rust game-engine libraries, with a client framework and server framework. This supports a hypothesis laboratory in which both client and server could be instrumented, including a durable action ledger at UI dispatch and server command/application points. That feasibility is an inference from the published repository structure and instructions; it has not been demonstrated by a build or run.

The repositories were inspected on 2026-10-03. A read-only `git ls-remote` resolved Kiomet `HEAD` and `refs/heads/main` to `d3f0956f27f48f6cac9ac9991f948fa7f90ba77c`; Kodiak `HEAD` and `refs/heads/main` to `83f62d2aacd94647dbc97d1bd4764fbfc17cdf55`; and Kodiak `refs/tags/0.1.1` to `c17719a1b54ae1eae663a26bbb39fd842cd9a5c2`. The command returned no peeled `refs/tags/0.1.1^{}` line, so only the tag ref result is recorded here. No clone or fetch was performed.

## Materials and blockers

The published instructions require Rust, GNU make, GCC, Trunk 0.17.5, Rust Nightly, and the WebAssembly target. The same README explicitly warns that its `download_makefiles.sh` step is currently broken: it fetches newer Makefiles that use unsupported Trunk options, and suggests debugging them or trying a later Trunk. The script confirms it pulls `client.mk`, `game.mk`, and `server.mk` from Kodiak's moving `main` branch. This makes the documented build non-reproducible without first pinning or repairing those build files.

Kiomet's `.gitmodules` also names an `engine` submodule using the relative URL `../engine.git`, resolving under the organization to `SoftbearStudios/engine`. That official repository URL returned 404 in this review, so public availability and a reproducible submodule commit are unconfirmed (the repository could be private, removed, or otherwise inaccessible). Kodiak's README says some features, including chat, depend on a backend microservice, and that developer tools are still being prepared for open source. Those features may need to be disabled, replaced, or omitted for a minimal offline lab. Until the submodule and all build-time resources are resolved, successful compilation remains unknown.

## Control and action evidence

The published Kiomet `main` tree contains `client`, `common`, and `server`; the client and server manifests both declare version `0.1.1`, and the client references Kodiak client/common at tag `0.1.1` while the server references Kodiak server at the same tag. In a local-only build, source access should allow modifying both ends: the client can persist `intent_id`, monotonic send time, world sequence and chosen action before dispatch; the server can log receipt/application time and its applied command/result under the same correlation ID. This is a proposed instrumentation design, not a demonstrated API or existing feature.

The cleanest ledger would record separate client `ACTION_INTENT`, client UI/send result, server receive, server apply, and observed-world-result records. This could distinguish “gesture delivered,” “server received,” and “server applied” directly, then align the applied result to a server tick without inferring that tick from browser timing. It would still characterize only the open-source build. It would not by itself prove that the currently pinned official live client or server uses the same path.

## License and live-version boundary

The official repositories identify Kiomet as AGPL-3.0 and Kodiak as LGPL-3.0.

The official repository itself warns that commits may lag behind game updates. The locally pinned live assets in this workspace are WASM SHA-256 `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c` and generated JavaScript SHA-256 `05b51675785a3f6568f4d80562dabb4f59a6130504c7a04c7de9cf777c33094e`. This bounded source review did not map either live hash to the public repository or prove the public source corresponds to the official service on 2026-10-03. Differences in dispatch, queueing, tick timing, rules, and server behavior therefore remain unknown.

The repo's README expressly prohibits using its open-source client with official Kiomet servers. Any future build should run against its own localhost server in an isolated hypothesis laboratory; findings must be labeled `OPEN_SOURCE_SANDBOX_ONLY` and must not be promoted to claims about the pinned live service without independent version and behavior evidence.

## Source refs checked

The links point only to official Softbear GitHub repositories and raw files. The resolved refs above identify the official `main` branches and Kodiak `0.1.1` tag checked on 2026-10-03.

1. [Kiomet `main` README](https://raw.githubusercontent.com/SoftbearStudios/kiomet/main/Readme.md) — build steps, broken Makefile warning, localhost server instructions, official-server restriction, and lag caveat.
2. [Kiomet client `Cargo.toml` at `main`](https://raw.githubusercontent.com/SoftbearStudios/kiomet/main/client/Cargo.toml) and [server `Cargo.toml` at `main`](https://raw.githubusercontent.com/SoftbearStudios/kiomet/main/server/Cargo.toml) — client/server package versions and Kodiak `0.1.1` dependency refs.
3. [Kiomet `.gitmodules` at `main`](https://raw.githubusercontent.com/SoftbearStudios/kiomet/main/.gitmodules), [declared `SoftbearStudios/engine` submodule repository](https://github.com/SoftbearStudios/engine), and [Makefile download script at `main`](https://raw.githubusercontent.com/SoftbearStudios/kiomet/main/download_makefiles.sh) — engine submodule path (repo page returned 404) and moving Kodiak Makefile source.
4. [Kodiak `main` repository README](https://github.com/SoftbearStudios/kodiak/blob/main/README.md) and [Kodiak `main` LICENSE](https://raw.githubusercontent.com/SoftbearStudios/kodiak/main/LICENSE) — engine components, microservice/developer-tool caveats, LGPL-3.0.
5. [Kiomet `main` LICENSE](https://raw.githubusercontent.com/SoftbearStudios/kiomet/main/LICENSE) — AGPL-3.0.

No repository was cloned, and no dependency was installed; no build or runtime validation was performed.
