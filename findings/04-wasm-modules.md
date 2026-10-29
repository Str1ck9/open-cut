# WASM Modules, Device Paths & Electron Security Posture

**Target:** Cricut Design Space v10.9.118 (macOS arm64) · **Method:** brotli decompression, WASM section parsing, `strings`, static grep of renderer/main bundles · 2026-10-27
**Status:** Static survey only. No module was executed or disassembled. Function-level analysis is still open.
**Supersedes:** parts of `01` (§2, §6), `02` (connection-type notes), and `03` (§1 pipeline, §5 flow, §6.3 "next step"). See the inline notes in those files.

## 1. Six Swift→WASM modules (missed in earlier passes)

Location: `unpacked/static-asset/wasm/*.wasm.br` (brotli). A `find -name '*.wasm'` search does not match `.wasm.br`, which is probably why earlier passes missed them. Decompressed copies were made to scratchpad for inspection and are **not** stored in the project. To regenerate: `brotli -d -o <out> <file>.wasm.br`.

| Module | .br | Raw | Code / Data sections | Debug info | Loaded by |
|---|---|---|---|---|---|
| `Bifrost.wasm` | 20 MB | 69.3 MB | 29.0 / 39.2 MB | stripped (no `name`) | `design-space-app/chunk-BYrF6YNd.js`, `design-space-home/main.js` |
| `CriCanvas.wasm` | 20 MB | 67.3 MB | 28.4 / 38.1 MB | stripped | all `canvas-webw-*` workers, `chunk-CfNQc1Ps.js`, home `main.js` |
| `PhysicalCanvas.wasm` | 21 MB | 72.2 MB | 33.0 / 38.4 MB | stripped | `canvas-webw-cricanvas.js` |
| `CriMachineCapabilities.wasm` | 15 MB | 47.4 MB | 11.5 / 35.7 MB | stripped | `chunk-BuWsKJXW.js` |
| `CriTrace.wasm` | 11 MB | 47.4 MB | 21.7 / 4.7 MB | **full DWARF + `name` section (~20 MB)** | `canvas-webw-trace.js`, app/home `main.js` |
| `CriAnalytics.wasm` | 15 MB | 47.7 MB | 11.6 / 35.8 MB | stripped | app/home/about `main.js` |

Common traits (verified on Bifrost and CriMachineCapabilities):
- **Swift compiled to `wasm32-wasi`.** All carry a `.swift1_autolink_entries` custom section, and 3k–13k Swift symbol strings each.
- **Node-API-over-WASM (emnapi-style).** Imports: `napi` ×89, `wasi_snapshot_preview1` ×32–33, `env` ×8 (Bifrost only). Exports are only `memory`, `_initialize`, `malloc`, `free`, `__indirect_function_table`, `napi_register_module_v1`. **The real API is registered at runtime through N-API**, so the method names are in the JS glue and the WASM data section, not the export table.
- `CriTrace.wasm` shipping with full DWARF looks like a debug build that went to production.

## 2. `Bifrost.wasm` — a six-module N-API bundle (incl. the machine layer)

> **[UPDATED]** `Bifrost.wasm` is not one module. Its loader in `chunk-BYrF6YNd.js` instantiates it via emnapi and destructures **six** N-API submodules: `{Bifrost, Runtime, Tesseract, CriRaster, CriGeo, CriSVG}`. The machine module (`Bifrost`) is one of them, and it exports the device-object model for the BIFROST-comm families + Scout (29 types: `DumbledoreDevice`, `ScoutDevice`, `BluetoothLEService`, `TcpIpMdnsDescriptor`, `WifiProvisioningResult`, `CP4100FirmwareUpdate*`, …). Full surface and the loader snippet: `05-data-formats-and-ipc.md` §2 and `analysis/bifrost-wasm-surface.txt`. "Tesseract" is motion/pressure sensing, not OCR. Served over the renderer's custom `cricut-wasm` URL scheme.

The crypto-string census below therefore reflects the whole bundle, not a dedicated session module. The machine-session logic is still the best candidate location for the handshake, but it shares the file with raster/geometry/SVG/sensing code.

String census (157,423 strings ≥6 chars):

| Term | Hits | | Term | Hits |
|---|---|---|---|---|
| `Bifrost` | 849 | | `AES` | 174 |
| `calibrat` | 538 | | `GCM` | 28 |
| `protobuf` | 257 | | `ChaCha` | 21 |
| `Scout` | 122 | | `X25519`/`Curve25519` | 14 |
| `handshake` | 107 | | `P256`/`secp256` | 12 |
| `Gemini` | 3 | | `HKDF` | 7 |

