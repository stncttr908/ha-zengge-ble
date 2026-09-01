# Zengge / MagicHome BLE Smart Lamp Protocol Specification
## HagallBjarkan Transport & Application Layer Specification

---

## 1. Overview

This document provides a reverse-engineered specification for the Bluetooth Low Energy (BLE) communication protocol used by **Zengge / MagicHome** smart lamps, LED bulbs, and strip controllers employing the **HagallBjarkan** (`com.zengge.hagallbjarkan`) transport layer.

The protocol consists of:
1. **GATT Layer**: Standard BLE GATT Service and Characteristics (`0xFFFF` service).
2. **Outer Transport Layer (HagallBjarkan Frame)**: Encapsulation layer providing framing, sequence counters, command routing, and optional MTU-based segmentation.
3. **Inner Application Layer**: Standard MagicHome binary control commands (`0x31`, `0xCC`, `0xBB`, `0x71`) and extended HagallBjarkan parameter frames (`0xE0`).
4. **Notification Response Layer**: JSON-wrapped status telemetry over characteristic `0xFF02`.

---

## 2. GATT Architecture

| Attribute Type | UUID | Handle (Typical) | Properties | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Service** | `0000ffff-0000-1000-8000-00805f9b34fb` (`0xFFFF`) | `0x0010` | - | Main Zengge device control service |
| **Write Characteristic** | `0000ff01-0000-1000-8000-00805f9b34fb` (`0xFF01`) | `0x0017` | `Write Without Response` (`0x04`), `Write` (`0x08`) | Host-to-Device command transmission |
| **Notify Characteristic** | `0000ff02-0000-1000-8000-00805f9b34fb` (`0xFF02`) | `0x0014` | `Notify` (`0x10`), `Read` (`0x02`) | Device-to-Host status telemetry & JSON responses |
| **OTA Service** | `0000fe00-0000-1000-8000-00805f9b34fb` (`0xFE00`) | - | - | Firmware Over-The-Air upgrade service |
| **OTA Write** | `0000ff11-0000-1000-8000-00805f9b34fb` (`0xFF11`) | - | `Write Without Response` | Firmware binary chunk write |
| **OTA Notify** | `0000ff22-0000-1000-8000-00805f9b34fb` (`0xFF22`) | - | `Notify` | OTA step acknowledgment & CRC validation |

---

## 3. Outer Transport Layer (HagallBjarkan Framing)

Every message transmitted over GATT characteristic `0xFF01` (and received on `0xFF02`) is encapsulated in a **Lower Transport Layer** outer header.

### 3.1 Unsegmented Outer Frame Structure (Payload $\le \text{MTU} - 8$)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     Ctrl      |      Seq      |         Marker (0x8000)       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     Length (16-bit BE)        |    Len + 1    |     CmdID     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                   Inner Payload (N Bytes) ...                 |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

#### Byte Mapping Table
| Byte Offset | Field Name | Type | Description |
| :--- | :--- | :--- | :--- |
| `0` | **Ctrl** | `uint8` | Control flag byte (bitmask defined below). Typically `0x00` for outgoing commands, `0x04` for incoming JSON notifications. |
| `1` | **Seq** | `uint8` | Sequence number counter (`0x01` $\dots$ `0xFF`), incremented per write. |
| `2..3` | **Marker** | `uint16_be` | Fixed constant `0x8000` (`Short.MIN_VALUE` / `-32768`). |
| `4..5` | **Length** | `uint16_be` | 16-bit Big-Endian length of the `Inner Payload` ($N$). |
| `6` | **Len+1** | `uint8` | Length of inner payload plus one: `(N + 1) & 0xFF`. |
| `7` | **CmdID** | `uint8` | Application Command ID: `0x0A` for standard commands, `0x0C` for notification responses. |
| `8..8+N-1` | **Inner Payload** | `bytes[N]` | High-level device command or UTF-8 telemetry string. |

---

### 3.2 Control Byte (`Ctrl`) Bitmask

The `Ctrl` byte at offset `0` is constructed as follows:
- **Bit 7**: Reserved / Retry bit (set to `1` when retrying unacknowledged packets).
- **Bit 6**: `is_fragmented` (`1` = segmented multi-packet payload, `0` = single unsegmented packet).
- **Bit 5**: `is_protect` (`1` = encrypted/protected frame, `0` = plaintext).
- **Bit 4**: `is_ack` (`1` = acknowledgment requested, `0` = unacknowledged write).
- **Bit 3..2**: Payload format (`00` = Binary, `01` = UTF-8 JSON String, `10` = ACK packet).
- **Bit 1..0**: Protocol Version (`00` = Version 0 / 255-byte MTU, `01` = Version 1 / 512-byte MTU).

