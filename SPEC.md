# Cricut Design Space — Clean-Room Behavioral Specification

**Derived from:** Cricut Design Space v10.9.118 (macOS, Electron, arm64) · **Compiled:** 2026-10-27
**Consolidates:** `findings/01`–`09` · **Detail/evidence:** the `findings/` and `analysis/` files referenced per section.

---

## 0. Purpose, method, and boundary

### 0.1 What this document is
A behavioral specification of Cricut Design Space's structure, interfaces, and data formats, written so a separate implementation team could build a **compatible design/cut application** working only from this document — i.e. the hand-off artifact of a clean-room process. It describes **what** the software does and **what interfaces/formats** it uses, observed from the shipped build. It does **not** reproduce Cricut's source code, assets, keys, or protected algorithms.

### 0.2 Clean-room discipline (binding on any implementation)
- This spec records **observed behavior and interface facts only**. No proprietary source, obfuscated or not, is copied into it.
- Implementers working from this document must not themselves read Cricut's code, assets, or keys — the point of the two-team split.
- Cricut-owned **assets** (images, fonts, SVGs, translations, machine art) are **not** redistributable. Implementations supply their own.
- Cricut has litigated against protocol re-implementors (Make The Cut, Sure Cuts A Lot). Clean-room discipline is mandatory.

### 0.3 The protected boundary — NOT specified here
The following were deliberately **not reverse-engineered** and are **out of scope** for this spec. Re-implementing them is the step most exposed to DMCA §1201 anti-circumvention claims and requires **legal counsel sign-off** before any work:
1. **The machine-link secure-session handshake** (AEAD-encrypted Bridge frames; mandatory for Scout on Bifrost firmware ≥ 31.0.0). §5.3.
2. **The SQLCipher key** for the local database. §8.1.
3. **Design-asset encrypt/decrypt** in PathOperation and `PBCartridgeDataEncData`. §9.1.

A compatible product that only drives **older, non-session-crypto machines** (Explore/Maker-era, CNV2) and supplies its own content may avoid (1); it must still be reviewed. This spec gives everything up to that boundary and stops.

### 0.4 Confidence
Facts are marked **[C]** confirmed (multiple sources / Ghidra / verified), **[O]** observed (single reliable source), **[I]** inferred. Unmarked prose is confirmed.

---

## 1. System architecture

Electron desktop app with three code tiers plus out-of-process native helpers. [C]

| Tier | Location | Form | Reproducible? |
|---|---|---|---|
| Main process | `cricut-ele-design-space/main.js` (9.6 MB) | Obfuscated JS (string-array rotation) | Behavior yes; verbatim no |
| Preload bridge | `cricut-ele-design-space/preload.js` | Light obfuscation; ~277 bridge APIs | Yes (§7) |
| Renderer | `design-space-app/` etc. | **Angular 22.2.2**, minified not obfuscated | Yes — workflows/i18n/flags all readable |
| Canvas workers | `canvas-webw-*.js` (7) | Minified; protobuf models | Yes (§6) |
| WASM modules | `static-asset/wasm/*.wasm.br` (6) | Swift→wasm32-wasi, emnapi | Interfaces yes; internals no |
| Native helpers | `…/Resources/plugins/*` (12 binaries) | C++/Swift Mach-O, Developer-ID signed (Team `25627ZFVT7`) | Interfaces/schemas yes; crypto no |

**Separation of concerns:** the renderer edits a protobuf canvas model; the Electron main process coordinates sessions/flags/plugins and **relays bytes**; native helpers do all device I/O, geometry, fonts, printing, and local storage. The main process is a coordinator, **not** the device driver. [C] *(findings 01, 04)*

---

## 2. Machine catalog

25 families / 72 machine types. Full table with numeric IDs: `findings/02`. [C]

### 2.1 Communication-type enum (drives everything downstream)
`communicationType = { BIFROST = 0, CNV2 = 1, ODM = 2 }`. Each family declares one. [C]