Interpretation (inference, not yet confirmed at the function level):
- This is the strongest candidate for where the Scout/Bifrost **session handshake and AEAD framing** are implemented. The handshake vocabulary and the key-agreement/KDF/AEAD primitives sit together here.
- It runs **in the renderer process** as WASM, not in the native helpers. That contradicts the old README conclusion #5, which said the handshake lives in stripped native Mach-O helpers.
- Several primitives co-occur (AES, GCM, ChaCha, X25519, P-256, HKDF). This pattern fits a general crypto library such as swift-crypto being linked in. **The census alone doesn't show which cipher suite the machine link negotiates.**
- `CriCanvas` and `PhysicalCanvas` show an identical smaller crypto census (AES 36 / GCM 12 / ChaCha 18 / X25519 8 / HKDF 7), which fits the same library being linked into each. Crypto strings alone therefore don't single out Bifrost. **The handshake/Scout/calibration counts do.**

## 3. "Bifrost" is an overloaded name

Don't treat these as one thing:

| Usage | Evidence |
|---|---|
| `communicationType` enum value | `{BIFROST=0, CNV2=1, ODM=2}` in `chunk-BYrF6YNd.js` (see `02` §3) |
| WASM module | `Bifrost.wasm` |
| Firmware/platform version line | "Default true as of **Bifrost 31.0.0**…" (Scout flag text) |
| Calibration subsystem | knife/rotary/theta calibration, buttonless PTC, etc. (`01` §2) |

## 4. Device paths: three groups, not one pipeline

`03` §5 drew a single chain: renderer → main → Bridge 7 → CricutDeviceIO → CricutDevice. The evidence instead shows separate paths chosen per machine family:

```
                    ┌─ Path A: "Bridge (CNV2)" ─────────────────────────────────────────┐
 Angular renderer ──┤   ipcBridge.pluginDeviceCommon* → main → Bridge 7 helper process  │
 (design-space-app) │   (device-common/CricutDevice, local socket, "Bridge 7 frames")   │
                    │   Families with communicationType=CNV2: Explore, Maker, Maker 3,  │
                    │   Explore 3, Joy, Joy Xtra, Venture, Maker 4, Explore 4, presses  │
                    ├─ Path B: CDIO byte link ──────────────────────────────────────────┤
                    │   Bifrost.wasm (in renderer) ⇄ ipcBridge.pluginCdioSend/Receive-  │
                    │   Bytes → main → per-window CDIO process (CricutDeviceIO)         │
                    │   Gemini, Scout, AND communicationType=BIFROST families          │
                    │   (DUMBLEDORE, EROS, GANDALF, PSYCHE) — confirmed, see below      │
                    └─ Path C: Vulcan plugin ── ipcBridge.pluginVulcan* → CricutVulcanDevice ┘
```

Evidence:
- *"Fix: passive auto-connect drove a Gemini down the **Bridge (CNV2) path instead of the CDIO one**…"* (main-strings)
- *"**Bridge-enumerated machines only (Gemini, Scout and Bifrost keep their rules)**: match machines by identity instead of the Bridge 7 per-process key…"* Bridge-enumerated machines are explicitly a different set from Gemini/Scout/Bifrost. ("Per-process key" here is an enumeration handle, **not** a crypto key.)
- *"Cannot send bytes: CDIO process not available for window"* and *"Starting CDIO Plugin for window"*: CDIO is per window, and main relays bytes from the renderer.
- Scout CDIO strings mention BLE advertisement/manufacturer data (Windows packet split) and stored-IP fast-path across networks. So Scout uses BLE and IP via CDIO.
- Preload exposes `pluginCdioStart/Stop/SendBytes/ReceiveBytes/Close`, `pluginDeviceCommonStart/Request/OnResponse`, and `pluginVulcanStart/Request/Response`. These are three distinct native channels.
- **[CONFIRMED]** The Path B assignment for the four `BIFROST` families is no longer inferred. The renderer gates on `isBifrostFamily(t){return …communicationType===wt.BIFROST}`, and `isBifrostFamily||isGeminiFamily` routes to `BifrostDeviceDiscoveryManager` + the CDIO path, while CNV2 families use `OobCnv2ConnectionManager`. The `Bifrost.wasm` `Bifrost` submodule even exports `DumbledoreDevice`/`ErosDevice`/`GandalfDevice`/`PsycheDevice`/`ScoutDevice` with their own BLE/mDNS/WiFi types. See `05` §2–§3. An `_isOdmDevice` getter and `DH_MACHINES_FIX_PICKER_ODM_BIFROST_ROUTING` confirm ODM as a real third routing class (Path A variant).

