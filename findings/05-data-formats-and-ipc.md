# Data Formats, Bifrost.wasm Surface & IPC Registry

**Target:** Cricut Design Space v10.9.118 (macOS arm64) · **Method:** REA (native `inspect_macho`/`inspect_signature`; JS-recovery and deep-disassembly providers were unavailable, see §5) plus direct static extraction · 2026-10-27
**Scope note:** This covers structure and data formats only. No crypto/handshake methods were enumerated — that work is held pending legal review (see `04` §7, README #6).

## 1. Canvas / cut-job protobuf schema (item: "57 canvas types")

Source: `unpacked/design-space-app/canvas-webw-cricanvas.js` (protobuf.js runtime, minified). Names recovered from protobuf.js **verifier strings** (`<Message>.<field>: <type> expected`) and `field: enum …` typings. Full inventory: `analysis/canvas-protobuf-schema.txt`.

**48 message types** confirmed via verifier strings:

```
AppliedMaterial, Artboard, Assembly, Attachment, AttachmentPlacement, Bitmap,
BitmapMetaData, Boundary, BoundaryExplicit, Cache, CanvasBody, CanvasChangedBody,
Circle, ClipGraphic, Design, DifferenceGraphic, EraseGraphic, FontBody,
FontCharacterImage, Graphic, GraphicContainer, ImageBody, ImageConvertBody,
ImageSourceDetails, ImageUploadBody, Intent, IntersectionGraphic, LayerContourDetails,
LayerDataBody, LayerFill, LayerGraphic, LayerStroke, MaterialClass, PhysicalObject,
Piece, RectF64, Region, StickerizedGraphic, Substrate, Surface, SurfaceImage,
SurfaceRepresentation, SymmetricDifferenceGraphic, TextGraphic, UnionGraphic,
UpdateReasons, WarpedGraphic, Workspace
```

The graphic model is a boolean-op tree: `Graphic` / `GraphicContainer` with `UnionGraphic`, `DifferenceGraphic`, `IntersectionGraphic`, `SymmetricDifferenceGraphic`, `ClipGraphic`, `EraseGraphic`, `WarpedGraphic`, `StickerizedGraphic`, `TextGraphic`, `LayerGraphic`. `CanvasBody` is the document root; `Design`/`Assembly`/`Piece`/`PhysicalObject`/`Substrate`/`Surface` model the physical cut layout.

**26 enum types** referenced as field types:

```
Alignment, CanvasType, Capabilities, ContainmentMode, DefaultPieceLocks, FillBitmapType,
FillRule, FillType, FontType, ImageSourceType, Kind, LayerOperationsUsedSet, LayerOutputType,
LayerPolarity, LockedType, MaterialType, OriginalOutputType, Role, StickerType, StrokeType,
Style, TextMode, TextRenderer, UploadType, UserLocks, VerticalAlignment
```

The `Cut`/`Material` model cited in `01` §2 is present in the same file: `Cut, CutState, CutKiss, CutInteriorShape, CutDie, Material, MaterialType, MaterialId, MaterialClass, MaterialColor`.

> The earlier "57 types" figure is in range but wasn't reproducible as a single count. **48 messages + 26 enums** is the defensible, method-backed number. Field-level schemas (tags, types) were **not** reconstructed: REA's Wakaru-based `recover_javascript_sources` provider is not installed in this environment, and protobuf.js carries no `.proto`. Recovering field tags would need either Wakaru or a runtime dump of `$root` with a debug port.

This is the canvas model (document/graphic/cut geometry). It is **distinct** from the `NativeModel.Bridge` machine-command protobuf (142 names, `03` §4): canvas model = what the renderer edits; Bridge model = what gets sent to a machine.

## 2. Bifrost.wasm is a six-module N-API bundle (revises `04` §2)

The loader in `chunk-BYrF6YNd.js`:

```js
let e = yield fetch(`Bifrost.wasm`),
    {instance:r} = yield WebAssembly.instantiateStreaming(e, s);
let a = u.init(r);
return {Bifrost:At, Runtime:Ji, Tesseract:po, CriRaster:P8, CriGeo:I8, CriSVG:R8} = a
```

- Instantiated through **emnapi** (`napi_register_wasm_v1` / `napi_register_module_v1`), i.e. Node-API compiled to WASM, matching the import census in `04` §1.
- Served over the renderer's custom **`cricut-wasm`** URL scheme (registered standard/secure/cors/fetch/streaming in the renderer process args; also used for the other `Cri*.wasm`).
- **One `.wasm` file registers six N-API submodules:** `Bifrost`, `Runtime`, `Tesseract`, `CriRaster`, `CriGeo`, `CriSVG`. So the "Bifrost.wasm = machine session layer" framing in `04` §2 was too narrow — the machine module is **one of six** in the bundle.

**`Bifrost` submodule — 29 exported types** seen in this chunk (full list: `analysis/bifrost-wasm-surface.txt`):

- Per-family device classes: `DumbledoreDevice`, `ErosDevice`, `GandalfDevice`, `PsycheDevice`, `ScoutDevice`, `ScoutProvisionerDevice`, `BootloaderDevice`
- BLE stack: `BluetoothLEService`, `BluetoothLECharacteristic`, `BluetoothLECharacteristicProperties`, `BluetoothLENotification`, `GenericBluetoothLEPhysicalConnection`, `GenericPhysicalConnection`, `CricutBleAdvertisement`
- Network discovery: `TcpIpMdnsDescriptor`, `TcpIpMdnsTxtRecord`
- WiFi provisioning: `WifiProvisioningResult`, `WifiProvisioningError`, `WifiProvisioningErrorCode`
- Firmware: `CP4100FirmwareUpdateError`, `CP4100FirmwareUpdateProgressStage`, `CP4100FirmwareUpdateResult`
- Config/enums: `ConnectionConfig`, `MovementConfig`, `DeviceType`, `MCUType`, `BifrostInfo`, `PressureToolColor`, `PressureToolDescription`

**Why this matters:** the BIFROST-comm families (Dumbledore/Eros/Gandalf/Psyche) **and** Scout get their whole transport + provisioning object model from this renderer-side WASM — its own BLE, mDNS, and WiFi provisioning — which is why they take the CDIO path and bypass the native `device-common` Bridge (see §3). `ScoutProvisionerDevice` + `WifiProvisioning*` match the Scout stored-IP/mDNS behavior in the main-process strings.

Other submodules: `Tesseract` exposes **motion/pressure sensing** types (`AccelerationMeasurement`, `VelocityMeasurement`, `WeightMeasurement`, `Vector3D`, `MovementSettings1D/3D`, `PressureToolSettings`) — **not OCR**, correcting an earlier guess. `CriRaster`/`CriGeo`/`CriSVG` are accessed through wrappers elsewhere (no direct member access in this chunk); the name split (raster / geometry / SVG) matches the `canvas-webw-*` worker division.

## 3. Device-path routing is confirmed (upgrades `04` §4 from inferred)

The renderer selects the path by machine family's `communicationType`:

| `communicationType` | Families | Discovery / connection | Native path |
|---|---|---|---|
| **BIFROST** | Dumbledore, Eros, Gandalf, Psyche (+ Gemini, Scout by family) | `BifrostDeviceDiscoveryManager` | **CDIO** — `Bifrost.wasm` ⇄ `pluginCdio*` ⇄ `CricutDeviceIO` |
| **CNV2** | Explore, Maker, Maker 3/4, Explore 3/4, Joy, Joy Xtra, Venture, all presses | `OobCnv2ConnectionManager` / `EnumerableDevicesPollingService` ("CNV2-only contract") | **Bridge 7** — `pluginDeviceCommon*` ⇄ `device-common/CricutDevice` |
| **ODM** | (enum value; `_isOdmDevice` getter, `DH_MACHINES_FIX_PICKER_ODM_BIFROST_ROUTING`) | — | third routing class, legacy/ODM |

Confirming evidence (renderer, non-obfuscated):
- `isBifrostFamily(t){return this.getConfiguration(t).communicationType===wt.BIFROST}` and an `isBifrostDevice` selector gate every Bifrost/Gemini branch.
- Discovery: `this._isBifrostFamily||this._isGeminiFamily ? this._bifrostDeviceDiscoveryManager… : this._oobCnv2Connection…`
- Code comment: *"Now a Gemini takes the CDIO discovery path and skips [the CNV2-only `EnumerableDevicesPollingService`]."*
- Flags: `DH_MACHINES_FIX_PICKER_ODM_BIFROST_ROUTING`, `DH_MACHINES_BIFROST_HANDSHAKE_RETRY` (existence noted; internals not analyzed).

## 4. IPC registry (item: main-process handler registry)

> **[RESOLVED 2026-10-27 → see `findings/11-ipc-channel-map.md`.]** The string array was de-obfuscated and the surface mapped. Summary below; full map in `analysis/ipc-channel-map.tsv`.

- **Preload** (`preload.js`) exposes **261** `window.ipcBridge` keys; **145** are `ipcRenderer` forwarders (methods, once resolved: `invoke` 139, `send` 4, `once` 1, `sendSync` 1). The channel is a **caller-supplied argument**, not a preload literal.
- **The renderer** supplies the channel as a constant that maps identity, so **channel string == PascalCase(api)** (confirmed for all 53 call sites found; e.g. `getStatsigOverrides` → channel `GetStatsigOverrides`).
- **Main process** (`main.js`, obfuscated) registers **127 `ipcMain.handle`** and **136 `.on`** handlers on those PascalCase channels. Pairing the main-side handler bodies to channels still needs main.js deobfuscation (its `analyze_javascript_application` times out; documented), but the channel names are now known from the renderer side.
- The native-plugin channels (`pluginCdio*`, `pluginDeviceCommon*`, `pluginVulcan*`, `pluginLocalData*`, `pluginSystemFont*`, `pluginSystemPrinter*`, `pluginPathOperation*`) are mapped in finding 11 §2.1.

## 5. REA native inspection (provenance for `03`'s helper table)

Confirmed against the installed app. **Correction:** REA's **Ghidra provider is installed and works** — it rejects only *universal* Mach-O, so each binary must be thinned to a single arch first (`lipo -thin arm64 <bin> -output <slice>`) and then opened. This was demonstrated on the `CricutDeviceIO` arm64 slice (open succeeded, Ghidra auto-analysis ran). Hopper and IDA are genuinely absent/unconfigured. Procedure-level analysis is therefore available for structural work; the crypto/handshake paths stay behind the legal gate.

Header/signature tools (provider-free) need no thinning:

`CricutDeviceIO` (transport), `inspect_macho` + `inspect_signature`:
- arm64 slice links **libswiftCore + CoreBluetooth + IOBluetooth + IOKit + Security + libc++** → Swift (BLE) over C++ (libusbp), as `03` §2 said. Built **SDK 26.4, min macOS 11.0**, rpaths `/usr/lib/swift` + `@executable_path`.
- Signed: **Team ID `25627ZFVT7`, "Developer ID Application: Cricut, Inc."**, notarized, hardened runtime.
- Helper entitlements (same risky set as the app plist): `allow-jit`, `allow-unsigned-executable-memory`, `disable-executable-page-protection`, `disable-library-validation`, `personal-information.location`.

Running helper versions (from the live process list): `device-common/CricutDevice v6.12.13` (launched `--new-comm-lib`), `CricutDeviceIO 3.18.0-alpha3`. Hashes for all 12 helpers: `analysis/evidence/native-binaries.sha256`.

**Ghidra deep analysis works (demonstrated).** With a thinned arm64 slice (`lipo -thin arm64 CricutDeviceIO -output CricutDeviceIO.arm64`), REA's **Ghidra v12.1.4** provider imported and auto-analyzed it: **11,991 procedures, 36,248 strings, 53 segments**, including Swift reflection sections (`__swift5_types`, `__swift5_fieldmd`, `__swift5_typeref`, …) and ObjC metadata. So `search_procedures`, `analyze_function`, `get_call_graph`, and Swift-type recovery are all available on these binaries once thinned — the earlier "deep providers unavailable" note was wrong. The only remaining constraints are (a) thin each universal binary first, and (b) the legal gate on crypto/handshake functions.

A first `analyze_swift_types` pass on the slice (137 Swift class procedures) **confirmed the C++/Swift split in the transport layer**: only BLE is Swift (the `btle_corebluetooth` CoreBluetooth wrapper — classes `Adapter`/`Device`, delegates, and a read/write/notify op model); USB/BT-classic/IP are C++ and emit no Swift metadata. Full structure in `03` §2a. This was structural transport work only — no crypto functions were decompiled.

## 6. Artifacts added this pass

- `analysis/canvas-protobuf-schema.txt` — 48 messages + 26 enums + Cut/Material names
- `analysis/bifrost-wasm-surface.txt` — the six submodules and the Bifrost module's 29 types
- `analysis/evidence/bridge.log` — the 6-frame capture `03` §3 relies on
- `analysis/evidence/native-binaries.sha256` — hashes/sizes/arches for the 12 native helpers