### 2.2 Supported cutting machines (shipping)
| Family | Product | Comm | Notes |
|---|---|---|---|
| EXPLORE | Explore / One / Air / Air 2 | CNV2 | + Bluetooth-module dongle |
| MAKER | Maker | CNV2 | |
| SCAMANDER | Maker 3 | CNV2 | |
| VOLDEMORT | Explore 3 | CNV2 | |
| NEWT | **Maker 4** | CNV2 | |
| RIDDLE | **Explore 4** | CNV2 | |
| CUPID | Joy | CNV2 | BT-only |
| MARS | Joy Xtra | CNV2 | BT-only |
| MORPHEUS | Venture | CNV2 | networked |
| DUMBLEDORE/EROS/GANDALF/PSYCHE | (unreleased cutters) | **BIFROST** | session-crypto families |
| GEMINI, SCOUT | (unreleased) | — (CDIO path) | Scout enforces secure session |

### 2.3 Heat presses (all CNV2)
EasyPress 2 (EASY_PRESS2), EasyPress 3 (ATMOSPHERE), Hat Press (BROOKLYN), Mug Press (ROOTBEER), AutoPress (VULCAN), AutoPress 2 (HYDROGEN), DTF EasyPress (DTF). Numbered-voltage variants (NEUTRON/PROTON/QUARK) and newest IDs (TITAN/RANGER/SPRITE/VOYAGER) are unreleased. [C/I]

### 2.4 Connection types
`USB_CT`, `BLUETOOTH_CT` (classic), `BLE_CT`, `IP_TCP_CT` (mDNS-discovered). [O]

---

## 3. Device-path routing (required behavior)

The renderer selects a native path per family `communicationType`. [C] *(finding 05 §3)*

```
family.communicationType ==
  CNV2    → Bridge 7:  ipcBridge.pluginDeviceCommon* → main → device-common/CricutDevice
  BIFROST → CDIO:      Bifrost.wasm (renderer) → ipcBridge.pluginCdio{Send,Receive}Bytes → main → CricutDeviceIO
            (also Gemini, Scout — selected by isBifrostFamily||isGeminiFamily)
  (Vulcan pod/press)  → ipcBridge.pluginVulcan* → plugin-vulcan/CricutVulcanDevice
```

An implementation must route discovery and I/O the same way: CNV2 machines enumerate via a polling/"Bridge-enumerated" service keyed by device identity; BIFROST/Gemini/Scout enumerate via a BLE/mDNS discovery manager fed by the CDIO transport.

---

## 4. Transport layer

Four transports behind one interface (`connect`/`disconnect`/`send_bytes`/`receive_bytes`/`get_connection_state` + async). [C] *(findings 03, 05)*

| Transport | Mechanism | Discovery |
|---|---|---|
| USB serial | libusbp (C++). Cricut USB **VID 0x24AA** [O, unverified] | `usb_serial_device_inquirer` |
| USB HID | `create_usb_hid_async_transport` | — |
| Bluetooth classic | `bluetooth_serial_transport` + pairing | enumerate devices |
| **BLE** | **Swift `btle_corebluetooth`** over CoreBluetooth (the only Swift transport) | manufacturer-data scan |
| TCP/IP | `ip_tcp_transport` + keepalive | **mDNS** (`tcp_ip_mdns_device_inquirer`) |

### 4.1 BLE adapter model (confirmed via Ghidra, finding 03 §2a)
A generic GATT client — scan → connect → discover services/characteristics → read/write/notify — carrying the Cricut protocol as characteristic payloads. Classes `Adapter` (CBCentralManager) and `Device` (CBPeripheral); op model `{Discovery,Read,Write,Notify}Request`; shared types `DeviceId`, `Service`, `Characteristic`, `AdvertisementData`, `ScanningOptions`, `DeviceConnectionState`, `PairingStatus`. No machine-specific logic lives here.

### 4.2 Bifrost.wasm device object model (renderer-side, finding 05 §2)
For BIFROST/Scout, the renderer owns the device objects in `Bifrost.wasm` (a six-submodule N-API bundle: `Bifrost, Runtime, Tesseract, CriRaster, CriGeo, CriSVG`, served over the `cricut-wasm` URL scheme). The `Bifrost` submodule exports 29 types incl. `DumbledoreDevice`/`ScoutDevice`/`ScoutProvisionerDevice`, its own `BluetoothLE*` stack, `TcpIpMdns*`, `WifiProvisioning*`, and `CP4100FirmwareUpdate*`. Full list: `analysis/bifrost-wasm-surface.txt`.

---

## 5. Machine protocol

