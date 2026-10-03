# Goal 005 — Official source-default upgrade labels

The ordinary upgrade title composes the translated target tower label with Translator::upgrade_to_label. Kiomet client Cargo.toml pins Kodiak tag 0.1.1, commit c17719a1b54ae1eae663a26bbb39fd842cd9a5c2.

Primary source:
- Audited local vendor/kiomet-ref/client/src/ui/tower_overlay.rs179–190 calls the normal upgrade/downgrade renderer; ui/phrases.rs39–72 defines the27 tower phrase keys. Source SHA256 values and enum ordering are recorded in the fixture.
- [Kodiak upgrade template](https://github.com/SoftbearStudios/kodiak/blob/c17719a1b54ae1eae663a26bbb39fd842cd9a5c2/client/src/translation/phrases.rs)129–134 distinguishes upgrade and downgrade.
- [Translation implementation](https://github.com/SoftbearStudios/kodiak/blob/c17719a1b54ae1eae663a26bbb39fd842cd9a5c2/client/src/translation/translator.rs) falls back to the source phrase and replaces the named variable.
- [Procedural macro](https://github.com/SoftbearStudios/kodiak/blob/c17719a1b54ae1eae663a26bbb39fd842cd9a5c2/macros/src/translate.rs) passes the source phrase and named variable.
- [Translation cache](https://github.com/SoftbearStudios/kodiak/blob/c17719a1b54ae1eae663a26bbb39fd842cd9a5c2/client/src/translation/cache.rs) fetches the runtime dictionary separately. No authoritative Traditional Chinese catalog was retrieved in this P0.

All6 downloaded Rust files were verified against Git blob IDs in the pinned commit tree. tests/fixtures/v2_goal_upgrade_titles_source.json records SHA256 values and27 source-default labels independently extracted from audited Kiomet enum ordering and phrase match arms. EWS is the display key; Ews is the enum spelling.

The helper accepts exact source-default English titles only. It does not identify the current locale or prove deployed translation/version parity. A normal visible exact title, coherent selected own tower and all existing enabled/unlocked/prerequisite/state guards remain mandatory. Unverified Chinese headings and titles stay UNKNOWN. Fixtures demonstrate string/DOM identification, not server acceptance or action reliability. No live or Final outcomes are exposed.
