# Cricut Design Space — REA Analysis Findings

**Target:** Cricut Design Space v10.9.118 (desktop, macOS arm64)
**Bundle ID:** com.cricut.design
**Method:** REA 6.7.0 static analysis + manual bundle inspection
**Analyst:** DATA (OpenClaw) · 2026-10-27
**Status:** ~~Ongoing — deep REA pass on obfuscated main process still running~~ **[REVISED 2026-10-27]** Both REA main-process runs **timed out** (300 s; then 900 s with a 4 GB heap) and produced only partial graphs. The string-array dump (`analysis/main-strings.txt`) replaced them.

> **This document is partly superseded.** Where it conflicts with `03`/`04`/`05`, those win. Corrections are marked **[REVISED]** inline. Main overrides: machine I/O is **not** in the main process (03 §1, 04 §4, 05 §3). Six WASM modules were missed, and `Bifrost.wasm` is itself a six-module bundle (04 §1, 05 §2). The preload surface is far larger than described here (04 §5, 05 §4). The canvas protobuf schema is recovered (05 §1). swift-meta.wasm's purpose is resolved (04 §6).

## 1. Application Architecture

Electron app, three distinct code tiers:

| Layer | Path | Size | Protection |
|---|---|---|---|
| Main process | `cricut-ele-design-space/main.js` | 10.0 MB | javascript-obfuscator (string-array rotation, `_0x` identifiers) |
| Preload bridge | `cricut-ele-design-space/preload.js` | 26 KB | Light obfuscation (same family, readable strings) |
| Renderer | `design-space-app/` (Angular **22.2.2** [REVISED: was "15+"]) | **72** chunks (app), 32 (home), 10 (tabs) [REVISED: was "~40"] | Minified, NOT obfuscated — full i18n/strings readable |
| Canvas workers | `canvas-webw-*.js` (7 files) | **3.2 MB** [REVISED: was ~2.6] | Minified, protobuf schemas extractable |
| Plugins | `plugins/@cricut/` | **441** files [REVISED: was 540] | Plain webpack bundles |
| WASM (Swift) | `static-asset/wasm/*.wasm.br` (6 modules) | 102 MB br / 351 MB raw | **[REVISED: missing from the original]** See `04` §1 |

Also present: `config.bin` (6.7 KB, encrypted/binary — main-process config, likely key or license material).

