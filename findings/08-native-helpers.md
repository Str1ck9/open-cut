# Native Helpers — PathOperation, SystemFont, SystemPrinter

**Target:** Cricut Design Space v10.9.118 · **Method:** embedded protobuf descriptors + linkage (strings/otool) from each C++ helper · 2026-10-27
**Scope:** data model / role only. Full inventory: `analysis/native-helpers-schema.txt`.

These are the three remaining data/geometry helpers, each a C++ process driven over its `plugin*` IPC channel (04 §4). None carries machine-link crypto. One content-DRM note in §1.

## 1. `path-operation/CricutPathOperation` — geometry engine (92 messages)

The vector-math service behind slice/weld/contour and pen fills. `.NativePathOperation.*`:

| Group | Messages |
|---|---|
| **Boolean ops** | `PBCommonSVGResponse{a_minus_b, b_minus_a, intersection, path, paths}` — difference (both directions), intersection, union |
| **Slice** | `RequestPathOperationSlice`, `SliceSimple{path_1, path_2}` |
| **Vector fill** (pen) | `DoVectorFill`, `PBVectorFillType`, `PBVectorFillWaveType`, `PBMatVectorFillData{particle_fill_path}` |
| **Transform** | `TransformPath`, `PBMatrixPathOp`, `PBPointPathOp`, `PBSizePathOp` |
| **Query / parse** | `GetBounds`, `GetPathDirection`, `GetPathPoints`, `ParsePath`, `PBSVGCommand`, `PBSVGPathNode` |
| **Image trace** | `TraceImage` (raster → vector) |

Links AppKit + a bundled Cricut geometry lib. No OpenSSL/Security linkage.

> **Content-DRM boundary (not analyzed).** This helper also defines `RequestPathOperationEncrypt{path_data}` and `RequestPathOperationDecrypt{path_item}`. That is **design-asset protection** — licensed/Cricut Access SVG paths are stored/transported encrypted and decrypted here for rendering. This is distinct from the machine-link handshake (03/04), but it is still a content-protection mechanism, so per the project's clean-room rule (README #6) its algorithm/keys were **not** reversed. Only the existence of the two operations is recorded.

## 2. `system-fonts/CricutSystemFont` — system font access (67 messages)

Bridges the OS font stack into the canvas. **Links CoreText.** `.NativeSystemFont.*`:

- **Requests:** `SystemFontList`(+`OTF`), `SystemFontInfoOTF`, `SystemFontMetrics`(+`OTF`), `SystemFontCharacter`(+`OTF`), `SystemFontParseOTF`, `SystemFontConversionData`, and spell-check (`SpellCheckText`, `SpellCheckWordAdd/Remove`).
- **Models:** `PBFont`/`PBFontOTF`/`PBFontFileOTF`/`PBFontCharacterMapOTF`, `Character`/`CharacterOTF{path_data}` (glyph outlines), `Metrics`/`MetricsOTF`, `FontBBox`, `CharacterKerning`/`KerningPairOTF`, `FontSelection{name}`.

Role: enumerate installed system fonts, return glyph **outlines as `path_data`** plus metrics/kerning for layout, and host spell-check. Everything has a legacy and a newer `OTF` variant — the OTF path feeds the system-font half of the LocalData font cache (07 §4). This is why system fonts can be cut/drawn, not just display fonts.

## 3. `system-printer/CricutSystemPrinter` — Print-Then-Cut host printing (56 messages)

Drives the desktop printer for Print-Then-Cut. **Links CoreGraphics + ApplicationServices** (the macOS print stack). `.NativeSystemPrinter.*`:

- **Requests:** `SystemPrinterList`(+`Async`), `SystemPrintImage`, `SystemPrintTestPage`.
- **Printer model:** `Printer{name, port}`, `Bin{name}`, `PaperSize{name, type_name}`, `PaperOrientation`, `PBFile{filename, mime_type}`.
- **Preview/compose:** `PreviewParams{name, mime_type, preview_type, preserve_aspect_ratio}`, `PreviewLayerParams{fill_bitmap_file_name, fill_color, stroke_color, group_guid}`, `PreviewGroupParams`.
- **Print-Then-Cut:** `FiducialData` — the registration marks the machine later scans to align the cut to the print (ties to the BIFROST calibration / fiducial-scan subsystem in `01` §2 / `03` §4).
- **Renderer:** `PBSystemPrinterInteractionMessage.magick_path` → it shells the bundled **ImageMagick** (`canvas/cricut-magick`, seen in the plugins tree) to rasterize layers before printing.

## 4. Place in the pipeline

```
Canvas (design-space-app, protobuf CanvasBody)
  ├─ CricutPathOperation  → boolean ops / slice / vector-fill / trace → cut geometry
  ├─ CricutSystemFont     → system-font glyph outlines + metrics → text layers
  └─ Print-Then-Cut: CricutSystemPrinter (ImageMagick raster → host print + FiducialData)
                       → machine scans fiducials → cut (03/04 transport)
```

All three are local, deterministic, and free of machine-link crypto — the clean-room-safe part of the stack. The only protected surface among them is PathOperation's design-asset encrypt/decrypt (§1), left unopened.
