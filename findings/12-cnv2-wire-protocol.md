# CNV2 Wire Protocol — Prior Art & Capture Plan

**Target:** Explore/Joy/Maker-era (CNV2) + legacy Provo-Craft machines of Cricut Design Space 10.9.118 · **Method:** survey of open-source prior-art controllers (read-only; no code copied) cross-referenced against our 142 `NativeModel.Bridge.PB*` names · **Date:** 2026-10-27
**Boundary:** The secure-session handshake / AES session / key agreement (SPEC §0.3.1) is **out of scope**. Where a repo implements it, only the *existence* and the plaintext framing are noted — the crypto is not documented. Legal gate (README #6) applies before any machine-link implementation.

## 1. Prior-art repos surveyed

| Repo | URL | Commit | License | Era / target | Value here |
|---|---|---|---|---|---|
| **FreeKnife** | github.com/OddPig/FreeKnife | `3dd2bc6` | none stated (⚠ all-rights-reserved; describe only) | **CNV2 — Explore Air 2**, USB serial | **Byte-level opcode table + framing** |
| **libcutter** | github.com/vangdfang/libcutter | `d7711ed` | LGPL-2.1 | Legacy — Personal/Expression/Create/Cake, serial | Legacy command bytes + XXTEA framing |
| **slicebug** | github.com/XtremeCoder007/slicebug | `b9e1ad8` | none stated (⚠ describe only) | **CNV2 — Explore/Maker**, via CDS plugin | Reconstructed `Bridge.proto` **field tags**; confirms PB vocabulary |
| **FreeExpression** | github.com/markawilliamson/FreeExpression | `094b670` | GPL-family (18K LICENSE) | Legacy — firmware *replacement* | Alternative-firmware approach (HPGL/GPGL), not Cricut protocol |
| **grasshopper** | github.com/CutFreedom/grasshopper | `a953ed0` | 6.9K LICENSE | Cloud + firmware tooling | `api.cricut.com` local replacement + `app.asar` unpacker — **not** wire-level |

All clones are in scratch (`…/scratchpad/priorart/`), outside the project tree, per clean-room rules. None of their source is reproduced below; commands are described in our own words.

## 2. Per-repo command models

### 2.1 FreeKnife — CNV2 (Explore Air 2), USB serial [C for framing/opcodes]
**Framing:** each message = a length prefix (1 or 2 bytes) + payload. The **high bit of the length is a cipher flag** (`len & 0x80` / `len & 0x8000`): set ⇒ the payload is session-encrypted; clear ⇒ plaintext. This corroborates our local-socket frame (`03` §5.1) at the *machine* layer — same "length + flag + payload" shape.

**Plaintext opcode table** (opcode byte → meaning; args in our words):

| Cmd | Opcode | Args | Meaning |
|---|---|---|---|
| BeginCut | `0x21` | fixed | start a cut job |
| EndCut | `0x22` | fixed | end a cut job |
| Move | `0x43` | `type` (uint8), `x` (float32 LE), `y` (float32 LE) | tool move/draw to (x,y); `type` selects up/down/tool |
| GetStatus | `0x60` | fixed | poll machine status (response byte 0 == `0x60`) |
| ClearErrors | `0x0A` | — | clear error state |
| SetSpeedsAndFeeds | `0x31` | value | set speed/force feeds |
| SeedRandom | `0xCF` | random bytes | seed RNG |
| Unknown30 / UnknownSet74 | `0x30` / `0x74` | value | purpose not identified |
| *PreHandshake* | `0xE5` | fixed, len 64 | **session setup — §0.3 boundary, not analyzed** |
| *NewAES* | `0xC7` | random | **session key op — §0.3 boundary, not analyzed** |

Devices are matched by USB `manufacturer` string containing "Provo"/"Cricut" (not a fixed VID/PID) [O].

### 2.2 libcutter — legacy serial (Personal/Expression/Create/Cake) [C]
Each geometry command is a `0x40`-prefixed packet carrying a 3-word coordinate payload **XXTEA-encrypted** with a per-command key (`MOVE_KEY`/`LINE_KEY`/`CURVE_KEY`), keys deliberately withheld by the project:

| Cmd | Encoding | Meaning |
|---|---|---|
| move_to(pt) | `0x40` + XXTEA(3 words, move_key) | pen-up move |
| cut_to(pt) | `0x40` + XXTEA(3 words, line_key) | pen-down cut |
| curve_to(p0..p3) | 4× `0x40` + XXTEA(…, curve_key) | Bézier via 4 control points |
| start | `0x21` (32-bit) | begin |
| stop | `0x22` (32-bit) | end |
| init/hello | `0x12` (32-bit); responses `0x14`/`0x1e`/`0x0a` | connect handshake |

**Cross-era continuity [C]:** `start=0x21` / `stop=0x22` are identical to FreeKnife's `BeginCut`/`EndCut`, and `0x0a` appears in both (libcutter init response, FreeKnife ClearErrors). The CNV2 opcode space inherits from the legacy serial protocol; `0x40`(legacy move) → `0x43`(CNV2 Move) and coordinates shifted from fixed-point XXTEA words to plaintext float32-LE.

### 2.3 slicebug — CNV2 via the official plugin [C]
Does **not** byte-decode the machine link. It drives Design Space's own `device-common` plugin, sending `NativeModel.Bridge.PB*` messages and letting the plugin encrypt (it copies CDS's key material at "bootstrap"). Its `send()` = `send_bytes(encrypt_request(message))` — confirming the app-layer path is *PB message → encrypt → bytes* (our `03` §5), with crypto reused, not reimplemented. Its reconstructed `Bridge.proto` carries **real field tags** for 9 messages + 2 enums — see §3 and the note for Gap 1.

