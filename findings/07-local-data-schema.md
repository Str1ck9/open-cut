# Local Data Cache — `local-data/CricutLocalData` schema

**Target:** Cricut Design Space v10.9.118 · **Method:** embedded protobuf `FileDescriptorProto` message names + SQL/ORM column tokens from the C++ helper binary (strings/descriptor extraction; Ghidra not needed — the schema is fully in the descriptor data) · 2026-10-27
**Scope:** data model only. The DB is SQLCipher-encrypted; the key is **not** analyzed.
Full inventory: `analysis/localdata-schema.txt`.

## 1. What it is

`CricutLocalData` is the **offline cache**: a local mirror of the user's cloud content so Design Space works without the network. It's a C++ helper driven over the `pluginLocalData*` IPC channels (04 §4), speaking **151 `NativeLocalData.Request*/Response*`** protobuf messages — a get/set/delete CRUD over the domains below.

## 2. Storage: encrypted SQLite

- SQLite database **`metadata.db`**, accessed through **SQLCipher** — `cipher_default_kdf_algorithm`, `cipher_default_hmac_algorithm`, `cipher_default_kdf_iter`, `cipher_default_page_size`, `cipher_default_plaintext_header_size` are all present. So the local cache (including entitlements) is **encrypted at rest**.
- Full-text search uses SQLite FTS3/4 (`%q_content`/`%q_segdir`/`%q_docsize` virtual tables) — for searching cached fonts/images/patterns.
- The SQLCipher key derivation is out of scope (legal gate / not needed for schema).

## 3. Entitlement schema (the subscription cache)

Columns: **`entitlement_id`** (key), **`entitlement_expiration_date`**, **`entitlements_data`** (a serialized `PBEntitlementData` blob). Operations: `SetEntitlements`, `GetEntitlementsByIDs`, `GetAllEntitlementIDs`, `DeleteEntitlements`, **`CheckAllEntitlementsValid`**, **`ClearRemainingOrphanEntitlements`**.

This is how **Cricut Access gating works offline**: the app caches the user's entitlement IDs with an expiration date, validates them by date (`CheckAllEntitlementsValid`), and prunes stale/orphan rows. Premium content (images, fonts, patterns) is unlocked locally against this table when offline. Storing it in a SQLCipher DB is what keeps it from being trivially edited.

## 4. Canvas / content schema

| Domain | Columns (tokens) | PB type |
|---|---|---|
| **Canvases** | `canvas_id` (PK), `canvas_data`, `canvas_details`, `canvas_json`, `canvas_json_file_size`, `canvas_cache_timestamp` | `PBOfflineCanvasData`, `PBCanvasDetailsFileData` |
| **Canvas↔entity** (M:N) | `entity_id`, `entity_ids`, `canvas_ids`, `entity_id_canvases_data`, `entity_id_to_canvas_data` | `PBCanvasIDToEntityIDsData`, `PBEntityIDToCanvasesData` |
| **Images** | `image_id` (PK), `image_data`, `image_details`, `image_preview`, `image_preview_url`, `bitmap_data` | `PBCanvasImageData`, `PBImageIsPattern` |
| **Fonts** | `font_id`, `font_family_ids`, `font_family_data`, `font_family_name(s)`, `font_family_preview(_url)`, `font_family_fonts`, `font_chars_data`, `font_metric_data`, `font_file_paths`, `font_id_paths` | `PBFontFamilyData`, `PBFontFamilyLinkData`, `PBSingleFontData(OTF)`, `PBFontFilePaths` |
| **Materials / machine** | `material_settings_data`, `material_sizes_data`, `machine_families_data`, `machine_pressure_settings_data`, `machine_serial`, `pattern_search_filter_data` | — |
| **User / profile** | `user_key`, `user_settings(_data)`, `user_preferences_data`, `user_version`, `profile_id`, `tag_data`, `tag_type` | `PBUserSettingsLD` |

The `canvas_json` / `canvas_data` columns hold the serialized canvas document (the same model recovered in `05` §1 — `CanvasBody`/`Graphic` protobuf), and `entity_id` ties cached canvases to cloud project/entity IDs. `bitmap_data` backs the `GetBitmapFillById` path (raster fills).

## 5. Why this matters

- **Offline capability is real and bounded:** canvases, images, fonts, materials, pens, machine/pressure settings, and entitlements are all cached locally; the cut pipeline can run against this mirror (`01` §4).
- **The entitlement cache is the local half of monetization** — pairs with the cloud `apis.cricut.com/claims` surface (`01` §4). SQLCipher encryption is the tamper barrier.
- No crypto/handshake code is involved here — this is a content cache, distinct from the machine-link security (`03`/`04`).
