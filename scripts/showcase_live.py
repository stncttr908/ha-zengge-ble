#!/usr/bin/env python3
"""
showcase_live.py
Visual live demonstration script:
- Pure Red -> Green -> Blue -> Yellow -> Purple -> Cyan
- Fast 360° Rainbow flow (multiple complete color wheel cycles)
- Candle / Flame organic flicker
- CCT Warm White -> Cool White transition
"""

import asyncio
import math
import random
import sys
from pathlib import Path
from importlib.machinery import SourceFileLoader
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent))

from bleak import BleakScanner

controller = SourceFileLoader("controller", str(Path(__file__).parent / "05_controller.py")).load_module()

console = Console()

async def run_showcase():
    console.print("[bold cyan]==================================================[/bold cyan]")
    console.print("[bold cyan]Starting Visual Lamp Showcase Pipeline (30s)[/bold cyan]")
    console.print("[bold cyan]==================================================[/bold cyan]\n")

    console.print("[dim]Scanning for IOTBT537 lamp...[/dim]")
    dev = await BleakScanner.find_device_by_name("IOTBT537", timeout=6.0)
    if not dev:
        devs = await BleakScanner.discover(timeout=5.0)
        for d in devs:
            if d.name and "iotbt" in d.name.lower():
                dev = d
                break
    if not dev:
        console.print("[red]Lamp not detected. Please make sure HA integration is disabled.[/red]")
        return

    console.print(f"[green]✓ Found lamp:[/green] {dev.address} ({dev.name})")
    client = controller.ZenggeLampClient(dev.address, target_device=dev)
    await client.connect(timeout=10.0)

    try:
        # Phase 1: Pure Colors Sequence
        console.print("\n[bold yellow]▶ Phase 1: Vivid Primary & Secondary Colors[/bold yellow]")
        colors = [
            ("PURE RED", 255, 0, 0),
            ("PURE GREEN", 0, 255, 0),
            ("PURE BLUE", 0, 0, 255),
            ("GOLDEN YELLOW", 255, 200, 0),
            ("DEEP MAGENTA", 255, 0, 255),
            ("CYAN / TURQUOISE", 0, 255, 255),
        ]
        for name, r, g, b in colors:
            console.print(f"  ➜ [bold]{name}[/bold] (RGB: {r},{g},{b})")
            await client.set_rgb(r, g, b)
            await asyncio.sleep(1.6)

        # Phase 2: Fast 360° Rainbow Rotation
        console.print("\n[bold yellow]▶ Phase 2: Fast 360° Dynamic Rainbow Flow (10s)[/bold yellow]")
        t_start = asyncio.get_event_loop().time()
        hue = 0.0
        while (asyncio.get_event_loop().time() - t_start) < 10.0:
            hue = (hue + 12.0) % 360.0
            await client.set_hsv(int(hue), 100, 100)
            await asyncio.sleep(0.04)
        console.print("  ✓ Completed multiple full rainbow spectrum rotations!")

        # Phase 3: Organic Flame / Candle Flicker
        console.print("\n[bold yellow]▶ Phase 3: Organic Candle / Flame Flicker (5s)[/bold yellow]")
        t_start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - t_start) < 5.0:
            flicker_hue = random.randint(24, 40)
            flicker_bri = random.randint(40, 100)
            flicker_sat = random.randint(85, 100)
            await client.set_hsv(flicker_hue, flicker_sat, flicker_bri)
            await asyncio.sleep(random.uniform(0.04, 0.12))
        console.print("  ✓ Flame effect rendered!")

        # Phase 4: Color Temperature (CCT)
        console.print("\n[bold yellow]▶ Phase 4: Color Temperature Tuning[/bold yellow]")
        console.print("  ➜ Warm White (2700K / 0% CCT)...")
        await client.set_cct(0, 100)
        await asyncio.sleep(2.5)

        console.print("  ➜ Cool Daylight White (6500K / 100% CCT)...")
        await client.set_cct(100, 100)
        await asyncio.sleep(2.5)

        console.print("  ➜ Balanced Neutral White (4600K / 50% CCT)...")
        await client.set_cct(50, 100)
        await asyncio.sleep(2.5)

        console.print("\n[bold green]✓ Complete visual showcase finished successfully![/bold green]")

    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(run_showcase())