*Standard client write:* `0x00` (Unsegmented, Plaintext, No ACK, Version 0).  
*Standard device notification:* `0x04` (Unsegmented, Type=1 JSON, Version 0).

---

### 3.3 Multi-Packet Segmentation (Payload $> \text{MTU} - 8$)

When payload length exceeds the single-packet capacity ($\text{MTU} - 8$):
1. **First Segment (Segment 0)**:
   - Header (8 bytes): `Ctrl` (with Bit 6 set: `0x40`), `Seq`, `0x00 0x00` (segment index 0), `TotalPayloadLength` (16-bit BE), `ChunkLength + 1`, `CmdID` (`0x0A`).
   - Data: First $\text{MTU} - 8$ bytes of payload.
2. **Subsequent Segments (Segment $K$)**:
   - Header (5 bytes): `Ctrl` (`0x40`), `Seq`, `0x00` or `0x80` (MSB set on final segment) + `SegmentIndex` (16-bit BE), `ChunkLength`.
   - Data: Next slice of payload.

---

## 4. Inner Application Layer Commands

All inner command payloads are placed starting at offset `8` of the outer frame.

### 4.1 Checksum Algorithm
For commands requiring a checksum, the checksum byte is the least significant byte of the sum of all preceding command bytes:
$$\text{Checksum} = \left(\sum_{i=0}^{L-1} \text{Byte}_i\right) \pmod{256}$$

---

### 4.2 Standard MagicHome Commands

#### 1. Power ON
- **Inner Payload**: `0xCC, 0x23, 0x33` (3 bytes)
- **Full Outer Frame** (`Seq=0x01`):
  `00 01 80 00 00 03 04 0A CC 23 33`

#### 2. Power OFF
- **Inner Payload**: `0xCC, 0x24, 0x33` (3 bytes)
- **Full Outer Frame** (`Seq=0x02`):
  `00 02 80 00 00 03 04 0A CC 24 33`

#### 3. Set Static RGB Color
- **Inner Payload** (8 bytes):
  `0x31, <R>, <G>, <B>, 0x00, 0x00, 0x0F, <Checksum>`
  - `<R>`, `<G>`, `<B>`: Color channel intensities (`0x00` $\dots$ `0xFF` / $0 \dots 255$).
  - `0x00, 0x00`: Warm White / Cold White components (disabled in pure RGB mode).
  - `0x0F`: RGB write mask indicator.
  - `<Checksum>`: `(0x31 + R + G + B + 0x00 + 0x00 + 0x0F) & 0xFF`.
- **Example: Pure Red (`#FF0000`)**:
  - Inner: `31 FF 00 00 00 00 0F 3F`
  - Full Frame: `00 03 80 00 00 08 09 0A 31 FF 00 00 00 00 0F 3F`

#### 4. Set White / Color Temperature (CCT)
- **Inner Payload** (8 bytes):
  `0x31, 0x00, 0x00, 0x00, <WarmWhite>, <ColdWhite>, 0x0F, <Checksum>`
  - `<WarmWhite>`: Warm white intensity (`0x00` $\dots$ `0xFF`).
  - `<ColdWhite>`: Cold white intensity (`0x00` $\dots$ `0xFF`).
  - `<Checksum>`: `(0x31 + 0x00 + 0x00 + 0x00 + Warm + Cold + 0x0F) & 0xFF`.

#### 5. HagallBjarkan Native Preset Dynamic Effects / Scenes
- **Inner Payload** (6 bytes):
  `0xE0, 0x02, 0x00, <SceneID>, 0xFF, 0xFF`
  - `<SceneID>`: Built-in scene identifier (see table below).
  - `0xFF, 0xFF`: Speed and brightness parameters (or auto mask).
- **Full Outer Frame** (e.g. Preset Colorful `0x0A`, `Seq=0x04`):
  `00 04 80 00 00 06 07 0A E0 02 00 0A FF FF`

