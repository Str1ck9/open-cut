# Cricut Internal Machine Codenames (extracted from Design Space 10.9.118)

**Revised 2026-10-27.** The first version listed 18 codenames and classed GANDALF/DUMBLEDORE/PSYCHE/EROS/RIDDLE/NEWT as heat presses. **That was wrong.** They're cutting machines (§2). The enum has **25 families and 72 machine types**.

Sources (all in `unpacked/design-space-app/` unless noted):
- `chunk-BYrF6YNd.js`: machine-type enum, the `deviceTypeEnum` numeric IDs, the MT→family switch, and **per-family descriptor objects** (`family`, `apiFamilyString`, `communicationType`, `category`, `isBluetoothOnly`, `bridgeMachineTypes`, images)
- `chunk-D1dob9Im.js`: family→displayName switch
- `canvas-webw-path.js`: numeric family enum (`ROOTBEER=7, VULCAN=8, ZEUS_FAMILY=9, BROOKLYN=10, ATMOSPHERE=11, MARS_FAMILY=12 … SCOUT_FAMILY=27, DTF_FAMILY=28, HYDROGEN=29, HYDROGEN_LITE=30`)
- `static-asset/design3/translation/en_US.json`: `OOB_*_LABEL` product names
- `static-asset/design3/{cutting-machines,machines-transparent,heatpress-machines-transparent}/`: product images

Confidence key: **C** = confirmed by displayName, OOB label, or family descriptor image. **I** = inferred.

## 1. Communication-type enum

`{BIFROST=0, CNV2=1, ODM=2}`. Each family descriptor declares one. **Only four families use `BIFROST`:** DUMBLEDORE, EROS, GANDALF, PSYCHE. Everything else with a descriptor is `CNV2`. No descriptor uses `ODM`. See `04` §4 for how this maps to device paths.

## 2. Cutting machines

| Family | Machine type(s) [deviceTypeEnum] | Product | Comm | BT-only | Conf. |
|---|---|---|---|---|---|
| EXPLORE | ZORRO [7], HELIUM [8], WARRO [9], HELIUM2 [10], BLUETOOTH_MODULE [-99] | Explore / One / Air / Air 2 (+ BT dongle) | CNV2 | no | C |
| MAKER | ATHENA [11] | Maker | CNV2 | no | C |
| CUPID | CUPID [12] | Joy | CNV2 | yes | C |
| MORPHEUS | MORPHEUS [13] | Venture | CNV2 | no | C (displayName `Venture`) |
| SCAMANDER | SCAMANDER [14] | Maker 3 | CNV2 | no | C (`Maker3`, OOB label) |
| VOLDEMORT | VOLDEMORT [15] | Explore 3 | CNV2 | no | C (`Explore3`, OOB label) |
| MARS | CUPIDXL [19] | Joy Xtra | CNV2 | yes | C (image `joy-xtra.png`) |
| **NEWT** | NEWT [22], LOKI_NEWT [-204] | **Maker 4** | CNV2 | no | C (image `maker4.png`) |
| **RIDDLE** | RIDDLE [23], LOKI_RIDDLE [-205] | **Explore 4** | CNV2 | no | C (image `explore4.png`) |
| **DUMBLEDORE** | DUMBLEDORE [20], LOKI_DUMBLEDORE [-202] | No public name in this build | **BIFROST** | no | C category=cutting |
| **PSYCHE** | PSYCHE [21], LOKI_PSYCHE [-203] | No public name in this build | **BIFROST** | yes | C category=cutting |
| **EROS** | EROS [25], LOKI_EROS [-207] | No public name in this build; shares `psyche.png` (PSYCHE variant?) | **BIFROST** | yes | C category=cutting; variant link I |
| **GANDALF** | GANDALF [24], LOKI_GANDALF [-206] | No public name in this build | **BIFROST** | no | C category=cutting |
| GEMINI | GEMINI [26] | No public name in this build; `DH_MACHINES_GEMINI_SUPPORT` flag | (no descriptor) — uses CDIO path per `04` §4 | — | C displayName `Gemini` |
| SCOUT | SCOUT [27] | No public name in this build; BLE + IP; secure session required on Bifrost FW 31.0.0+ | (no descriptor) — CDIO path | — | C displayName `Scout` |

## 3. Heat presses (`category: heatpress`, all CNV2)

