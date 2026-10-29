# IPC Channel Map — bridge API → method → channel (Gap 2)

**Target:** Cricut Design Space v10.9.118 · **Date:** 2026-10-27
**Method:** de-obfuscate `preload.js` + static renderer scan (`tools/ipc_map.py`). No app launch; no bridge method invoked.
**Deliverable:** `analysis/ipc-channel-map.tsv`.

## 1. How the IPC surface actually works

Finding 05 §4 noted the channels were obfuscated lookups. Resolved, the design is:

1. **`preload.js` exposes `window.ipcBridge`** — **261** keys. **145** are thin `ipcRenderer` forwarders of the shape
   `'<api>': (chan, …args) => ipcRenderer[<method>](chan, …args)`.
   The `<method>` is the only obfuscated part: a javascript-obfuscator **string-array** lookup. Reversing the array (replicating the rotation until its checksum matches the magic `0x1c4da`) resolves every method. (The other ~116 keys are `webFrame` spell-check methods and the channel-enum members, not ipcRenderer forwarders.)
2. **The channel is supplied by the caller**, not hard-coded in preload. The renderer calls `ipcBridge.<api>(D0.<Member>, …)` where `D0` is a channel-constant object whose members map **identity**: `D0.GetStatsigOverrides = \`GetStatsigOverrides\``. So **channel string == PascalCase(api)**.
3. **The main process** registers `ipcMain.handle`/`.on` on those PascalCase channel names (127 + 136 handlers, finding 06); pairing them requires deobfuscating main.js (out of scope — timeout/documented), but the channel name is now known from the renderer side.

## 2. Results

- **145 forwarders mapped**, methods resolved: `invoke` 139, `send` 4, `once` 1, `sendSync` 1.
- The method split is semantically coherent (validates the array reversal): request/response → `invoke` (`appConfigSync`, `getStatsigOverrides`); fire-and-forget byte streams → `send` (`pluginCdioSendBytes`, `pluginDeviceCommonClearMatCutExecutionPlan`); one-shot reply → `once` (`clipboardOnValueReady`); blocking → `sendSync` (`getActiveTabType`).
- **53 channels confirmed** directly from renderer call sites; **all 53 follow channel == PascalCase(api)**, so the remaining forwarders' channels are inferred by that rule **[I]** (column `channel_inferred` in the TSV).

### 2.1 Device / machine channels (the high-value subset)
| bridge API | method | channel (PascalCase) | → native layer |
|---|---|---|---|
| `pluginCdioSendBytes` | send | PluginCdioSendBytes | CDIO transport (Bifrost/Scout) |
| `pluginCdioReceiveBytes` | invoke | PluginCdioReceiveBytes | CDIO transport |
| `pluginDeviceCommonStart` / `Request` / `Stop` | invoke | PluginDeviceCommon… | Bridge-7 command layer (CNV2) |
| `pluginDeviceCommonClearMatCutExecutionPlan` | send | …ClearMatCutExecutionPlan | cut-plan reset |
| `pluginVulcanStart` / `Request` / `Stop` | invoke/send | PluginVulcan… | Vulcan pod/press |
| `pluginLocalDataRequest` / `Start` / `Stop` / `Version` | invoke | PluginLocalData… | SQLCipher cache |
| `pluginPathOperationRequest` | invoke | PluginPathOperationRequest | geometry |
| `pluginSystemFontRequest` | invoke | PluginSystemFontRequest | fonts |
| `pluginSystemPrinterRequest` | invoke | PluginSystemPrinterRequest | Print-Then-Cut |
| `machinesUpdated`, `machineFamilyUpdated`, `machineOnboardingCompleted`, … | invoke | Machine… | machine-state events |

These confirm the routing of findings 04/05: the renderer reaches each native helper through a dedicated `plugin*` channel; the device byte I/O (`pluginCdio*`) uses `send`/`invoke` for streaming, while the request/response helpers use `invoke`.

### 2.2 Handler groups (all 145)
`misc` 59, `app`/`appConfig`/`appFeatureFlag` 14, `systemPreferences` 6, `machine` 6, `update` 6, `event` 6, `plugin*` (device/data/etc.) 14, `wifi` 4, `canvasCache` 4, `login` 3, `dataStorage` 3, `clipboard` 3, `project` 3, `about` 3, `record` 3, `tab`/`menu`/`auth`/`statsig`/`screenSize`/`keepScreenAwake` 2 each. Full table in the TSV.

## 3. Security note (for a clean implementation)
Because channels are caller-supplied and the preload forwards blindly, any renderer code can invoke any channel — consistent with `contextIsolation:false` (finding 04 §5). A clean-room build should instead expose a **fixed, enumerated** channel set through `contextBridge` rather than a generic forwarder.

## 4. Reproduce
```
python3 tools/ipc_map.py unpacked/cricut-ele-design-space/preload.js \
  'unpacked/design-space-app/*.js,unpacked/design-space-home/*.js' analysis/ipc-channel-map.tsv
```