##### Reverse-Engineered HagallBjarkan Scene Mode Catalog
| Scene ID (Hex) | Scene ID (Dec) | Alias / Name | Category | Description |
| :--- | :--- | :--- | :--- | :--- |
| `0x25` | 37 | `gradient-3` | Custom | Three Color Gradient |
| `0x26` | 38 | `jump-5` | Custom | Five Color Jump |
| `0x27` | 39 | `colorful-breath` | Custom | Colorful Breath |
| `0x28` | 40 | `heartbeat` | Custom | Heartbeat Pulse |
| `0x29` | 41 | `lightning` | Custom | Lightning Strobe |
| `0x2C` | 44 | `flame` | Custom | Realistic Candle / Fireplace Flame |
| `0x01` | 1 | `breathe` | Preset | Breathe Transition |
| `0x02` | 2 | `step-change` | Preset | Step Change |
| `0x03` | 3 | `rhythm-change` | Preset | Rhythm Change |
| `0x04` | 4 | `leisure` | Preset | Leisure Ambience |
| `0x05` | 5 | `night-light` | Preset | Night Light |
| `0x06` | 6 | `good-night` | Preset | Good Night |
| `0x07` | 7 | `read` | Preset | Reading Mode |
| `0x08` | 8 | `work` | Preset | Work Mode |
| `0x09` | 9 | `grassland` | Preset | Grassland Ambience |
| `0x0A` | 10 | `colorful` | Preset | Colorful Dynamic Cycle |
| `0x0B` | 11 | `dazzling` | Preset | Dazzling Dynamic Shift |
| `0x0C` | 12 | `gorgeous` | Preset | Gorgeous Atmosphere |
| `0x0D` | 13 | `blue-sky` | Preset | Blue Sky |
| `0x0E` | 14 | `sunflower` | Preset | Sunflower Amber Glow |
| `0x0F` | 15 | `forest` | Preset | Forest Emerald Shift |
| `0x10` | 16 | `mediterranean` | Preset | Mediterranean Ocean Blend |
| `0x11` | 17 | `french-style` | Preset | French Style Pastel Glow |
| `0x12` | 18 | `american-style` | Preset | American Style |
| `0x13` | 19 | `birthday` | Preset | Birthday Party Dynamic Cycle |
| `0x14` | 20 | `wedding` | Preset | Wedding Day Romantic Mood |

#### 6. Query Device Status
- **Inner Payload**: `0x71, 0x23` (or `0x71, 0x23, 0x94`)
- **Full Outer Frame** (`Seq=0x07`):
  `00 07 80 00 00 02 03 0A 71 23`

---

### 4.3 Extended HagallBjarkan HSV / CCT Parameter Frames

Observed in live companion app captures for high-granularity color wheel navigation:

#### 1. Set HSV Color (`0xA1` Subcommand)
- **Inner Payload** (14 bytes):
  `E0 01 00 A1 <HueDiv2> <Saturation%> <Brightness%> 00 00 00 00 14 00 00`
  - `<HueDiv2>`: Hue angle divided by 2 (`0` $\dots$ `180` representing $0^\circ \dots 360^\circ$).
    - Red ($0^\circ$): `0x00`
    - Green ($120^\circ$): `0x3C` (60)
    - Blue ($240^\circ$): `0x78` (120)
  - `<Saturation%>`: Saturation percentage (`0` $\dots$ `100` / `0x00` $\dots$ `0x64`).
  - `<Brightness%>`: Brightness percentage (`0` $\dots$ `100` / `0x00` $\dots$ `0x64`).
  - `14 00 00`: Transition duration / parameter flags.

#### 2. Set CCT White Level (`0xB1` Subcommand)
- **Inner Payload** (14 bytes):
  `E0 01 00 B1 00 00 00 <CCT%> <Brightness%> 00 00 14 00 00`
  - `<CCT%>`: Color temperature balance (`0` = 100% Warm White $\dots$ `100` / `0x64` = 100% Cool White).
  - `<Brightness%>`: White channel brightness (`0` $\dots$ `100` / `0x00` $\dots$ `0x64`).

---

## 5. Notification Telemetry & Response Parsing

When characteristic `0xFF02` notifies, the payload contains an outer transport frame with `Ctrl=0x04` and `CmdID=0x0C` wrapping a UTF-8 JSON response string.

### 5.1 JSON Response Wrapper
```json
{
  "code": 0,
  "payload": "EA8100000E0A23610240F0006464000000000000000000000000"
}
```
- `code`: Status return code (`0` = Success).
- `payload`: Hex-encoded 26-byte telemetry status packet.

---

### 5.2 Status Packet Byte Map (26 Bytes / 52 Hex Characters)

