# open-cut — Clean-Room Interoperability Notes for Cricut Design Space

> **Unofficial and unaffiliated.** This project is not associated with, endorsed by, or connected to Cricut, Inc. "Cricut" and related product names are trademarks of their respective owners, used here only for identification (nominative fair use). This repository documents *observed behavior and interfaces* of Cricut Design Space for interoperability and security-research purposes, under clean-room discipline. It contains **no** Cricut source code, assets, keys, or decompiled binaries — those are intentionally excluded (see "Analysis Artifacts" below). No circumvention of technical protection measures is provided: the protected machine-link surfaces are documented only as *out-of-scope* boundaries (see `SPEC.md` §0.3). Reverse-engineering for interoperability carries legal risk; consult IP counsel before building on it.

**Target analyzed:** Cricut Design Space v10.9.118 (macOS, Electron, arm64)
**Tooling:** REA 6.7.0 (`rea-agents`) + manual Mach-O symbol analysis + WASM section/string survey
**Started:** 2026-10-27 · **Revised:** 2026-10-27 (verification pass; corrections are marked **[REVISED]** in each finding)

## Documentation

**→ [`SPEC.md`](SPEC.md) — consolidated clean-room behavioral specification** (all nine findings synthesized into one hand-off document for an implementation team, with the protected surfaces marked out of scope). Start here.

The nine findings below are the detailed working notes behind the spec:

| File | Contents |
|---|---|
| `findings/01-app-architecture.md` | App structure, Electron layers, cloud/monetization surface. **Partly superseded** by 03/04 (see header). |
| `findings/02-machine-codenames.md` | **25 families / 72 machine types** → product mapping, comm type, numeric IDs (incl. Maker 4 = NEWT, Explore 4 = RIDDLE, and the unreleased GEMINI, SCOUT, BIFROST-comm cutters) |
| `findings/03-machine-protocol.md` | Bridge 7 architecture, transports, AEAD frame protocol, 142 machine-command protobuf names |
| `findings/04-wasm-modules.md` | **Six Swift→WASM modules**, the three device paths, Electron security posture, swift-meta Labs plugins |
| `findings/05-data-formats-and-ipc.md` | **Canvas protobuf schema (48 msgs + 26 enums)**, `Bifrost.wasm` = a 6-module N-API bundle (29 device types), confirmed BIFROST/CNV2/ODM routing, IPC registry, REA native-inspection provenance |
| `findings/06-native-command-layer.md` | **`CricutDevice` dispatch architecture** (Ghidra): `CommandTypes::get_command` resolver + `is_in_cutting_session` session gate; pure C++, method symbols stripped; crypto handlers left behind the legal gate |
| `findings/07-local-data-schema.md` | **`CricutLocalData` offline cache**: SQLCipher-encrypted `metadata.db`; entitlement table (offline Cricut Access gating) + canvas/image/font/material schema; 151-message CRUD API |
| `findings/08-native-helpers.md` | **PathOperation** (boolean/slice/vector-fill/trace geometry; design-asset encrypt/decrypt flagged, not opened), **SystemFont** (CoreText glyph outlines + spell-check), **SystemPrinter** (Print-Then-Cut host printing + fiducials via ImageMagick) |
| `findings/10-protobuf-schemas.md` | **Full protobuf field tags** (Gap 1): native descriptors decoded → protoc-validated `.proto` (7 binaries), validated 15/15 vs slicebug; canvas model (52 msgs/256 fields) from protobuf.js; §0.3 surfaces redacted |
| `findings/11-ipc-channel-map.md` | **IPC map** (Gap 2): 145 forwarders, string-array de-obfuscated → methods; channel == PascalCase(api); handler groups |
| `findings/12-cnv2-wire-protocol.md` | **CNV2 wire protocol** (Gap 3): prior-art byte opcodes (FreeKnife/libcutter/slicebug), PB↔wire first-pass mapping, hardware capture plan |
| `findings/09-command-layer-next-vs-current.md` | **`device-common` 6.12.13 vs `device-common-next` 7.0.6**: superset refresh (0 removed, ~45+ new messages, +7.5% code), same dispatch engine, snake_case→camelCase/Api field shift; heat-press telemetry + richer materials/tools |

## Analysis Artifacts (`analysis/`)

