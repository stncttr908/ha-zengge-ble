# Walkthrough: Zengge / MagicHome BLE Smart Lamp Controller

We have successfully reverse engineered the **HagallBjarkan** BLE protocol for the Zengge / MagicHome smart lamp ecosystem and implemented both the comprehensive protocol specification and a standalone Python BLE controller.

---

## Deliverables Summary

### 1. Protocol Specification: [`docs/protocol_spec.md`](file:///Users/david/Antigravity/Projects/BLE%20Decryption/docs/protocol_spec.md)
Comprehensive technical documentation covering:
- **GATT Profile**: Service (`0xFFFF`), Write Characteristic (`0xFF01`, Write Without Response), Notify Characteristic (`0xFF02`).
- **Transport Encapsulation (HagallBjarkan Outer Frame)**:
  - 8-byte header: `Ctrl` (`0x00`), `Seq` (`0x01..0xFF`), Marker (`0x8000`), `Length` (16-bit BE), `Len+1` (8-bit), `CmdID` (`0x0A`).
  - Bitmask control flags (protect, ack, segmented, version).
  - Multi-packet segmentation and reassembly for payloads exceeding MTU.
- **Application Layer Commands**:
  - Power ON (`0xCC, 0x23, 0x33`) & Power OFF (`0xCC, 0x24, 0x33`).
  - Static RGB (`0x31, R, G, B, 0x00, 0x00, 0x0F, Checksum`).
  - White / CCT (`0x31, 0, 0, 0, Warm, Cold, 0x0F, Checksum`).
  - Built-in Preset Scenes (`0xBB, ModeID, Speed, 0x44, Checksum`).
  - Extended HagallBjarkan HSV (`0xE0 0x01 0x00 0xA1 ...`) & CCT (`0xE0 0x01 0x00 0xB1 ...`).
  - Status Query (`0x71, 0x23` / `0x71, 0x24`).
- **Notification Response Parsing**:
  - Outer notification frame (`Ctrl=0x04`, `CmdID=0x0C`).
  - JSON payload wrapper `{"code":0,"payload":"..."}` and 26-byte status payload byte mapping.
- **Annotated Packet Dumps**:
  - Side-by-side breakdowns of live HCI capture frames.

---

### 2. Standalone Controller Script: [`scripts/05_controller.py`](file:///Users/david/Antigravity/Projects/BLE%20Decryption/scripts/05_controller.py)
A pure-Python asynchronous BLE controller built with `bleak` and `rich`:
- **Protocol Engine**:
  - `UpperTransportLayer`: Dataclass representation of high-level payloads.
  - `LowerTransportLayerEncoder`: Handles outer header framing and automatic MTU-aware multi-packet segmentation.
  - `LowerTransportLayerDecoder`: Handles single-packet and multi-segment frame reassembly.
  - `ZenggePayloadBuilder`: Encodes all standard and extended Zengge commands with valid checksums.
  - `ZenggeDeviceStatus`: Decodes 26-byte telemetry hex into structured Python dataclasses (power state, mode, color channel, hue, saturation, brightness, CCT, approximate RGB preview).
- **Asynchronous Client (`ZenggeLampClient`)**:
  - Connects via BLE MAC address or macOS CoreBluetooth UUID.
  - Subscribes to `0xFF02` notification characteristic and manages request/response synchronization futures.
  - Transmits encapsulated frames on `0xFF01`.
- **CLI & REPL Interface**:
  - One-off CLI arguments: `--mac`, `--scan`, `--power on|off`, `--rgb R G B`, `--brightness 0-100`, `--scene <ID>`, `--cct <0-100>`, `--status`.
  - Interactive REPL prompt (`zengge> `) with live status panels, color previews, scene listings, and raw frame transmission.

---