### 5.1 Bridge frame envelope (CNV2 path, verified — finding 03 §3)
Length-prefixed frames on the Electron↔Bridge-7 socket:
```
byte 0-1 : 0xCC 0x01            magic + protocol version
byte 2-5 : <len> 00 00 00       payload length, u32 LITTLE-ENDIAN (= total - 6)
byte 6+  : ENCRYPTED PAYLOAD     (nonce + ciphertext + auth tag)
```
Verified against 6 captured frames (`analysis/evidence/bridge.log`): 202/172-byte request/response pairs, lengths 196/166.

### 5.2 Command vocabulary
The payload carries protobuf `NativeModel.Bridge.PB*` messages. **Complete field-level schemas recovered** (finding 10): the machine-command model spans 10 `.proto` files — `NativeModel.Bridge` (70 msgs / 653 fields), `Commands` (28/172), `Machines` (18/436, incl. the `PBMachineType` family-ID enum), `Force`, `Devices`, `Backlash`, `Analytics`, `CustomerTheta`, `Learning`, `BridgeEnums` — emitted as protoc-validated `.proto` in `analysis/protos/CricutDevice/`, corroborated 15/15 against slicebug's independent reconstruction. [C] Covers the cut pipeline (`PBMatCutExecutionPlan`, `PBCutExecution`, `PBDrawVector(s)`, path sorting), materials/pressure/force, calibration (theta, fiducial, Print-Then-Cut), machine state/status, tools, and family-specific origin commands. The handshake key-exchange fields (`PBCommonBridge` 87/88) are **redacted** (§0.3). `device-common-next` (7.0.6) adds a `bridge.proto.device.{Session,Registry,Message}` transport layer (finding 10 §1.2).

Dispatch (native, C++ `CricutDevice`, finding 06): a `CommandTypes::get_command(enum)` resolver maps a command-type to a handler; `CricutDevice::is_in_cutting_session(CommandType)` gates commands by machine state (a static `cutCommands` set). Class method symbols are stripped; the enum→handler table is not enumerated here.

### 5.3 Secure session — **PROTECTED, NOT SPECIFIED** (§0.3)
The payload is an AEAD construction (nonce + auth tag; cipher **mode unconfirmed** — AES and ChaCha/ARX primitives both present). A mandatory encrypted session is **confirmed for Scout on Bifrost firmware ≥ 31.0.0** (flag `DH_MACHINES_SCOUT_SECURE_SESSION`; disabling it fails all Scout commands on ≥31.0.0). The handshake/key-exchange is the candidate contents of `Bifrost.wasm` (107 `handshake` strings) and is **the clean-room boundary**. Do not implement without counsel.

### 5.4 Build variants (finding 09)
Two command-layer builds ship, flag-selected: `device-common` **6.12.13** (active) and `device-common-next` **7.0.6** (staged). 7.0.6 is a strict superset (0 messages removed, ~45+ added: heat-press telemetry, device-identity serialization, analytics+entitlement, richer materials/tools/firmware), same dispatch engine, with field naming shifting snake_case → camelCase/`Api`-style (closer to cloud REST shapes).

---

## 6. Canvas / cut-job data model

The document/graphic model the GUI edits and serializes (protobuf.js in `canvas-webw-*.js`). **52 messages with full field tags** recovered and protoc-validated: `analysis/protos/canvas-model.proto` (+`-fields.tsv`, finding 10 §2); 26 enum value-sets in `analysis/canvas-protobuf-schema.txt`. [C] *(findings 05 §1, 10)* Enum-typed fields decode as `int32` (wire-identical); maps and repeated fields are resolved.

- **Document:** `CanvasBody` (root) → `GraphicContainer`/`Graphic`.
- **Boolean-op tree:** `UnionGraphic`, `DifferenceGraphic`, `IntersectionGraphic`, `SymmetricDifferenceGraphic`, `ClipGraphic`, `EraseGraphic`, `WarpedGraphic`, `StickerizedGraphic`, `TextGraphic`, `LayerGraphic`.
- **Physical layout:** `Design`, `Assembly`, `Piece`, `PhysicalObject`, `Substrate`, `Surface`, `Material*`.
- **Enums:** `CanvasType`, `FillType`, `StrokeType`, `LayerOutputType`, `ImageSourceType`, `UploadType`, `FontType`, `StickerType`, `MaterialType`, … (26).

