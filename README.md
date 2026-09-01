# Zengge / MagicHome BLE Smart Lamp Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)](https://home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A high-performance, fully reverse-engineered Home Assistant custom integration for **Zengge / MagicHome Bluetooth Low Energy (BLE)** smart lamps, ambient bulbs, and LED controllers utilizing the **HagallBjarkan** (`com.zengge.hagallbjarkan`) transport protocol.

---

## ✨ Features

- **🚀 Local Push Architecture**: Real-time bidirectional telemetry over GATT characteristic `0xFF02`. Changes made via physical controls or other clients update Home Assistant instantly.
- **🔍 Auto Discovery**: Native integration with Home Assistant's Bluetooth stack. Discovers lamps advertising `0xFFFF` service or `IOTBT*` names automatically.
- **📡 ESPHome Bluetooth Proxy Support**: Seamless roaming and multi-room coverage using ESPHome Active Bluetooth Proxies.
- **🎨 Complete Color & White Control**:
  - Full RGB / HSV Color Wheel (`ColorMode.HS`)
  - Tunable White / CCT (`ColorMode.COLOR_TEMP`) from **2700K** (Warm White) to **6500K** (Cool White)
  - Smooth brightness scaling ($0\% \dots 100\%$)
- **🔥 26 Built-In Native Hardware Scenes**: Direct access to all reverse-engineered firmware effect presets (Flame, Breathe, Heartbeat, Colorful, Rainbow, Mediterranean, and more) executed directly on the lamp's microcontroller.
- **🔒 100% Local & Cloud-Free**: Zero internet connection, zero vendor cloud dependencies, and zero accounts required.

---

## 🛠️ Supported Devices

Tested and confirmed compatible with:
- **Zengge / MagicHome BLE Ambient Smart Lamps** (e.g. `IOTBT537...`)
- **Zengge HagallBjarkan RGB+CCT Table Lamps**
- **MagicHome BLE LED Strips & Bulbs** using service `0000ffff-0000-1000-8000-00805f9b34fb`

---

## 📦 Installation

### Option 1: Installation via HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. In Home Assistant, navigate to **HACS** > **Integrations**.
3. Click the three dots in the top right corner and select **Custom repositories**.
4. Add this repository:
   - **Repository URL**: `https://github.com/stncttr908/ha-zengge-ble`
   - **Type**: `Integration`
5. Click **Add**, then search for **"Zengge BLE Smart Light"**.
6. Click **Download**, then restart Home Assistant.

### Option 2: Manual Installation

1. Download the latest release `.zip` from GitHub.
2. Copy the `custom_components/zengge_ble/` folder into your Home Assistant `<config>/custom_components/` directory:
   ```bash
   config/custom_components/zengge_ble/
   ├── __init__.py
   ├── config_flow.py
   ├── const.py
   ├── coordinator.py
   ├── light.py
   ├── manifest.json
   ├── strings.json
   ├── zengge_protocol.py
   └── translations/
       └── en.json
   ```
3. Restart Home Assistant.

---

## ⚙️ Configuration & Pairing

### Automatic Discovery
1. Turn on power to your Zengge lamp.
2. In Home Assistant, open **Settings** > **Devices & Services**.
3. The discovered lamp will appear automatically with a **"Discovered"** card (e.g. `IOTBT537...`).
4. Click **Configure** and confirm to add the light.

### Manual Configuration
1. Go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **"Zengge BLE Smart Light"**.
3. Select your discovered lamp from the list, or choose **"Manually enter Bluetooth MAC address"** and provide the device's MAC address (e.g. `AA:BB:CC:DD:EE:FF`).

---

## 📡 ESPHome Bluetooth Proxy Compatibility

To control your lamps throughout your home without being limited by the server's onboard Bluetooth range, you can use ESP32-based ESPHome Bluetooth Proxies.

Ensure your ESPHome configuration has `active: true` enabled:

```yaml
esp32_ble_tracker:
  scan_parameters:
    active: true

bluetooth_proxy:
  active: true
```

The integration will automatically connect through the closest proxy with the strongest RSSI signal.

---

## 🌈 Native Hardware Scene Catalog

The integration exposes 26 hardware-driven scenes that run autonomously on the device:

| Scene Name | Mode ID | Category | Description |
| :--- | :--- | :--- | :--- |
| **Flame** | `0x2C` | Dynamic | Realistic flickering candle / fireplace flame |
| **Breathe** | `0x01` | Preset | Smooth pulsing breathe cycle |
| **Three Color Gradient** | `0x25` | Dynamic | Tri-color smooth color wash |
| **Five Color Jump** | `0x26` | Dynamic | Stepped multi-color jump |
| **Colorful Breath** | `0x27` | Dynamic | Multi-color breathing cycle |
| **Heartbeat** | `0x28` | Dynamic | Pulsing rhythmic heartbeat |
| **Lightning** | `0x29` | Dynamic | Thunderstorm strobe flash |
| **Step Change** | `0x02` | Preset | Crisp color stepping |
| **Rhythm Change** | `0x03` | Preset | Musical cadence rhythm shift |
| **Leisure** | `0x04` | Preset | Warm relaxing atmosphere |
| **Night Light** | `0x05` | Preset | Dim amber night light |
| **Good Night** | `0x06` | Preset | Sleep aid sunset fading warm light |
| **Read** | `0x07` | Preset | High-CRI reading neutral white |
| **Work** | `0x08` | Preset | Crisp cool daylight for productivity |
| **Grassland** | `0x09` | Preset | Forest & fresh green tones |
| **Colorful** | `0x0A` | Preset | Vivid spectrum dynamic cycle |
| **Dazzling** | `0x0B` | Preset | High-energy dynamic party colors |
| **Gorgeous** | `0x0C` | Preset | Deep romantic purple & rose blend |
| **Blue Sky** | `0x0D` | Preset | Crisp azure sky blue |
| **Sunflower** | `0x0E` | Preset | Vibrant sunflower yellow |
| **Forest** | `0x0F` | Preset | Deep evergreen forest tones |
| **Mediterranean** | `0x10` | Preset | Aquamarine ocean gradients |
| **French Style** | `0x11` | Preset | Soft pastel romantic colors |
| **American Style** | `0x12` | Preset | Rich saturated primary tones |
| **Birthday Party** | `0x13` | Preset | Festivity party loop |
| **Wedding Day** | `0x14` | Preset | Soft warm romantic glow |

---

## 🔬 Protocol Architecture Summary

- **GATT Service**: `0000ffff-0000-1000-8000-00805f9b34fb` (`0xFFFF`)
- **Write Characteristic**: `0000ff01-0000-1000-8000-00805f9b34fb` (`0xFF01`)
- **Notify Characteristic**: `0000ff02-0000-1000-8000-00805f9b34fb` (`0xFF02`)
- **Framing**: Lower Transport Layer header `[Ctrl, Seq, 0x80, 0x00, Len_H, Len_L, Len+1, CmdID, ...Payload]`
- **Telemetry Payload**: Hex-encoded 26-byte status array encapsulated in UTF-8 JSON notification messages.

For comprehensive technical documentation, refer to [`docs/protocol_spec.md`](docs/protocol_spec.md).

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