| Byte Range | Hex in Capture | Field Name | Description & Decoded Values |
| :---: | :---: | :--- | :--- |
| `0..1` | `EA 81` | **Magic Header** | Fixed Zengge device identifier header (`0xEA81`). |
| `2..3` | `00 00` | **Reserved** | Reserved zero padding. |
| `4..5` | `0E 0A` | **Length / Cmd** | Payload length (`14` bytes) and Command ID (`0x0A`). |
| `6` | `23` / `24` | **Power State** | `0x23` = **Power ON**<br>`0x24` = **Power OFF** |
| `7` | `61` / `70` / `25..38` | **Operating Mode** | `0x61` = Color / CCT Mode<br>`0x70` = White / Static Mode<br>`0x25`..`0x38` = Built-in Dynamic Scene |
| `8..9` | `02 40` | **Version Flags** | Device model & firmware capability flags. |
| `10` | `F0` / `0F` | **Channel Flag** | `0xF0` = RGB / HSV Mode Active<br>`0x0F` = White / CCT Mode Active |
| `11` | `00` $\dots$ `B4` | **Hue / Warmth** | - In RGB mode: $\text{Hue Angle} / 2$ ($0 \dots 180 \rightarrow 0^\circ \dots 360^\circ$)<br>- In White mode: Warm white intensity ($0 \dots 100$) |
| `12` | `00` $\dots$ `64` | **Saturation / Cool** | - In RGB mode: Saturation percentage ($0 \dots 100\%$)<br>- In White mode: Cool white intensity ($0 \dots 100$) |
| `13` | `00` $\dots$ `64` | **Brightness** | Master brightness level ($0 \dots 100\%$). |
| `14` | `00` $\dots$ `64` | **Warm Channel** | Direct Warm White LED level ($0 \dots 100$). |
| `15` | `00` $\dots$ `64` | **Cool Channel** | Direct Cool White LED level ($0 \dots 100$). |
| `16..25` | `00 ... 00` | **Padding** | 10 reserved trailing bytes (`0x00`). |

---

## 6. Annotated Packet Traces from Live Capture

### Trace 1: Power ON & Initial Status Query
```
[ATT_WRITE_CMD] Handle: 0x0017
Raw: 00 07 80 00 00 02 03 0A 71 23
├─ 00       : Ctrl byte (unsegmented, no ack, v0)
├─ 07       : Seq number (7)
├─ 80 00    : Marker (0x8000)
├─ 00 02    : Inner payload length (2 bytes)
├─ 03       : Length + 1 (3)
├─ 0A       : CmdID (0x0A)
└─ 71 23    : Inner payload (Query Status / Power ON)

[ATT_HANDLE_VALUE_NTF] Handle: 0x0014
Raw: 04 20 80 00 00 4B 4C 0C 7B 22 63 6F 64 65 22 3A 30 2C ... 22 7D
├─ 04       : Ctrl byte (unsegmented, JSON type)
├─ 20       : Notification seq (32)
├─ 80 00    : Marker (0x8000)
├─ 00 4B    : JSON length (75 bytes)
├─ 4C       : Length + 1 (76)
├─ 0C       : CmdID (0x0C)
└─ UTF-8    : {"code":0,"payload":"EA8100000E0A23700240F0B46464000000000000000000000000"}
              ├─ Power State : 0x23 (ON)
              ├─ Mode        : 0x70 (White/Static)
              ├─ Channel     : 0xF0 (RGB active)
              ├─ Saturation  : 0x64 (100%)
              └─ Brightness  : 0x64 (100%)
```

### Trace 2: Setting Red Color (`#FF0000`)
```
[ATT_WRITE_CMD] Handle: 0x0017
Raw: 00 08 80 00 00 0E 0F 0A E0 01 00 A1 00 64 64 00 00 00 00 14 00 00
├─ 00 08 80 00 00 0E 0F 0A : Outer frame header (Seq=8, Len=14, Cmd=0x0A)
└─ E0 01 00 A1 00 64 64 ... : Hue=0° (Red), Sat=100%, Bright=100%

[ATT_HANDLE_VALUE_NTF] Handle: 0x0014
Raw JSON Payload: "EA8100000E0A23610240F0006464000000000000000000000000"
├─ Power      : 0x23 (ON)
├─ Mode       : 0x61 (Color mode)
├─ Hue        : 0x00 (0° -> Red)
├─ Saturation : 0x64 (100%)
└─ Brightness : 0x64 (100%)
```

### Trace 3: Power OFF
```
[ATT_WRITE_CMD] Handle: 0x0017
Raw: 00 46 80 00 00 02 03 0A 71 24
├─ 00 46 80 00 00 02 03 0A : Outer frame header (Seq=70, Len=2, Cmd=0x0A)
└─ 71 24                   : Inner payload (Power OFF)

[ATT_HANDLE_VALUE_NTF] Handle: 0x0014
Raw JSON Payload: "EA8100000E0A246102400F000000646400000000000000000000"
├─ Power : 0x24 (OFF)
└─ Mode  : 0x61 (Preserved last color state)
```

---

## 7. Security & Encryption Considerations

- **Pairing Requirement**: Default Zengge HagallBjarkan devices accept unauthenticated, unbonded connections over standard BLE advertising.
- **Transport Encryption**: Frames have `is_protect = 0` (plaintext payload encapsulation).
- **Session Sequence**: Sequential `Seq` numbers starting at `0x01` are tracked per connection instance.
