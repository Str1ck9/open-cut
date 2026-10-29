# Cricut Machine Protocol — Bridge 7 Architecture (from REA + binary analysis)

**Target:** Cricut Design Space v10.9.118 · **Method:** REA 6.7.0 (JS static analysis + obfuscator string-array dump), `nm`/`c++filt`/`strings` on Mach-O native binaries · 2026-10-27

> **Revised 2026-10-27 after verification review.** Corrections are inline and marked **[REVISED]**. Summary:
> (1) "AES-GCM" isn't supported by the strings. The evidence shows an **AEAD cipher, mode unconfirmed**.
> (2) The "Bifrost 31.0.0 requires a secure session" text is **scoped to Scout** and has an off switch. It isn't a statement about all machines.
> (3) There are **separate device paths** (Bridge/CNV2 vs. CDIO vs. Vulcan), not one pipeline. See `04-wasm-modules.md` §4.
> (4) The machine-session logic is most likely in **`Bifrost.wasm`, which runs in the renderer**, not only in native helpers. See `04` §2.
> (5) The protobuf list was 170 lines with `strings(1)` artifacts. Cleaned, it's **142** unique names.

## 1. The Big Discovery: Machine I/O Does NOT Live in the Electron Main Process

The obfuscated 10 MB `main.js` is a **coordinator**, not the driver. All machine I/O is delegated to **"Bridge 7"** — a set of native helper executables spawned as child processes, communicating with Electron over a local domain socket (`127.0.0.1` / AF_UNIX):

| Native binary (Resources/plugins/) | Role | Evidence |
|---|---|---|
| `cricut-device-io/CricutDeviceIO` (10.4 MB, universal, Swift+C++) | **Transport layer**: USB, BLE, classic BT, TCP enumeration + I/O | 17,446 symbols: `cricut::device_io::{usb,bluetooth,bluetooth_le,ip,async_transport}`, `libusbp` (libusb C++ wrapper), `btle_corebluetooth` (Swift BLE adapter) |
| `device-common/CricutDevice` (11.1 MB, universal, C++) | **Machine command layer**: cut execution, material settings, calibration, firmware | Static protobuf runtime; `NativeModel::Bridge::PB*` descriptors; `send_command_result`, `is_in_cutting_session(CommandType)` |
| `device-common-next/CricutDevice` | Newer version of same (transition) | Feature-flagged swap |
| `plugin-vulcan/CricutVulcanDevice` | **[REVISED]** Two-part **pod + main-unit** firmware/activation controller. The proto is product-agnostic; the renderer ties family `VULCAN` → "Cricut Autopress" (`OOB_VULCAN_LABEL`, `autopress.png`). Separate repo `cricut-plugin-vulcan` (CI path in binary). | `.cricut.plugin_vulcan.proto.*`: `ActivatePod`, `GetPodInfo`, `UpdatePodFirmware`, `UploadMainUnitFirmware`, `SetSerialNumber`, `GetDeviceErrors`, `FindDevices`, `ConnectionInfo`/`ConnectionType`, `DeviceId`, `Progress`, `InvalidRequestResponse` |
| `canvas/CricutCanvas` | Canvas geometry engine (x86_64 only) | Worker plugin |
| `local-data/CricutLocalData` | Local offline cache (canvases, fonts, images, **entitlements**) in a **SQLCipher-encrypted** `metadata.db`. Full schema: `07-local-data-schema.md`. | `.NativeLocalData.*` (151 Request/Response messages) |
| `path-operation/CricutPathOperation` | Geometry: boolean/slice/vector-fill/trace (+ design-asset encrypt/decrypt, not opened). Schema: `08-native-helpers.md`. | `.NativePathOperation.*` (92 messages) |
| `system-fonts/CricutSystemFont` | System-font glyph outlines + metrics/kerning + spell-check (CoreText). Schema: `08`. | `.NativeSystemFont.*` (67 messages) |
| `system-printer/CricutSystemPrinter` | Print-Then-Cut host printing + fiducials (ImageMagick raster). Schema: `08`. | `.NativeSystemPrinter.*` (56 messages) |
| `wifi-scan/Cricut Design Space Wifi.app` | WiFi scan helper (for IP-connected machines) | Separate app bundle |

