#!/usr/bin/env python3
"""
capture_real_scenes.py
Automates clicking every scene and custom preset on Tab 3,
records precise timestamps, pulls the bugreport over Wi-Fi, and maps GATT frames.
"""

import json
import os
import subprocess
import time
from datetime import datetime
from rich.console import Console

console = Console()
DEVICE_ID = "10.10.1.240:38051"
CAPTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "captures"))

def adb(cmd: str):
    return subprocess.run(f"adb -s {DEVICE_ID} {cmd}", shell=True, capture_output=True, text=True)

def tap(x: int, y: int):
    adb(f"shell input tap {x} {y}")

TAB3_SCENES = [
    # Customs
    ("Custom Three Color Gradient", 120, 326),
    ("Custom Five Color Jump", 360, 326),
    ("Custom Colorful Breath", 600, 326),
    ("Custom Heartbeat", 840, 326),
    ("Custom Lightning", 1080, 326),
    ("Custom Flame", 120, 566),
    # Presets Row 1
    ("Preset Breathe", 133, 927),
    ("Preset Step Change", 366, 927),
    ("Preset Rhythm Change", 600, 927),
    ("Preset Leisure", 833, 927),
    ("Preset Night Light", 1067, 927),
    # Presets Row 2
    ("Preset Good Night", 133, 1160),
    ("Preset Read", 366, 1160),
    ("Preset Work", 600, 1160),
    ("Preset Grassland", 833, 1160),
    ("Preset Colorful", 1067, 1160),
    # Presets Row 3
    ("Preset Dazzling", 133, 1393),
    ("Preset Gorgeous", 366, 1393),
    ("Preset Blue Sky", 600, 1393),
    ("Preset Sunflower", 833, 1393),
    ("Preset Forest", 1067, 1393),
    # Presets Row 4
    ("Preset Mediterranean", 133, 1627),
    ("Preset French Style", 366, 1627),
    ("Preset American Style", 600, 1627),
    ("Preset Birthday", 833, 1627),
    ("Preset Wedding Day", 1067, 1627),
]

def main():
    console.print("[bold cyan]==================================================[/bold cyan]")
    console.print("[bold cyan]Capturing Tab 3 Scenes & Dynamic Presets[/bold cyan]")
    console.print("[bold cyan]==================================================[/bold cyan]\n")

    events = []
    for name, x, y in TAB3_SCENES:
        console.print(f"▶ Tapping [bold green]{name}[/bold green] ({x}, {y})...")
        t_start = time.time()
        tap(x, y)
        time.sleep(2.5)
        events.append({
            "action": name,
            "timestamp": t_start,
            "iso_time": datetime.fromtimestamp(t_start).isoformat(),
        })

    events_path = os.path.join(CAPTURES_DIR, "tab3_scene_events.json")
    with open(events_path, "w") as f:
        json.dump(events, f, indent=2)
    console.print(f"\n[green]✓ Recorded {len(events)} scene events to {events_path}[/green]")

    # Pull bugreport
    console.print("[yellow]Pulling Android bugreport over Wi-Fi...[/yellow]")
    br_zip = os.path.join(CAPTURES_DIR, "tab3_bugreport.zip")
    adb(f"bugreport {br_zip}")

    if os.path.exists(br_zip):
        unzip_dir = os.path.join(CAPTURES_DIR, "tab3_bugreport_extracted")
        os.makedirs(unzip_dir, exist_ok=True)
        subprocess.run(["unzip", "-q", "-o", br_zip, "-d", unzip_dir], check=False)
        console.print("[green]✓ Extracted bugreport[/green]")

if __name__ == "__main__":
    main()