**Open question:** whether the encrypted "BRDG" frames (`0xCC 0x01…`, "Encrypted BRDG payload too short to contain nonce and authentication tag") protect the **local** Electron↔Bridge 7 socket, the **machine** link, or both. The Scout secure-session flag is about the machine link. The BRDG frame strings sit next to the Bridge 7 socket strings. They may be two separate crypto contexts.

## 5. Electron security posture (not covered in 01–03)

| Item | Evidence | Note |
|---|---|---|
| `contextIsolation: false`, `nodeIntegration: false` | BrowserWindow `webPreferences` literals in `cricut-ele-design-space/main.js` | Preload assigns `window.ipcBridge` directly (no `contextBridge`). This is why REA reported **0** context-bridge APIs and **0** IPC operations, a false negative. |
| Preload surface ≈ 275 string literals | `preload.js` | Includes raw device byte I/O (`pluginCdio*`), machine locks (`lockMachine`, `checkMachineIsLocked`, `disconnectMachinesFromOtherWindows`), `installPlugin`/`uninstallPlugin`, auth refresh, wifi scan, `isSslPinningFailed`. |
| TLS certificate pinning | `setCertificateVerifyProc`, `_isSslPinningFailed` | Relevant to any traffic-capture plan. |
| Hardened-runtime exceptions | `static-asset/apple-app-entitlements.plist` **and confirmed on the `CricutDeviceIO` helper via REA `inspect_signature`**: `allow-jit`, `allow-unsigned-executable-memory`, `disable-library-validation`, `disable-executable-page-protection`, `personal-information.location` | The transport helper itself carries the location entitlement (BLE/WiFi proximity). |
| Code signing | REA `inspect_signature`: **Team ID `25627ZFVT7`, "Developer ID Application: Cricut, Inc."**, notarized, hardened runtime | Developer ID (not App Store) distribution. |
| Custom URL scheme | renderer launched with `--standard-schemes=cricut-wasm --secure-schemes=cricut-wasm --cors-schemes=cricut-wasm --fetch-schemes=cricut-wasm --streaming-schemes=cricut-wasm` | How the `Cri*.wasm`/`Bifrost.wasm` modules are served to the renderer. |
| Renderer sandbox | renderer launched with `--enable-sandbox` | Note the tension with `contextIsolation: false`. |
| Plugin preload | `preload-plugin.js` → `window.CricutApplicationPlugin` {`exitPlugin`, `getCurrentMetaData`, `getConfig`, `onPluginShown`, `onPluginClose`} | — |

## 6. `swift-meta.wasm` (Labs) — purpose resolved

`static-asset/design3/labs/swift-meta.json` is the manifest for `swift-meta.wasm` (14.2 MB). It's a Swift **design-tool plugin host** with parameterized manifests (`apiVersion 0.1`):

| id | Name | Description |
|---|---|---|
| mstoker-pixelize | Pixelize | Fills a grid of cells by checking overlap with artwork |
| mstoker-shapes | Shapes | (placeholder `PLUGIN_DESCRIPTION`) |
| mstoker-vector-fill | Vector Fill | Line/curve fill patterns, for pen drawing |
| warp-to-shape | Warp to Shape | Warps artwork into a target shape |
| dvoss-card-maker | Card Maker | Card template with inserts/envelope |
| mstoker-paper-box | Paper Box Maker | Box templates |
| mstoker-kaleidoscope | Kaleido Scope | Wedge slice + radial duplication |

Loaded by `design-space-app/main.js`.

## 7. Next steps

1. ~~Pull the N-API registration names for `Bifrost.wasm`~~ **[DONE]** See `05` §2 and `analysis/bifrost-wasm-surface.txt`. The remaining piece is the per-method signatures inside each submodule, which needs the WASM data section or a runtime dump.
2. ~~Confirm the Path B assignment for the `BIFROST` families~~ **[DONE]** Confirmed in §4 and `05` §3.
3. Answer the §4 open question (local-socket crypto vs. machine-link crypto) before investing in either native or WASM analysis.
4. **Legal gate:** reconstructing the machine-link handshake is the step most exposed to DMCA §1201 anti-circumvention claims. Get IP counsel's review before function-level work on §2.