> **[VERIFIED 2026-10-27]** SHA-256, size and arch for all 12 helpers: `analysis/evidence/native-binaries.sha256`. REA `inspect_macho`/`inspect_signature` on `CricutDeviceIO` confirm: universal (x86_64 + arm64), **SDK 26.4 / min macOS 11.0**, links `libswiftCore` + CoreBluetooth + IOBluetooth + IOKit + Security + libc++ (Swift-over-C++, as described), signed **Team ID `25627ZFVT7` "Cricut, Inc."**, notarized, hardened runtime. Running versions (live process list): `CricutDevice v6.12.13` (device-common, `--new-comm-lib`), `CricutDeviceIO 3.18.0-alpha3`. `CricutCanvas`/`cricut-magick` are x86_64-only; the rest are universal.
>
> **Deep-provider note:** REA's **Ghidra provider is installed and works** — it just can't import a *universal* Mach-O, so each binary must be thinned to one arch first (`lipo -thin arm64 <bin> -output <slice>`), then opened. Demonstrated on the `CricutDeviceIO` arm64 slice (05 §5). Hopper and IDA are not installed/configured. Procedure-level analysis of the **crypto/handshake** paths still waits on the legal gate in §6; structural analysis (segments, procedure inventory, call graphs) is available.

## 2. Transport Layer (CricutDeviceIO demangled symbols)

Four transports, all with the same abstract interface (`connect` / `disconnect` / `send_bytes` / `receive_bytes` / `get_connection_state` + async variants):

- **USB serial** — `cricut::device_io::usb::usb_serial_transport`, enumeration via `usb_serial_device_inquirer` (libusbp). Cricut USB VID: **0x24AA** **[still unverified 2026-10-27]**. A live `system_profiler SPUSBDataType` was run — **no Cricut device is attached to this machine**, so the VID couldn't be hardware-confirmed. The recovered `PBCricutDeviceSerialized` message carries runtime `vid`/`vid_hex`/`pid`/`pid_hex` fields (finding 10), i.e. the VID is reported per-device at runtime, not a static constant in the app. Confirm against attached hardware when available.
- **USB HID** — `create_usb_hid_async_transport`
- **Bluetooth Classic** — `bluetooth_serial_transport` + pairing (`pairing::try_pair`)
- **BLE** — `bluetooth_le_adapter` / `bluetooth_le_central` (CoreBluetooth-backed, Swift `btle_corebluetooth` FFI: `btle_adapter_start_scanning`, manufacturer-data parsing)
- **TCP/IP** — `ip_tcp_transport` with keepalive options, discovery via **mDNS** (`tcp_ip_mdns_device_inquirer`) — this is how Venture/Gemini-family machines are found on the network

Discovery callbacks (`set_device_discovered_callback`) feed an enumeration layer that surfaces devices to the renderer's `DeviceManager`/`BifrostDeviceDiscoveryManager` via the bridge.

### 2a. BLE adapter internals (REA Ghidra `analyze_swift_types`, arm64 slice)

The **C++/Swift split is now confirmed**: of the four transports, only **BLE is Swift** — the `btle_corebluetooth` module, a thin wrapper over CoreBluetooth. USB serial/HID, Bluetooth classic, and TCP/IP are C++ (they produce no Swift type metadata). Ghidra categorized 137 Swift class procedures; the structure:

- **Classes:** `Adapter` (CBCentralManager owner — scanning/connect), `Device` (CBPeripheral wrapper), `Context`, `Logger`, `DeviceEventHandler`.
- **Private CoreBluetooth delegates:** `Adapter.CentralDelegate` (`centralManager:didDiscoverPeripheral:advertisementData:RSSI:`, `didConnect`, `didDisconnect`, `didFailToConnect`, `willRestoreState`, `didUpdateState`) and `Device.PeripheralDelegate` (`didDiscoverServices`, `didDiscoverCharacteristicsForService`, `didUpdateValueForCharacteristic`, `didWriteValueForCharacteristic`, `didUpdateNotificationStateForCharacteristic`, …).
- **BLE op model** (nested in `Device`): `CharacteristicRequestQueue`, `DiscoveryRequest`, `ReadRequest`, `WriteRequest`, `NotifyRequest`.
- **Public operations:** `Adapter.connectToDevice` / `disconnectFromDevice` / `getDeviceConnectionState`; `Device.discoverServicesAndCharacteristics` / `readCharacteristic` / `onDisconnected`.
- **Shared FFI types (`CBTLECoreBluetoothCommon`):** `DeviceId`, `Service`, `Characteristic`, `AdvertisementData`, `ScanningOptions`, `DeviceConnectionState`, `PairingStatus`, `UnpairingStatus`, `AdapterState`, `OperationError`, `LogLevel`, and events `AdapterEvent` / `DeviceEvent` / `DeviceDiscoveredEvent` / `DeviceEventPayload` / `AdapterSessionRestoredEvent`.

This is a generic GATT client (scan → connect → discover services/characteristics → read/write/notify) with no machine-specific logic — the Cricut protocol rides on top as characteristic payloads. The C++ side exposes the same transports as a protobuf command vocabulary (`UsbSerialTransport*`, `BluetoothLeSerialTransport*`, `BluetoothSerialAdapter*`, `ip_tcp_transport_*`, `*DeviceDiscoveredNotification`), seen in the slice's strings.

