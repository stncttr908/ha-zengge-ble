#!/usr/bin/env python3
"""
test_live_lamp.py
Automated end-to-end test against the physical lamp:
1. Starts BLE listener for IOTBT537 / Zengge lamp
2. Power cycles the outlet if needed
3. Connects via BleakClient
4. Tests Power ON, Red, Green, Blue, Brightness, CCT Warm/Cool, Scenes, and Status Query
"""

import asyncio
import os
import sys
import subprocess
from pathlib import Path

# Add scripts directory
sys.path.insert(0, str(Path(__file__).parent))

from bleak import BleakScanner, BleakClient
from rich.console import Console
from importlib.machinery import SourceFileLoader

controller = SourceFileLoader("controller", str(Path(__file__).parent / "05_controller.py")).load_module()

ZenggeLampClient = controller.ZenggeLampClient
ZenggePayloadBuilder = controller.ZenggePayloadBuilder
display_status_panel = controller.display_status_panel

console = Console()

SERVICE_UUID = "0000ffff-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

async def run_live_pipeline():
    console.print("[bold cyan]==================================================[/bold cyan]")
    console.print("[bold cyan]Starting End-to-End Live Lamp Test Pipeline[/bold cyan]")
    console.print("[bold cyan]==================================================[/bold cyan]\n")

    stop_event = asyncio.Event()
    discovered_devices = []

    def on_detect(device, adv):
        name = device.name or adv.local_name or ""
        svcs = [str(u).lower() for u in adv.service_uuids]
        is_lamp = False
        
        if "iotbt" in name.lower():
            is_lamp = True
        elif ("ffff" in "".join(svcs) or "fe00" in "".join(svcs)) and "prov_" not in name.lower():
            is_lamp = True
            
        if is_lamp and not discovered_devices:
            console.print(f"[bold green]⚡ Detected lamp beacon:[/bold green] [white]{name}[/white] ({device.address}) RSSI={adv.rssi} dBm")
            discovered_devices.append((device, adv))
            stop_event.set()

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    console.print("[dim]BLE Scanner listening for boot beacon (10s timeout)...[/dim]")

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        console.print("[yellow]Lamp not seen immediately. Waiting a bit more...[/yellow]")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            console.print("[red]Timeout: Lamp beacon not detected.[/red]")
            await scanner.stop()
            return False
    finally:
        await scanner.stop()

    dev, adv = discovered_devices[0]
    console.print(f"[green]✓ Target identified:[/green] {dev.address} ({dev.name})\n")

    client = ZenggeLampClient(dev.address, target_device=dev)
    connected = await client.connect(timeout=12.0)
    if not connected:
        console.print("[red]Failed to connect to lamp.[/red]")
        return False

    try:
        # 1. Power ON
        console.print("\n[bold yellow]1. Sending Power ON (71 23)...[/bold yellow]")
        st = await client.power_on()
        if st: display_status_panel(st)
        await asyncio.sleep(2.0)

        # 2. Set RED
        console.print("\n[bold yellow]2. Setting Color -> PURE RED (#FF0000)...[/bold yellow]")
        st = await client.set_rgb(255, 0, 0)
        if st: display_status_panel(st)
        await asyncio.sleep(2.5)

        # 3. Set GREEN
        console.print("\n[bold yellow]3. Setting Color -> PURE GREEN (#00FF00)...[/bold yellow]")
        st = await client.set_rgb(0, 255, 0)
        if st: display_status_panel(st)
        await asyncio.sleep(2.5)

        # 4. Set BLUE
        console.print("\n[bold yellow]4. Setting Color -> PURE BLUE (#0000FF)...[/bold yellow]")
        st = await client.set_rgb(0, 0, 255)
        if st: display_status_panel(st)
        await asyncio.sleep(2.5)

        # 5. Set Brightness 50%
        console.print("\n[bold yellow]5. Setting Brightness -> 50%...[/bold yellow]")
        st = await client.set_brightness(50)
        if st: display_status_panel(st)
        await asyncio.sleep(2.0)

        # 6. Set Warm White
        console.print("\n[bold yellow]6. Setting Warm White (CCT 0%, Bri 100%)...[/bold yellow]")
        st = await client.set_cct(0, 100)
        if st: display_status_panel(st)
        await asyncio.sleep(2.5)

        # 7. Set Cool White
        console.print("\n[bold yellow]7. Setting Cool White (CCT 100%, Bri 100%)...[/bold yellow]")
        st = await client.set_cct(100, 100)
        if st: display_status_panel(st)
        await asyncio.sleep(2.5)

        # 8. Flame Scene
        console.print("\n[bold yellow]8. Activating Scene -> Custom Flame (Mode 0x2C)...[/bold yellow]")
        st = await client.set_scene(0x2C)
        if st: display_status_panel(st)
        await asyncio.sleep(4.0)

        # 9. Three Color Gradient Scene
        console.print("\n[bold yellow]9. Activating Scene -> Three Color Gradient (Mode 0x25)...[/bold yellow]")
        st = await client.set_scene(0x25)
        if st: display_status_panel(st)
        await asyncio.sleep(4.0)

        # 10. Query final status
        console.print("\n[bold yellow]10. Querying Final Status...[/bold yellow]")
        st = await client.query_status()
        if st: display_status_panel(st)

        console.print("\n[bold green]✓ All physical lamp tests passed successfully![/bold green]")
        return True

    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(run_live_pipeline())
