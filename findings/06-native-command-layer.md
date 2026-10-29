# Native Command Layer — `device-common/CricutDevice` dispatch

**Target:** Cricut Design Space v10.9.118 · **Method:** REA Ghidra v12.1.4 on the thinned arm64 slice (`lipo -thin arm64`), `binary_overview` / `search_procedures` / `search_strings` · 2026-10-27
**Scope:** Dispatch *architecture* only. Command-handler bodies (which include the encrypted-session path) were **not** decompiled — legal gate, README #6.

## 1. Binary shape

`device-common/CricutDevice` arm64 slice (5.0 MB, from the 11.1 MB universal): **15,901 procedures, 17,988 strings, 41 segments**. **No `__swift5_*` sections** — this is pure **C++/ObjC**, in contrast to the Swift transport helper (`CricutDeviceIO`, 03 §2a). Running build: **v6.12.13**, launched `--new-comm-lib` (05 §5).

## 2. Symbols are stripped at the method level

The class method symbols are **not** in the procedure-name table — `search_procedures` for `CricutDevice`, `CommandType`, `dispatch`, `handleCommand`, `executeCommand` all return empty. The class/method identities survive only as **data strings**: C++ RTTI type names, `fmt` log-formatter type tags (e.g. `fmt::…format_custom<send_command_result>` — so `send_command_result` is a *loggable struct*, not a function), and `__cxa_guard` symbols for function-local statics. Ghidra therefore names the handlers `FUN_<addr>`. Full switch reconstruction would require decompiling those anonymous functions by hand.

## 3. Dispatch architecture (recovered from symbol/RTTI evidence)

Two named anchors establish the shape:

| Symbol (demangled) | Role |
|---|---|
| `CommandTypes::get_command(CommandTypes::CommandTypes)` | **Command resolver/factory** — maps a `CommandTypes` enum value to its command object/handler. ≈12 references across `__text` (the dispatch call sites). |
| `CricutDevice::is_in_cutting_session(CommandType)` | **Session-state gate** — classifies a command by membership in a static local `cutCommands` set (the `__cxa_guard`/`_ZGVZ…cutCommands` symbols are the guard for that lazily-initialized set). |

So the model is: an incoming request carries a command-type enum → `CommandTypes::get_command()` resolves it to a handler → `CricutDevice` executes it, with `is_in_cutting_session()` gating which commands are legal for the current machine state (cut commands require/associate with an active cutting session).

Two related enum names appear: **`CommandType`** (used by `CricutDevice::is_in_cutting_session`) and **`CommandTypes::CommandTypes`** (used by `get_command`). They are probably a public command-type and an internal command-id enum; the exact relationship is inside the stripped bodies.

The **command *vocabulary*** these resolve to is already documented: the 142 `NativeModel::Bridge::PB*` protobuf message names (`03` §4, `analysis/bridge-protobuf-messages.txt`). This layer is what turns a `PB*` request into a machine operation.

## 4. What was deliberately not done

- **Enumerating the `CommandTypes` values** and the `cutCommands` membership — needs decompiling `get_command` and `is_in_cutting_session`, whose handler table fans out to every command including the encrypted-session commands. That is the legal-gate boundary.
- **Any crypto/handshake function.** Not searched, not read.

## 5. If this is pursued later (not now)

1. `analyze_function` on the `FUN_*` at the `get_command` call sites (addresses around `0x10048*`) would yield the enum→handler table — but see §4.
2. The `CommandType`/`CommandTypes` enumerators would also fall out of the protobuf descriptor data in the binary (`search_strings` for `NativeModel.Bridge`), which is lower-risk than decompiling handlers.
3. All of this stays behind README #6 for the parts that touch the secure session.