This renderer-side model is distinct from the §5.2 machine-command model: canvas = what is edited; Bridge = what is sent to the machine. A cut pipeline converts the former to the latter.

---

## 7. IPC surface (renderer ⇄ main)

`window.ipcBridge` exposes **261** keys (preload), of which **145 are `ipcRenderer` forwarders** (methods resolved: `invoke` 139, `send` 4, `once` 1, `sendSync` 1); the main process registers **127 `ipcMain.handle` + 136 `.on`** handlers. [C] **Channel resolution (finding 11):** forwarders pass a caller-supplied channel, and the renderer supplies `D0.<Member>` constants that map **identity** — so **channel string == PascalCase(api)** (confirmed for all 53 call sites found; `analysis/ipc-channel-map.tsv`). Functional groups an implementation must provide:
- **Device:** `pluginCdio{Start,Stop,SendBytes,ReceiveBytes,Close}`, `pluginDeviceCommon{Start,Request,OnResponse,Stop}`, `pluginVulcan{Start,Request,Response,Stop}`.
- **Local data / fonts / printing / path ops:** `pluginLocalData*`, `pluginSystemFont*`, `pluginSystemPrinter*`, `pluginPathOperation*` (§§8–9).
- **App:** config/feature-flags (Statsig), auth refresh, window/tab management, logging, spell-check, machine lock/unlock, wifi scan, SSL-pin status, plugin install/uninstall.

**Electron posture to match/decide:** windows run `contextIsolation:false, nodeIntegration:false, --enable-sandbox`, preload assigns `window.ipcBridge` directly. TLS certificate pinning (`setCertificateVerifyProc`). Hardened-runtime entitlements incl. `allow-jit`, `disable-library-validation`, `personal-information.location`. *(A clean implementation should prefer `contextIsolation:true` + `contextBridge`.)* [C]

---

## 8. Local data store

Native `CricutLocalData`; offline mirror of cloud content over 151 `NativeLocalData.*` request/response messages (get/set/delete CRUD). Full schema: `analysis/localdata-schema.txt`. [C] *(finding 07)*

### 8.1 Storage
SQLite **`metadata.db`** via **SQLCipher** (encrypted at rest; FTS3/4 for search). **The SQLCipher key is protected (§0.3)** — a clean implementation chooses its own key management.

### 8.2 Schema (domains → columns)
- **Entitlements (offline Cricut Access gating):** `entitlement_id`, `entitlement_expiration_date`, `entitlements_data` (`PBEntitlementData`); validity by expiration (`CheckAllEntitlementsValid`, `ClearRemainingOrphanEntitlements`).
- **Canvases:** `canvas_id`, `canvas_data`/`canvas_json` (the §6 model), `canvas_details`, `canvas_cache_timestamp`; M:N `entity_id ↔ canvas_ids`.
- **Images:** `image_id`, `image_data`, `image_preview(_url)`, `bitmap_data` (fills).
- **Fonts:** family/chars/metrics/OTF paths (pairs with §9.2).
- **Materials/machine:** settings, sizes, pressure, `machine_serial`, pattern filters.
- **User/profile:** settings, preferences, tags, `profile_id`.

---

## 9. Supporting native services

*(finding 08; schemas in `analysis/native-helpers-schema.txt`)*

### 9.1 PathOperation — geometry engine (92 msgs)
Boolean ops (`a_minus_b`/`b_minus_a`/`intersection`), slice (`SliceSimple{path_1,path_2}`), vector fill for pens (`DoVectorFill`, wave/particle types), transforms (`PBMatrixPathOp`), queries (`GetBounds`/`GetPathDirection`/`GetPathPoints`/`ParsePath`), raster→vector `TraceImage`. An implementation can supply these with any 2D geometry library.
- **PROTECTED (§0.3):** `RequestPathOperationEncrypt/Decrypt` on path data = design-asset DRM. Not specified.

### 9.2 SystemFont — font access (67 msgs, CoreText)
Enumerate installed fonts; return **glyph outlines as `path_data`** + metrics + kerning (legacy and OTF variants); host spell-check. This is why system fonts are cuttable, not just displayable.

