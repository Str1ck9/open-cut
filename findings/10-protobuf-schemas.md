# Protobuf Schemas — Full Field Tags (Gap 1)

**Target:** Cricut Design Space v10.9.118 · **Date:** 2026-10-27
**Method:** two independent static extractions, both validated with `protoc 36.2`. No app launch.
**Deliverables:** `analysis/protos/<binary>/*.proto` (native), `analysis/protos/canvas-model.proto` (+`-fields.tsv`), tools `tools/pbscan.py` and `tools/pbjs_extract.py`.
**Boundary (§0.3):** handshake key-exchange fields and the design-asset/cartridge encrypt-decrypt messages are **redacted** in the emitted `.proto` (marker comments, field present/count noted, layout omitted). Crypto was not analyzed.

Previously we had message/enum **names** only (findings 03/05/07/08). This recovers the **field numbers, wire types, labels, enum values, nested types, maps, and oneofs** — everything needed to actually serialize. Confidence **[C]**: field tags are read directly from the binaries' own descriptors / generated code and compile under protoc.

## 1. Route A — native C++ descriptors (`tools/pbscan.py`)

Each native helper embeds serialized `google.protobuf.FileDescriptorProto` blobs (the source of the `NativeModel.*` name strings). `pbscan.py` locates them (anchored on the `.proto` filename field), decodes the wire format with a pure-Python FDP parser, and renders `.proto`. Universal binaries were thinned (`lipo -thin arm64`) first. **All seven sets compile cleanly.**

| Binary | namespace(s) | files | messages | enums | fields |
|---|---|---|---|---|---|
| `device-common/CricutDevice` (6.12.13) | `NativeModel.Bridge` + `NativeModel` | 10 | 155 | 49 | ~1700 |
| `device-common-next/CricutDevice` (7.0.6) | + `bridge.proto.device/logging` | 17 | 177 | 52 | ~1750 |
| `local-data/CricutLocalData` | `NativeLocalData` | 1 | 155 | 0 | 319 |
| `path-operation/CricutPathOperation` | `NativePathOperation` | 1 | 46 | 3 | 167 |
| `system-fonts/CricutSystemFont` | `.Interaction`, `.Models` | 2 | 41 | 2 | 152 |
| `system-printer/CricutSystemPrinter` | `NativeSystemPrinter` | 1 | 23 | 1 | 110 |
| `plugin-vulcan/CricutVulcanDevice` | `cricut.plugin_vulcan.proto` | 1 | 23 | 8 | 68 |

The machine-command protocol (`device-common`) is split across 10 `.proto` files: `NativeModel.Bridge` (70 msgs / 653 fields — the main command set), `Commands` (28 / 172), `Machines` (18 / 436, incl. the `PBMachineType` enum with the family IDs from finding 02, negatives correct e.g. `LOKI_UNDERMINER_MT = -200`), `Force` (17 / 166), `Devices` (13 / 81), `Backlash`, `Analytics`, `CustomerTheta`, `Learning`, and `BridgeEnums` (12 enums).

### 1.1 Independent validation — matches slicebug
The community project **slicebug** ships a hand-reconstructed `Bridge.proto`. Cross-checking shared messages: **15/15 name-matched field numbers identical, 0 mismatches** (e.g. `PBMatPathData{fiducial_id=1, path_data=2, path_color=4, actual_path_type=14, contour_active_flags=21}`; `PBCricutDeviceSerialized{device_type=5, port=8, connection_type=21, device_type_enum=25, key=27, serial=10}`). Our extraction is far more complete (PBMatPathData: 38 fields vs their 8; PBCricutDeviceSerialized: 60 vs 7). This corroborates Route A at **[C]**.

### 1.2 device-common-next (7.0.6) additions
Beyond the superset noted in finding 09, 7.0.6 adds a structured transport layer as its own descriptors: `bridge.proto.device.{DeviceRegistry, Session, DeviceMessage}` and `bridge.proto.logging`. **`session.proto`** is the transport session state machine — `SessionOpen/Close/DataStreamRequest/Response` keyed by `DeviceHandle`, carrying opaque `bytes data` (the encrypted payload is a black box here; **not** the handshake). `registry.proto` enumerates connected devices; `logging` is structured logs. Field naming shifts snake_case → the editions/proto3 style.

## 2. Route B — canvas model (`tools/pbjs_extract.py`)

The canvas/cut-job model is protobuf.js **static generated code** in `canvas-webw-*.js`, not a native descriptor. `pbjs_extract.py` parses each message's `decode()` `switch(tag>>>3)` to recover field number → name → reader type, including protobuf **map** fields (nested-switch form) and repeated fields. Output: `canvas-model.proto` (**compiles cleanly**) + `canvas-model-fields.tsv`.

- **52 messages, 256 fields** recovered with tags (e.g. `CanvasBody{CanvasType=1, CanvasSize=2, CanvasRootGraphic=3, …, IsAutoSaveEnabled=11}`; `Cache{Layers=1, map<string,string> AttachIds=2, AutoWeldIds=3}`; `Bitmap{… map<string,string> PreviewUrls=3}`).
- 12 referenced-but-unextracted types are stubbed (e.g. `WeldedGraphic`, `SlicedGraphic`, `BoundaryDerived`; `google.protobuf.*Value` wrappers imported).
- **Limitation:** enum-typed fields decode as `int32` (wire-identical to enums); scalar-vs-enum is ambiguous from `decode()` alone, so they render as `int32`. The enum **value sets** (names→numbers) are in `analysis/canvas-protobuf-schema.txt` (finding 05) and can be re-attached. Field names are preserved (not minified) in protobuf.js, so names are exact.

## 3. What this unblocks
A clean-room implementation can now **serialize/deserialize** the canvas model and the non-protected machine-command, local-data, path-op, font, printer, and vulcan messages exactly, because the `.proto` files are byte-compatible (verified by protoc, corroborated by slicebug). The remaining gaps are only the redacted §0.3 surfaces.

## 4. Reproduce
```
lipo -thin arm64 <CricutX> -o <CricutX>.arm64
python3 tools/pbscan.py <CricutX>.arm64 analysis/protos/<CricutX> --redact Encrypt,Decrypt,EncData
python3 tools/pbjs_extract.py 'unpacked/design-space-app/canvas-webw-*.js' analysis/protos/canvas-model.proto analysis/protos/canvas-model-fields.tsv
protoc --proto_path=analysis/protos/<dir> --proto_path=/opt/homebrew/include -o /dev/null <dir>/*.proto   # validates
```
