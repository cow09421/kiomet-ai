# M2A manual launch initialization

This note records the pinned manual `DeployForce` initialization used by the
simulator. It establishes the new force's current-segment acceleration,
progress, and fuel. It does not establish whether the force receives another
path at arrival.

## Manual command path

The vendored normal UI handles a left-button drag in
`vendor/kiomet-ref/client/src/game.rs`: on mouse-up it calls
`Command::deploy_force_from_path(path)` when the gesture is a launch rather
than a supply-line edit. The command sets the source to `path[0]` and wraps the
same path in `Path::new` (`vendor/kiomet-ref/common/src/protocol.rs:35-40`;
`common/src/force.rs:16-31`). The pinned server apply function's manual
DeployForce case calls `Tower::deploy_force` at `0x7d542`
(`runtime/research/v2/Chunk__apply_0.txt`, function 573, `0x7d430`).

`Tower::deploy_force` is function 1791 at `0x100407`. It creates the outgoing
Force value at stack offset +24 and calls `Tower::send_force` with that value
at `0x1004ba`:

- `0x100495-0x10049c` copies the supplied Path header into Force+0..+11;
- `0x10049f-0x1004a6` copies the remaining Path header word;
- `0x1004a9-0x1004b0` copies the source Tower byte at +45 into Force+21;
- `0x100485-0x10048b` stores `38400` (`0x9600`) at stack +46, which is Force
  +22/+23 in little-endian order: progress `0`, fuel `150`;
- `0x1004ba` passes the constructed Force to `Tower::send_force`, which copies
  its fields into the outbound/inbound events (`Tower__send_force.txt`,
  `0x107643-0x1076d3`).

The pinned `Force::progress_required` reads Force+21 as the accelerated flag
(`runtime/research/v2/disassembly.json`, function 2689, `0x11ccf0-0x11cd15`),
and `Force::interpolated_position` reads Force+22 as path progress (function
1861, `0x1036f0-0x103701`). Therefore a manual launch inherits the source's
observed `Tower.morale` byte as `accelerated`; it starts at progress 0 with
fuel 150. This is the exact initial current-segment state represented by
`SimForce` in `src/kiomet_ai/v2/sim/step.py`.

The separate scratch Force construction at `Chunk__apply_0` `0x7d849-0x7d898`
does zero +21/+22 and store 150 at +23. It is in another apply branch after
the spawn setup at `0x7d661` and must not be used to infer manual launch
acceleration. An earlier audit incorrectly applied that zeroed scratch value
to normal manual launches; the manual `Tower::deploy_force` call above is the
correct construction path.

## Limits

The pinned values establish launch-time fields only. They do not establish
that a two-node Path cannot continue through an automatic supply line at
arrival, nor do they establish terminal-route status from a later visible
force segment. The UI can also interpret a drag from an already selected
mobile-producing source as `SetSupplyLine`; the launch simulator premise
applies only when the UI takes its `DeployForce` branch. Current force
observations expose the current segment, not the remaining Path or fuel.

The supporting WASM has SHA-256
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c` in
`runtime/research/v2/client-version.json`.