| File | Contents |
|---|---|
| `asar-filelist.txt` | Full asar inventory: 3,213 entries (2,942 files + dirs), matches `unpacked/` exactly |
| `main-strings.txt` | 21,291 lines (21,199 unique) decoded from the obfuscated main-process string array. **Has NUL/control bytes, so use `LC_ALL=C grep -a`**. Plain `grep` silently returns nothing. |
| `deviceio-symbols-full.txt` | 17,446 symbols from CricutDeviceIO (transport layer) |
| `bridge-protobuf-messages.txt` | 142 cleaned `NativeModel.Bridge` names with a source column (both / binary-only / js-only) |
| `bridge-protobuf-messages.raw.txt` | Original 170-line `strings(1)` output, including tag-byte artifacts |
| `canvas-protobuf-schema.txt` | Canvas/cut-job model: 48 message types + 26 enums + Cut/Material names (from protobuf.js verifier strings) |
| `bifrost-wasm-surface.txt` | `Bifrost.wasm`'s six N-API submodules and the `Bifrost` module's 29 device-object types |
| `localdata-schema.txt` | `CricutLocalData` offline-cache schema: entitlement + canvas/image/font/material tables, 151-message API |
| `native-helpers-schema.txt` | PathOperation / SystemFont / SystemPrinter protobuf API surfaces (geometry, fonts, Print-Then-Cut) |
| `protos/<binary>/*.proto` | **Recovered, protoc-validated protobuf schemas with full field tags** (native descriptors + canvas model); §0.3 surfaces redacted |
| `ipc-channel-map.tsv` | bridge API → ipcRenderer method → channel (PascalCase) → handler group, for 145 forwarders |
| `tools/` | `pbscan.py` (native FileDescriptorProto decoder), `pbjs_extract.py` (protobuf.js tag extractor), `ipc_map.py` (preload de-obfuscator) |
| `evidence/bridge.log` | 6 captured Bridge 7 frames (verifies the `0xCC 0x01` + u32-LE-length layout) |
| `evidence/native-binaries.sha256` | SHA-256, size, arch for all 12 native helper binaries |
| `rea-preload.md` | REA static analysis of preload.js. Note: reports 0 bridge APIs/IPC, a false negative caused by `contextIsolation: false` (see 04 §5) |
| `rea-main-process.md`, `rea-main-process-v2.md` | REA runs that **timed out** (300 s / 900 s). Partial graphs only, with lossy `[object Object]` cells |

> **Omitted from this public repository (by design):** `main-strings.txt`, `deviceio-symbols-full.txt`, `bridge-protobuf-messages.raw.txt`, `asar-filelist.txt` and the `rea-*.md`/`rea-*.err` REA dumps are verbatim or near-verbatim reproductions of the target's binary. They are retained locally for the authors' reference but are **not redistributed here**, to preserve clean-room integrity and avoid redistributing copyrighted code. Findings that cite them remain valid; only the derived, behavior-level artifacts (schemas, maps, evidence hashes) are published.

**Evidence now captured:** `analysis/evidence/bridge.log` (frame layout, 03 §3) and `analysis/evidence/native-binaries.sha256` (12 helper hashes). The native binaries themselves stay in `/Applications/…/plugins/` (not copied — proprietary).

## Key Conclusions (for GUI recreation)

1. **GUI layer: reproducible.** The Angular 22 renderer is minified but readable. Workflows, i18n (23 locales under `static-asset/design3/translation/`), and the `DH_*` Statsig feature-flag descriptions (in the main-process strings) are all extractable. (`translation/featureFlags.json` is an i18n bundle of feature-grouped UI strings, not the flag definitions.)
2. **Machine I/O: native, out of process, three paths — confirmed.** The renderer routes by family `communicationType`: `CNV2` → Bridge 7 helper (`device-common/CricutDevice`); `BIFROST` (Dumbledore/Eros/Gandalf/Psyche) + Gemini + Scout → per-window CDIO link (`CricutDeviceIO`) driven by `Bifrost.wasm`; `ODM` is a third class; Vulcan has its own plugin (05 §3, 04 §4).
3. **[REVISED] Protocol: protobuf over AEAD-encrypted frames.** Frame layout **verified** from `analysis/evidence/bridge.log`: `0xCC 0x01` + u32-LE length + encrypted payload. The cipher **mode is unconfirmed** (no `GCM` string in the main process; ChaCha/ARX code also present). A mandatory secure session is **confirmed only for Scout on Bifrost firmware ≥ 31.0.0**; whether that machine session and the local Bridge 7 frame encryption are the same context is still open.
4. **Cut model: documented.** Canvas protobuf model — **48 message types + 26 enums** recovered (05 §1) — plus 142 machine-command names (95 confirmed in both native and JS).
5. **[REVISED] Next step if pursuing:** the machine module is the `Bifrost` submodule inside **`static-asset/wasm/Bifrost.wasm.br`** (a six-module N-API bundle; 05 §2), renderer-side Swift→WASM with 107 `handshake` strings. Its device-object surface is recovered; the remaining work is per-method signatures / the handshake itself. **This is the legal-gate item (conclusion 6)** — not done. (Tooling is available: REA's **Ghidra v12.1.4** works on these binaries once thinned to one arch — demonstrated on `CricutDeviceIO`, 11,991 procedures; Hopper/IDA absent. So the blocker here is legal, not tooling.)
6. **Legal:** Cricut has litigated against protocol re-implementors (Make The Cut, Sure Cuts A Lot). Clean-room discipline is mandatory. Reconstructing the machine-link handshake is the step most exposed to DMCA §1201 anti-circumvention claims, so **get IP counsel's review before function-level work on conclusion 5.** Don't commit or share `unpacked/` (proprietary code/assets) or `screenshots/` (they contain account PII).
