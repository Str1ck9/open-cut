# Command Layer: `device-common` vs `device-common-next`

**Target:** Cricut Design Space v10.9.118 · **Method:** REA Ghidra v12.1.4 `binary_overview` on thinned arm64 slices + protobuf-descriptor string diff · 2026-10-27
**Scope:** structure/version/message-set diff only. No crypto/handshake analysis (README #6). Builds on `06` (dispatch architecture, unchanged between the two).

The app ships **two builds of the same C++ command helper** and selects between them by feature flag (`01` §1 "feature-flagged swap"). `device-common` is the active one; `device-common-next` is the staged successor.

## 1. Structural comparison

| | `device-common/CricutDevice` (current) | `device-common-next/CricutDevice` (next) |
|---|---|---|
| Product version | **6.12.13** (running; launched `--new-comm-lib`) | **7.0.6** (staged, not active) |
| Universal size | 11.1 MB | 12.9 MB |
| arm64 procedures (Ghidra) | 15,901 | **17,102** (+1,201, +7.5%) |
| `__text` | 3.81 MB | 4.57 MB (+20%) |
| Language | C++/ObjC (no Swift) | C++/ObjC (no Swift) — same |
| Dispatch model | `CommandTypes::get_command` + `is_in_cutting_session` (`06`) | **unchanged** — same architecture |
| `NativeModel.Bridge` message set | baseline | **strict superset: 0 removed, ~45+ added** |
| Proto field naming | `snake_case` | many `camelCase` + `…Api`-suffixed messages |

`device-common-next` is a **superset refresh**: nothing was removed, the dispatch architecture is identical, and it's ~7.5% more code. The major version bump (6→7) and the field-naming shift are the headline differences.

## 2. New message concepts in 7.0.6 (clean prefixes from the descriptor)

| Area | New messages |
|---|---|
| **Heat-press telemetry** | `PBHeatingPressInfo` (model, voltage, current/bottom temp, error code, countdown) — first-class heat-press status in the *cutter* command layer |
| **Device identity** | `PBCricutDeviceSerialized` (device_type, serial, key, mac_address, bluetooth_version, pid/vid hex, libusb serial/port, bluetooth_name) |
| **Analytics + entitlement** | `PBAnalyticMachineSummary` (firmware values, company name, entitlement description/expiration, machine type, duration type, entitlement URL) |
| **Materials (expanded)** | `PBMaterialSettingV2`, `PBMaterialSettingsApi`, `PBMaterialTag`, `PBMaterialInset`, `PBMachineMaterial`, `PBMatSize` |
| **Mode / state / tools** | `PBMachineMode`, `PBModeApi`, `PBMachineDefaultState(s)`, `PBState`, `PBTool`, `PBToolType`, `PBToolSettings` |
| **Firmware** | `PBMachineFirmwareValuesApi`, `PBFirmwareUpdateOption` (+ `ValueFileVersion`) |
| **Infra / transport** | `PBDataRepo`, `PBTransmission`, `PBEmission`, `PBKeyValue`, `PBCommandTimeoutsConfig`, `PBWebRequest` (action/parameters/method/body), `PBDevicesResponseRequest` |
| **Cartridge (legacy)** | `PBCartridgeInformation`, `PBCartridgeDataEncData` |

## 3. Interpretation

- **Same engine, broader coverage.** 7.0.6 keeps the dispatch design and adds data models rather than restructuring — a low-risk, flag-gated migration.
- **Cloud-API alignment.** The `camelCase` fields and the cluster of `…Api` message names (`PBMaterialSettingsApi`, `PBMachineFirmwareValuesApi`, `PBModeApi`) suggest 7.x models its data closer to the cloud REST API shapes than 6.x did.
- **Heat presses move into the unified layer.** `PBHeatingPressInfo` in the cutter command helper hints at consolidating heat-press status under the same Bridge protocol (consistent with the many press families in `02`).
- **Richer telemetry.** `PBAnalyticMachineSummary` ties machine + firmware + entitlement into one analytics message.

## 4. Not analyzed (legal gate)

Both builds carry the secure-session envelope fields in `PBCommonBridge` / `PBDevicesResponseRequest` (device-hello / key-response). Their presence is noted; the handshake was **not** examined in either build. `PBCartridgeDataEncData` (encrypted cartridge data) was likewise left unopened.