### 9.3 SystemPrinter — Print-Then-Cut host printing (56 msgs, CoreGraphics/ApplicationServices)
Printer/bin/paper enumeration, print image/test page, layered preview composition, and **`FiducialData`** (registration marks the machine later scans to align cut-to-print). Rasterizes via bundled ImageMagick (`cricut-magick`, `magick_path`).

---

## 10. Cloud & monetization surface (external dependencies)

[C] *(finding 01)* An implementation must decide its own backends for these; the originals are Cricut-operated.
- **APIs:** `apis.cricut.com` (public + claims/entitlements), `design.cricut.com`, `staticcontent.cricut.com`, CloudFront CDNs.
- **Payments:** Stripe. **Subscriptions:** Cricut Access gating (`ACCESS_EXCLUSIVE_REQUIRE_SUBSCRIPTION`), cached locally (§8.2).
- **Flags/analytics:** Statsig (feature flags, exposed via preload), Braze.
- **AI features:** Chat-to-Make, GenerateAI metadata.

---

## 11. Reproducibility summary — what to build vs. what blocks

| Layer | Status for a clean-room build |
|---|---|
| GUI (Angular workflows, i18n structure, flags) | **Reproducible** — model from observed behavior; supply own assets |
| Canvas/cut-job model (§6) | **Reproducible** — 52 msgs with **full field tags** (protoc-validated, finding 10) + 26 enum sets |
| Geometry / fonts / printing (§9) | **Reproducible** with standard libraries; full `.proto` field tags recovered (finding 10) |
| Local store (§8) | **Reproducible** — own key/DB; full `NativeLocalData.proto` (155 msgs) recovered |
| Transports + routing (§§3–4) | **Reproducible** — USB/BT/BLE/TCP with a common interface; mDNS + BLE scan |
| IPC surface (§7) | **Reproducible** — 145 forwarders mapped, channel == PascalCase(api) (finding 11) |
| Frame envelope (§5.1) | **Known** — `0xCC 0x01` + u32-LE length |
| Command vocabulary (§5.2) | **Known + serializable** — full field tags (finding 10), validated vs slicebug; handler table not enumerated |
| CNV2 machine-side bytes (pre-Bifrost) | **Partial** — prior-art opcodes (`0x21`/`0x22`/`0x43`…) mapped; most of 142 PB cmds unmapped pending capture (finding 12) |
| **Secure session / handshake (§5.3)** | **BLOCKED — legal gate.** Required for Scout/Bifrost ≥31. Pre-Bifrost machines may not need it (verify). |
| **Design-asset & cartridge DRM (§9.1)** | **BLOCKED — legal gate.** |
| **SQLCipher key (§8.1)** | **BLOCKED — choose own.** |

**Lowest-risk path to a working product:** a clean-room GUI + cut pipeline targeting **CNV2 / pre-Bifrost machines** (which community projects cutcutgo/FreeKnife/grasshopper indicate do not enforce session crypto), using own cloud/content. Anything touching §§5.3, 9.1, 8.1 waits on counsel.

---

## Appendix A — Source findings & artifacts

| Spec §| Finding | Artifacts |
|---|---|---|
| 1 | 01, 04 | — |
| 2 | 02 | — |
| 3 | 05 | — |
| 4 | 03, 05 | `deviceio-symbols-full.txt`, `bifrost-wasm-surface.txt` |
| 5 | 03, 06, 09, **10, 12** | `bridge-protobuf-messages.txt`, `evidence/bridge.log`, **`protos/CricutDevice*/`** |
| 6 | 05, **10** | `canvas-protobuf-schema.txt`, **`protos/canvas-model.proto`** |
| 7 | 05, **11** | `main-strings.txt`, **`ipc-channel-map.tsv`** |
| 8 | 07, **10** | `localdata-schema.txt`, **`protos/CricutLocalData/`** |
| 9 | 08, **10** | `native-helpers-schema.txt`, **`protos/Cricut{PathOperation,SystemFont,SystemPrinter,VulcanDevice}/`** |
| 10 (cloud) | 01 | — |

**Target integrity:** `app.asar` sha256 `182907963bb52c2431e36ba70dcc65b1ba02b007f54a42710979911100af1800`; 12 native-helper hashes in `analysis/evidence/native-binaries.sha256`.
