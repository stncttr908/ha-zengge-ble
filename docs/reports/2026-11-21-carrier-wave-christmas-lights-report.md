# Zengge BLE Carrier-Wave Addressable String Lights (`IOTBTD84`, Product ID `0x00C5`) Protocol & Integration Report

**Date**: 2026-11-21  
**Device**: `IOTBTD84` (`DeviceDD84`, MAC `08:65:F0:41:DD:84`)  
**Firmware**: `BT.5B.00C5.43.28,V8` (`chipId=0x5B` PHY6252, `productId=0x00C5` / `197`, `firmwareVer=67`, `ledVersion=8`, `25` addressable LEDs)  
**Integration**: `custom_components/zengge_ble` (`v0.2.0`)

---

## 1. Root Cause & Discovery Summary

1. **Product Family Difference**:
   - The existing `IOTBT537` RGB Floor Lamp uses `productId = 0x000E` (`14`), which speaks `common2_0` HSV (`E0 01 00 A1 ...`), CCT (`E0 01 00 B1 ...`), and ROM scenes (`E0 02 00 ...`), and signals RGB mode via byte `10 = 0xF0` in `EA81...` telemetry.
   - The new `IOTBTD84` Christmas String Lights use `productId = 0x00C5` (`197`, `wifibleCarrierWaveSymphony` / `hc3`), which is RGB-only (`25` addressable LEDs, no dedicated CCT channel) and uses `symphonyE1` (`0xE1`), `symphonyE4` / `0xEC`, and `E0 01 00 C1` commands.
   - In `EA810000C508...` telemetry, byte `10` is `0x00`, causing the original `v0.1.0` parser (`channel_flag == 0xF0`) to misclassify `IOTBTD84` as a `WHITE` / `COLOR_TEMP` light at `2700K` and ignore `0xA1`/`0xB1`/`E0 02` writes.
2. **Startup Query Bug Fixed**:
   - `custom_components/zengge_ble/coordinator.py` previously lacked `import asyncio`, causing `await asyncio.sleep(0.2)` inside `_async_update_data()` to fail silently on startup/reload with `NameError: name 'asyncio' is not defined`.
   - `ZenggeLampDevice.send_command()` also lacked an async command lock (`self._cmd_lock`), allowing concurrent calls to clobber `self._status_future`.

---

## 2. Reverse-Engineered Carrier-Wave (`0x00C5`) Protocol

Captured via Wi-Fi ADB (`10.10.1.240:37273`) from `com.zennge.magichome2` (`captures/christmas_btsnoop_hci.log`, `117` timestamped UI actions in `captures/christmas_events.json`, `286` correlated ATT packets in `captures/christmas_correlated.json`):

| Feature | Outer CmdID | Inner Payload Format | Telemetry / Notes |
| :--- | :---: | :--- | :--- |
| **Status Query** | `0x0A` | `EA 81 8A 8B 59` | Non-destructive status query (with checksum `0x59`); replies `EA810000C508...` |
| **Power ON** | `0x0A` | `E0 01 00 23 00 00 00 00 00 00 00 00 00 00` | Emits `0xFF02` telemetry (`b[6] = 0x23`) |
| **Power OFF** | `0x0A` | `E0 01 00 24 00 00 00 00 00 00 00 00 00 00` | Turns off silently without emitting `0xFF02` notification |
| **Solid Color (`0xC1`)** | `0x0A` | `E0 01 00 C1 [H>>1] [((H&1)<<7)\|S] [V] 00 00 00 00 14 00 00` | 9-bit Hue packing (`0..359`), `S=0..100`, `V=1..100`; `b[7]=0x24`, `b[8]=0x14` |
| **String Presets (`EC 07`)** | `0x0A` | `EC 07 00 [bri] [n] [N x 5B 9-bit HSV00]` | 5 multi-color string presets; `b[7]=0x24`, `b[8]=0x01` |
| **Built-in Effects (`E1 21`)** | `0x0A` | `E1 21 00 [bri] [mode] [dir] [step] [param] [speed] 00 [bg 5B] [n] [colors...]` | 68 built-in effects across Festival, View, Atmosphere, Commerce, Romantic, Life; `b[7]=0x25`, `b[8]=mode`, `b[9]=speed` |
| **Music Modes (`EC 03`)** | `0x0A` | `EC 03 00 [bri] [mode 1..6] 00 [sens] [n] [colors...]` | 6 device-mic music modes; `b[7]=0x62`, `b[8]=mode` |
| **Custom Smudge (`E1 23`)** | `0x0A` | `E1 23 01 [anim] 00 00 [bri] 00 [count=25] [25 x 7B]` | 184-byte multi-segment TX (`ctrl=0x40`); `b[7]=0x66`, `b[8]=anim` |

---

## 3. Home Assistant 2026.11.x Marketplace & Zero-Restart Readiness

- **`manifest.json` (`v0.2.0`)**: Added `issue_tracker`, bumped `version` to `"0.2.0"`, and added `service_data_uuid` matchers (`00005a00-0000-1000-8000-00805f9b34fb` and `00005a02-0000-1000-8000-00805f9b34fb`) alongside `0000ffff-...` and `IOTBT*`.
- **In-Place Submodule Hot-Reloader (`__init__.py`)**: Moved submodule reloading into `async_setup_entry` via `hass.async_add_executor_job(_reload_submodules_if_changed)` so `const`, `zengge_protocol`, `coordinator`, `light`, and `config_flow` reload in topological order whenever files on disk have newer mtimes—enabling zero-restart code updates on HA `Reload` once `v0.2.0` is loaded, while new installations via HA `2026.11` Marketplace load immediately without a restart.

---

## 4. Verification

- Standalone unit test suite (`tests/`): **57/57 tests passing** (`.venv/bin/python3 -m unittest discover -s tests -v`), covering `IOTBT537` backward compatibility, `0x5A00`/`0x5A02` service data product ID decoding, 9-bit HSV packing, `E1 21`/`EC 07`/`EC 03` effect serialization, `EA810000C508...` telemetry parsing, `ZenggeLampDevice` async dispatch, and `ZenggeHBLightEntity` dynamic capabilities.