### Bundle sections (asar, 3,213 entries = 2,942 files + directories; `unpacked/` = 424 MB on disk)
- `design-space-app` — main Angular canvas application
- `design-space-home` — home/dashboard app
- `plugins` — lazy-loaded feature plugins (e.g. monogram maker)
- `static-asset/design3/`: translations under `design3/translation/` (**[REVISED]** 23 flat locale JSONs, 6,543 keys each, plus `translation/featureFlags.json` — an **i18n bundle of 58 feature-grouped UI string sets** (MARS, NEW_FEATURES, MACHINE_CARE, …), *not* the Statsig flag definitions; the actual `DH_*` flags live in the main-process strings. The "33 modules" structure couldn't be reproduced), platform assets, Labs WASM
- `static-asset/wasm/`: **[REVISED: added]** six Swift→WASM modules (`04` §1)
- `design-space-login`, `design-space-tabs`, `design-space-performance-monitor`

## 2. Machine Communication (the crown jewels)

> **[REVISED] Superseded by `03` §1–2 and `04` §2/§4.** Machine I/O runs through native helper processes (Bridge 7 / CDIO / Vulcan), and the Bifrost session layer is very likely `Bifrost.wasm` in the renderer.

**USB vendor ID:** `0x24AA` (decimal 9390). ~~confirmed in renderer main.js and obfuscated main process~~ **[REVISED: unverified]** The 80 `0x24aa` hits in obfuscated `main.js` are normal hex index literals the obfuscator emits, and there are **0** standalone `9390` hits in renderer `main.js`. The value may be right, but these files don't prove it.
**Transports:** USB, Bluetooth classic, BLE, TCP/IP (see `03` §2). ~~"Ryzen" USB bugstring suggests libusb-style native USB on Windows~~ **[REVISED]** "Ryzen" is a UI flag, `isAffectedByRyzenIssue`, that shows a connection-help link. It says nothing about the USB stack.

**Cut-plan protocol:** `canvas-webw-cricanvas.js` contains protobufjs schemas for the cut job model:
- `Cut`, `CutState`, `CutKiss`, `CutInteriorShape`, `CutDie`, `CutDieCutEdge`
- `Material`, `MaterialType`, `MaterialId`, `MaterialClass`, `MaterialColor`
- Canvas model: `CanvasType`, `FillType`, `StrokeType`, `LayerOutputType`, `ImageSourceType`, `UploadType`, `FontType`, `StickerType`

**Renderer-side native blobs** (embedded base64, decoded):
- libheif (HEIF/AVIF image decode) + libde265 (HEVC decode)
- `RegionGeometry_*` structures (Point/Rectangle/Ellipse/Polygon/ReferencedMask/InlineMask) — composition geometry
- A 164 KB JPEG "Manual Alignment Pattern" — Print Then Cut calibration asset
- Full libc++/libc++abi runtime symbols

**Calibration subsystem codename: BIFROST.** Handles: knife-blade calibration, rotary blade, Print Then Cut fiducial scanning ("buttonless PTCC"), bilinear calibration, theta calibration, test-cut flows, material prefeed.

## 3. Supported Machine Families (from i18n)

> **[REVISED]** Partial. The full mapping (25 families, 72 machine types, including Maker 4 = NEWT, Explore 4 = RIDDLE, EasyPress 3 = ATMOSPHERE, Hat Press = BROOKLYN) is in `02-machine-codenames.md`.

- Maker series, Explore series, Joy, Venture
- Autopress, EasyPress / EasyPress 2, Mug Press, Cuttlebug (cartridge adapter)
- Cartridge Adapter legacy support

## 4. Cloud & Monetization Surface

**APIs:** `apis.cricut.com` (public + claims endpoints), `design.cricut.com`, `staticcontent.cricut.com`, CloudFront CDN pair
**Payments:** Stripe (stripe.com + m.stripe.com/network beacons)
**Subscriptions:** Cricut Access gating throughout (i18n: ACCESS_EXCLUSIVE_REQUIRE_SUBSCRIPTION)
**Analytics/flags:** Statsig (feature flags exposed via preload bridge), Braze (engagement)
**AI features:** Chat-to-Make, chatbot assets, "GenerateAI" metadata buttons (title/description/tags AI generation for templates)

## 5. Preload Bridge (IPC surface)

`window.ipcBridge` exposes: appConfig sync/settle, feature flags, Statsig overrides, app-update events, external logging, spell-check word suggestions, cache clearing. Channel names pass through as arguments — the obfuscated main process holds the handler registry.

**[REVISED] Badly understated.** `preload.js` holds about 275 distinct string literals. These include raw device I/O (`pluginCdioSendBytes/ReceiveBytes`, `pluginDeviceCommonRequest`, `pluginVulcanRequest`), machine locking (`lockMachine`, `checkMachineIsLocked`, `disconnectMachinesFromOtherWindows`), auth refresh, `installPlugin`/`uninstallPlugin`, wifi scan, and `isSslPinningFailed`. Windows run with `contextIsolation: false`, and preload assigns `window.ipcBridge` directly, which is why REA reported 0 bridge APIs. See `04` §5.

## 6. Experimental

`static-asset/design3/labs/swift-meta.wasm` — 14.2 MB **Swift-language WebAssembly** module (Swift stdlib symbols present). "labs" path = feature-flagged experiment. ~~Purpose not yet determined (name suggests metadata processing).~~ **[REVISED]** Resolved by the adjacent `swift-meta.json`: it's a Labs **design-tool plugin host** (Pixelize, Shapes, Vector Fill, Warp to Shape, Card Maker, Paper Box Maker, Kaleidoscope). See `04` §6.

## 7. Implications for a GUI Recreation

1. **UI layer is reproducible.** The Angular renderer is minified but not obfuscated; all workflows, i18n (**[REVISED]** 23 locales × 6,543 flat keys; ~~33 modules × 22 locales~~), and data-test-ids are extractable. A clean-room GUI can be modeled on these flows.
2. **Machine protocol is the moat.** ~~USB/Bluetooth device I/O lives in the obfuscated 10 MB main process. REA analysis (in progress) targets this.~~ **[REVISED]** Device I/O is in native helper processes, and the Bifrost session layer is likely `Bifrost.wasm` (`04`). Prior art for older machines exists (cutcutgo, FreeKnife, grasshopper repos).
3. **Cut-job format is protobuf.** The schema is embedded and extractable from cricanvas worker — this is the language the GUI speaks to the machine layer.
4. **Cloud dependency is real but bounded** — auth, content, and subscriptions are cloud; the cut pipeline (canvas → protobuf cut plan → USB/BT) is local.
5. **Legal caution:** Cricut has litigation history (sued Make The Cut / Sure Cuts A Lot). Clean-room discipline required: document behavior, never ship their code/assets.

## Files

- `analysis/asar-filelist.txt` — full 3,213-file inventory
- `unpacked/` — extracted asar (424 MB)
- `analysis/rea-main-process.md`, `-v2.md`: REA main-process runs (**[REVISED]** both timed out; partial graphs only, with lossy `[object Object]` cells)