## 3. Bridge 7 Wire Protocol (from string-table + captured bridge.log)

~~The Electron main process ↔ CricutDeviceIO channel~~ **[REVISED]** The Electron main process ↔ **Bridge 7 helper** channel (device-common, the CNV2 path) uses length-prefixed frames. CricutDeviceIO is a separate per-window "CDIO" byte link (`04` §4).

```
Decoded live frames (analysis/evidence/bridge.log, base64 per line; VERIFIED):
  byte 0-1:  0xCC 0x01            magic + protocol version
  byte 2-5:  <len> 0x00 0x00 0x00 payload length, u32 LITTLE-ENDIAN (= total-6)
  byte 6+:   ENCRYPTED PAYLOAD    (nonce + ciphertext + auth tag)
Observed: 6 frames, 202/172 bytes alternating; lengths 196 (0xC4) / 166 (0xA6).
```

> **[VERIFIED 2026-10-27]** `bridge.log` is now in the project (`analysis/evidence/bridge.log`) and decodes cleanly. Six base64 frames, alternating 202/172 bytes (request/response). Every frame: bytes 0–1 = `cc 01`; bytes 2–5 = the payload length as **u32 little-endian** (`c4 00 00 00` = 196, `a6 00 00 00` = 166), which equals total−6 exactly; bytes 6+ = payload. So the field is a **4-byte LE length**, not "u8 BE" — the 3 "reserved zero" bytes were the high bytes of the length. Payloads are ciphertext and were not analyzed.

Evidence: "Encrypted BRDG payload too short to contain nonce and authentication tag", "Bridge 7 frame CRC mismatch (expected …)", "CRC_ERROR_DURING_DECRYPT", "NO_AES_HANDSHAKE", "Bridge 7 socket connected", "ms waiting for Bridge 7 socket connection".

**[REVISED] Cipher:** ~~AES-GCM~~ The strings show an **AEAD construction (nonce + authentication tag), mode unconfirmed**. There is **no `GCM` literal** in the 21k-string main-process dump (the only case-insensitive hit is the unrelated `ngcm`). What *is* present:
- `ENCRYPT_AES_PATH_MA` / `DECRYPT_AES_PATH_MA` (points toward AES; mode not stated)
- `@noble/ciphers`-style errors: `arx: nonce must be`, `arx: invalid block position` (the ARX = ChaCha/Salsa core), `"ciphertext" expected length >= tagLength=`, `"fn" expected cipher constructor`
- `aes-256-cbc` with Node `createCipheriv` (probably unrelated local-storage crypto)

AES-GCM and ChaCha20-Poly1305 both remain plausible. Settle it from code, not names. `Bifrost.wasm` also contains AES/GCM/ChaCha/X25519/P-256/HKDF strings (`04` §2).

**[REVISED] Scope of the secure-session requirement.** ~~The same encrypted-link handshake is used end-to-end … Machines enforce the crypto.~~ The only source is the feature-flag description `DH_MACHINES_SCOUT_SECURE_SESSION_DESC`:
> "Scout: establish a secure (encrypted) session on connect/reconnect. Default true as of Bifrost 31.0.0, which unconditionally requires an established secure session for every Scout command — off restores the pre-31.0.0-compatible behaviour of skipping the handshake, which will fail all Scout commands against Bifrost 31.0.0+."

This shows that **Scout** on Bifrost firmware ≥ 31.0.0 enforces a session handshake. It says nothing about other families. It's also unclear whether the BRDG frame encryption above (local Bridge 7 socket) and the Scout machine session are the same crypto context. Treat them as separate until shown otherwise (`04` §4, open question).

## 4. Machine Command Vocabulary (protobuf `NativeModel.Bridge`)

~~170~~ **[REVISED] 142 unique** PB message/enum names. The raw `strings(1)` pass on `CricutDevice` gave 170 lines, but 35+ were duplicates with a trailing descriptor tag byte (`PBAccessoryB`, `PBBridgeApiErrorH`). Cleaned list: `analysis/bridge-protobuf-messages.txt` (95 also confirmed by protobufjs verifier strings in the main process, 42 binary-only (mostly enums), 5 JS-only). Raw: `bridge-protobuf-messages.raw.txt`. Highlights:

- **Cut pipeline:** `PBMatCutExecutionPlan` (groupedExecutions → `PBMatCutGroupExecution.paths`), `PBCutExecution`/`PBForceExecution(Plan)`, `PBDrawVector(s)`, `PBPathSplitData`, `PBSortingDistances`/`PBVectorToMachineSorting`, `PBPathSortingConfig` (path optimization/ordering)
- **Materials/pressure:** `PBMaterialSelected`, `PBPressureTableRow`, `PBForceCurve`, `PBForceGauge*` (settings, history, vendor), `PBSpeedSettingsZTS`/`PBToolSettingsZTS` (per-tool speed/force), `PBForceMatType`
- **Calibration:** `PBCustomerTheta`, `PBThetaBias(Mode|Rotate)`, `PBThetaHomeOffset`, `PBFiducialOffset(sReport)`, `PBMatFiducialData` (Print-Then-Cut fiducials), `PBPtcTestsInputData`, `PBScanDiagnostics(ScanResultItem)`
- **Machine state:** `PBMachineStatus`, `PBGetFullStatus`, `PBSetMachineState`, `PBUnitDevicesState`, `PBProgress` (lineProgress, currentToolSettings), `PBSimulateButton`, `PBSetPlatformSequence`
- **Tools:** `PBToolInfo`, `PBToolLocation`, `PBCommonTool(Cut)`, `PBCricutToolZTS`, `PBAccessory(V2)`, `PBPenToBlade`
- **Legacy/ODM:** `PBMachineType`, `PBCartridgeData` (physical cartridge linking), `PBRawCommandRequestResponse` (raw passthrough)
- **Family-specific:** `PBZorroOriginCommand` (Explore), `PBMorphOriginCommand` (Venture), `PBAthenaHomeThetaResult` (Maker)

Result/error codes (`kSuccess`, `kUnableToAuthenticateDevice`, `kInvalidCRC`, `kCutAborted`, …) show that device authentication exists and can fail. **[REVISED]** ~~confirm every device connection is authenticated and encrypted~~ They don't show that it applies to every family or connection.

## 5. Renderer→Bridge Flow (end-to-end cut pipeline)

> **[REVISED] Superseded by `04-wasm-modules.md` §4.** The chain below describes only the Bridge/CNV2 path. Gemini/Scout (and probably the `BIFROST`-comm families) use a CDIO byte link fed by `Bifrost.wasm` in the renderer. Vulcan has its own plugin channel. Kept for history.

```
Angular canvas (design-space-app)
  └─ protobuf CanvasBody/Graphic model (canvas-webw-cricanvas worker, 57 PB types)
       └─ IPC → Electron main (obfuscated main.js: session mgmt, feature flags, plugins)
            └─ domain socket → Bridge 7 frames (0xCC 0x01 … AEAD, mode unconfirmed)
                 └─ CricutDeviceIO (transport selection: USB/BT/BLE/TCP)
                      └─ CricutDevice (machine command protobuf → device-specific encoding)
                           └─ machine (Bifrost firmware enforces its own session crypto)
```

## 6. Implications for a Clean-Room GUI

1. **The GUI is fully reproducible** — Angular renderer is minified-but-readable; all 33 i18n modules, workflows, and feature flags are extractable.
2. **The transport stack is documented**: 4 transports with a common interface; USB VID 0x24AA; BLE manufacturer-data parsing; mDNS discovery for network machines.
3. **The command vocabulary is documented** (142 PB names). **[REVISED]** A session handshake is confirmed only for **Scout on Bifrost FW ≥ 31.0.0**, and its cipher mode is unconfirmed (§3). ~~The handshake lives in the stripped parts of CricutDevice/CricutDeviceIO; native Ghidra/Hopper is the next step.~~ The strongest candidate location is **`Bifrost.wasm`** (renderer-side Swift→WASM, 107 `handshake` strings). See `04` §2 and §7 for next steps and the legal gate.
4. **Older machines** (Explore/Maker era, `communicationType: CNV2`) are assumed not to enforce machine-link session crypto, consistent with prior community work (cutcutgo, FreeKnife, grasshopper). **[REVISED]** Not verified in this project.
5. **Legal caution remains** — Cricut has sued protocol re-implementors before (Make The Cut, Sure Cuts A Lot). Clean-room discipline: never ship their code, assets, or the recovered handshake keys.

## Artifacts

- `analysis/main-strings.txt` — 21,132 decoded obfuscator strings (the entire main-process vocabulary)
- `analysis/deviceio-symbols-full.txt` — 17,446 CricutDeviceIO symbols (demangled transport surface)
- `analysis/bridge-protobuf-messages.txt`: 142 cleaned PB names with source column (`.raw.txt` = original 170-line `strings` output)
- `findings/01-app-architecture.md`, `02-machine-codenames.md`: prior findings
- `findings/04-wasm-modules.md`: WASM modules, device paths, Electron security posture
- `findings/05-data-formats-and-ipc.md`: canvas protobuf schema, Bifrost.wasm surface, IPC registry, native-inspection provenance
- `analysis/evidence/bridge.log`, `analysis/evidence/native-binaries.sha256`: captured frames + helper hashes (the former evidence gap, now closed)

> Note: `main-strings.txt` contains NUL/control bytes, so `file` reports `data` and plain `grep` returns nothing. Use `LC_ALL=C grep -a`.