### 2.4 FreeExpression / grasshopper
FreeExpression replaces the AVR firmware so a legacy machine speaks **HPGL/GP-GL** plotter languages (Docs: `HP-GL.pdf`, `GP-GL.pdf`) — an alternative-firmware route, not the Cricut protocol. grasshopper is a local `api.cricut.com` replacement server + an `app.asar` unpacker (same extraction our project did) — relevant to the **cloud** surface (SPEC §10), not the machine wire.

## 3. PB ↔ wire first-pass mapping

Two different layers: our **142 PB messages** are the app/plugin Bridge objects; FreeKnife's **opcodes** are the machine-firmware commands the plugin ultimately emits. Mapping is therefore app-message → opcode-sequence, mostly inferred.

| PB message (ours) | Wire (prior art) | Confidence |
|---|---|---|
| `PBMatPathData.pathData` (SVG string, tag 2 — slicebug) | expands to `Move(0x43)` sequences (float32-LE x/y) | **inferred** |
| `PBMatCutExecutionPlan` / `PBCutExecution` / `PBForceExecution(Plan)` | `BeginCut(0x21)` → `Move(0x43)…` → `EndCut(0x22)` | **inferred** |
| `PBDrawVector(s)` | `Move(0x43)` with pen `type` | **inferred** |
| `PBMachineStatus` / `PBGetFullStatus` | `GetStatus(0x60)` | **inferred** |
| `PBSpeedSettingsZTS` / `PBToolSettingsZTS` / `PBForceCurve` | `SetSpeedsAndFeeds(0x31)` | **inferred** |
| secure-session PB fields (`PBCommonBridge.authData`, device hello/key) | `PreHandshake(0xE5)` / `NewAES(0xC7)` | **boundary — not mapped (§0.3)** |
| ~130 others (theta/backlash/fiducial/force-gauge/cartridge/calibration/…) | no prior-art coverage | **unknown** |

Honest tally: **1 partial-known** (cut path → Move), **5 inferred groups**, **2 crypto-boundary**, **~130 unknown**. Prior art covers only the minimal Explore-Air-2 cut path; the richer command set (calibration, force gauges, Print-Then-Cut fiducials, cartridges) has no public wire mapping.

## 4. Hardware capture plan (for when a CNV2 machine is available)

Goal: record one real cut on a **pre-Bifrost / non-session-crypto CNV2 machine** (Explore Air 2 / Explore One / original Maker over USB-serial or BT-classic) to confirm the framing and plaintext opcodes above. Do **not** target Scout/Bifrost ≥31 (session-encrypted) and do **not** attempt to decrypt cipher-flagged frames or recover keys (§0.3).

1. **Serial pass-through MITM (preferred, USB machines).** Insert a logging tap between Design Space and the machine (two USB-serial adapters bridged by a pass-through logger, or `socat`/`tee` on a Linux host presenting a virtual port). Log every byte both directions with timestamps. This yields exact framing: length byte(s), the cipher-flag high bit, and plaintext opcodes (`0x21`/`0x22`/`0x43`/`0x60`/…).
2. **USB bus capture (alternative).** Linux VM (or Raspberry Pi) with `usbmon` + Wireshark, or a hardware USB analyzer, capturing the CDC-serial endpoint during a cut.
3. **BLE capture (BLE machines).** macOS **PacketLogger** (Additional Tools for Xcode) HCI capture, or an nRF sniffer, during discovery+connect+cut. Expect the GATT write/notify characteristics (`03` §4.1) carrying the same framed payloads; BLE on Bifrost machines will be session-encrypted.
4. **What to log:** full byte stream, direction, timestamps; note which frames have the cipher flag set vs clear; capture status polls idle vs active.
5. **Alignment to PB vocabulary:** enable Design Space's own Bridge logging (the "Enable/Disable Bifrost Logging to file" flag; cf. `analysis/evidence/bridge.log`) and correlate by timestamp — each logged PB command lines up with a captured frame, turning §3's "inferred" rows into "known" where the frame is plaintext. Encrypted frames stay opaque and are left so.

## 5. Limitations

- No hardware was captured; §§2–3 are from prior-art source review only.
- FreeKnife/slicebug have **no stated license** — treated as all-rights-reserved; only behavior is described, no code copied. libcutter (LGPL) and FreeExpression (GPL-family) permit reuse but none is copied here.
- FreeKnife's opcode set is the **minimal** Explore-Air-2 path; newer machines' richer commands are unmapped.
- The cipher-flagged (encrypted) frames and all handshake opcodes (`0xE5`, `0xC7`) are the §0.3 boundary and were not analyzed.
- **Spillover for Gap 1:** slicebug's `protobufs/…/Bridge.proto` contains real field tags for `PBCommonBridge`, `PBMatPathData`, `PBMaterialSelected`, `PBBridgeSelectedTools`, `PBCricutDeviceSerialized`, `PBToolInfo`, `PBAccessoryV2`, `PBInteractionHandle`, `PBMatFiducialData` + enums `PBInteractionStatus`/`PBConnectionType` — an independent cross-check for the native-descriptor extraction. (PBCommonBridge includes an `authData` field = the session envelope; its crypto is out of scope.)