| Family (api string) | Machine type(s) [deviceTypeEnum] | Product | Conf. |
|---|---|---|---|
| EASY_PRESS2 (`EASYPRESS_TWO_FAMILY`) | EZP_APP_MODE [-101], EZP_EP6/9/12 × 120/230 V [-102…-107] | EasyPress 2 (6″/9″/12″) | C (OOB label) |
| DTF (`DTF_FAMILY`; API-mapped to `EASYPRESS_TWO_FAMILY`) | DTF_EASY_PRESS | EasyPress (DTF) | C |
| ATMOSPHERE | ATMOSPHERE9/12 × 110/230 V [-116…-119] | **EasyPress 3** (9″/12″) | C (`OOB_ATMOSPHERE_LABEL`) |
| BROOKLYN | BROOKLYN_110/230 [-120, -121] | **Hat Press** | C (`OOB_BROOKLYN_LABEL`, `hat-press.png`) |
| ROOTBEER (`MUG_PRESS_FAMILY`) | ROOT_BEER, ROOT_BEER_APP, ROOT_BEER_230, ROOT_BEER_APP_230 [-108,-110,-112,-114] | **Mug Press** | C (`OOB_ROOTBEER_LABEL`) |
| VULCAN | VULCAN [-109], VULCAN_APP [-111] | **AutoPress** | C (`OOB_VULCAN_LABEL`, `autopress.png`) |
| HYDROGEN | HYDROGEN [-1] | AutoPress 2 (`OOB_HYDROGEN_LABEL` = "Cricut AutoPress™ 2") | C |
| HYDROGEN_LITE | HYDROGEN_LITE [-2] | Lighter AutoPress-class press (`hydrogen-lite.png`) | I |

## 4. Machine types with no family descriptor

| Machine type(s) [deviceTypeEnum] | Notes | Conf. |
|---|---|---|
| NEUTRON / PROTON / QUARK / QUARK_LT × 110/230 V [-124…-131] | Mains-voltage variants, numbered next to the presses → likely unreleased heat presses | I |
| TITAN [28], RANGER [29], SPRITE [30], VOYAGER [31] | Positive IDs after SCOUT → newest/unreleased line (cutter numbering). A "Titan Support" dev-tools flag exists in main-strings. | I |
| INCREDIBOY [17], UNDERMINER [18], LOKI_INCREDIBOY [-201], LOKI_UNDERMINER [-200] | Between Explore 3 and Joy Xtra in numbering; unreleased or cancelled | I |
| ZEUS [16] (`ZEUS_FAMILY`) | Family exists, no descriptor | I |
| `LOKI_*` [-200…-207] | Variant of 8 families (UNDERMINER, INCREDIBOY, DUMBLEDORE, PSYCHE, NEWT, RIDDLE, GANDALF, EROS). Purpose unknown (factory/test/regional?) | I |
| SMARTIES [-98] | Accessory-range ID next to BLUETOOTH_MODULE/CART_ADAPTER | I |
| V1 [1], EXPRESSION [2], CREATE [3], EXPRESSION2 [4], MINI [5], CART_ADAPTER [-100] | Legacy cartridge-era machines + cartridge adapter | C (well-known product names) |
| NOT_IMPORTANT [0] | Sentinel | C |

## 5. Connection types (enum `Ae`; carried over from the original pass, not re-verified)

- `USB_CT`: USB
- `BLUETOOTH_CT`: classic Bluetooth
- `BLE_CT`: Bluetooth Low Energy (Scout BLE advertising is confirmed via CDIO fix strings)
- `IP_TCP_CT`: TCP/IP with mDNS discovery (Scout stored-IP strings confirm it's in use)

~~"BLE_CT — Bifrost-family machines: Maker 3, Explore 3, Joy Xtra"~~ **Retracted.** Maker 3, Explore 3 and Joy Xtra are `communicationType: CNV2`. The `BIFROST` comm type belongs to DUMBLEDORE/EROS/GANDALF/PSYCHE only (§1).

## 6. Discovery & connection services (renderer, not obfuscated)

- `BifrostDeviceDiscoveryManager`: discovery for `BIFROST`-comm machines
- `DeviceManager` / `DeviceManagerService`: central device registry
- `MachineConnectionManager`, `OOB Cnv2 Connection Manager`: out-of-box connection flows
- `FirmwareUpdateInteractionService`: firmware update UX (aware of connection type)
- `DeviceIdentityResolver`: identity-based matching for Bridge-enumerated (CNV2) machines

## 7. Image assets

- `cutting-machines/`: dumbledore, explore{,-air,-air2,-one,3,4}, gandalf, gemini, joy, joy-xtra, maker{,3,4}, psyche, scout, venture
- `machines-transparent/`: cupid, dumbledore, easypress2, explore{,-air,-air2,-one,4}, gandalf, gemini, maker{,4}, mars, morpheus, psyche, scamander, scout, voldemort
- `heatpress-machines-transparent/`: autopress, easypress-2, easypress-3, hat-press, hydrogen, hydrogen-lite, mug-press