### 3. Unit Test Suite: [`tests/test_controller.py`](file:///Users/david/Antigravity/Projects/BLE%20Decryption/tests/test_controller.py)
Automated test suite covering:
- Exact packet match against live capture bytes for Power ON, Power OFF, Status Query, and HSV Red.
- RGB and Scene checksum algorithms.
- Multi-segment payload fragmentation and decoder reassembly.
- Real notification JSON and telemetry byte parsing.
- Color and scene input parsers.

---

## Verification Results

### Automated Unit Tests
```bash
$ .venv/bin/python3 -m unittest discover -s tests
...........
----------------------------------------------------------------------
Ran 11 tests in 0.000s

OK
```

### CLI Options & Help Check
```bash
$ .venv/bin/python3 scripts/05_controller.py --help
usage: 05_controller.py [-h] [--mac MAC] [--scan] [--power {on,off}]
                        [--rgb RGB [RGB ...]] [--brightness BRIGHTNESS]
                        [--cct CCT] [--scene SCENE] [--speed SPEED] [--status]
                        [--interactive] [--timeout TIMEOUT] [--verbose]
```

### BLE Discovery Scan Check
```bash
$ .venv/bin/python3 scripts/05_controller.py --scan
Scanning for nearby Zengge BLE lamps (3.0s)...
                             Discovered BLE Devices                             
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━┳━━━━┓
│ IOTBT537                    │ DC9F4295-5D03-AA2A-5EF5-6EE6449669A4 │ -74│ N/A│
...
```

### Live Physical Hardware Verification
Full end-to-end automated pipeline executing against the physical lamp:
```text
1. Power ON (71 23) -> Success
2. Setting Color -> PURE RED (#FF0000)
   Telemetry: Power ON, Mode 0x61, Channel RGB, Hue 0°, Sat 100%, Bri 100% (EA8100000E0A23610240F0006464...)
3. Setting Color -> PURE GREEN (#00FF00)
   Telemetry: Power ON, Mode 0x61, Channel RGB, Hue 120°, Sat 100%, Bri 100% (EA8100000E0A23610240F03C6464...)
4. Setting Color -> PURE BLUE (#0000FF)
   Telemetry: Power ON, Mode 0x61, Channel RGB, Hue 240°, Sat 100%, Bri 100% (EA8100000E0A23610240F0786464...)
5. Setting Brightness -> 50%
   Telemetry: Power ON, Mode 0x61, Channel RGB, Hue 240°, Sat 100%, Bri 50% (EA8100000E0A23610240F0786432...)
6. Setting Warm White (CCT 0%, Bri 100%) -> Success
7. Activating Scene -> Rainbow Fade (Mode 0x25, Speed 16) -> Success
8. Querying Final Status -> Success
✓ All hardware tests passed!
```

---

## Example Usage

### 1. Scan for Nearby Lamps
```bash
python3 scripts/05_controller.py --scan
```

### 2. Query Lamp Status
```bash
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --status
```

### 3. Set Color & Brightness
```bash
# Set pure red (#FF0000)
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --rgb 255 0 0

# Set color by name with 50% brightness
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --rgb cyan --brightness 50
```

### 4. Activate Native & Dynamic Animated Scenes
```bash
# Reverse-Engineered Firmware Native Presets
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene flame
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene colorful
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene breathe
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene grassland
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene sunset
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene blue-sky

# High-Framerate Dynamic Software Scenes
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene rainbow --duration 15 --speed 20
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene candle --duration 10
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene aurora --duration 20
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene pulse --speed 16
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --scene police --duration 5
```

### 5. Launch Interactive REPL
```bash
python3 scripts/05_controller.py --mac AA:BB:CC:DD:EE:FF --interactive
```
```text
zengge> on
zengge> scenes             # Displays full table of all 26 native presets & customs
zengge> scene flame        # Plays native Flame animation
zengge> scene colorful     # Plays native Colorful cycle
zengge> scene rainbow 20   # Plays smooth rainbow flow
zengge> rgb cyan
zengge> brightness 60
zengge> cct 0 100
zengge> off
zengge> exit
```
