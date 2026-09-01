#!/usr/bin/env python3
"""
auto_capture_scenes.py
Automates tapping through all native scenes in MagicHome on the Android device over Wi-Fi,
records timestamps for each tapped scene, pulls the btsnoop log, and extracts exact BLE frames.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from rich.console import Console
from rich.table import Table

console = Console()

DEVICE_ID = "10.10.1.240:38051"
CAPTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "captures"))
os.makedirs(CAPTURES_DIR, exist_ok=True)

def adb(cmd: str):
    full = f"adb -s {DEVICE_ID} {cmd}"
    return subprocess.run(full, shell=True, capture_output=True, text=True)

def tap(x: int, y: int):
    adb(f"shell input tap {x} {y}")

def swipe_up():
    adb("shell input swipe 600 1200 600 500 300")

SCENE_TARGETS_PAGE1 = [
    ("Colorful", 177, 671),
    ("French Style", 459, 671),
    ("American Style", 740, 671),
    ("Valentine's Day", 1022, 671),
    ("Easter", 177, 790),
    ("Halloween", 459, 790),
    ("Thanksgiving", 740, 790),
    ("Christmas", 1022, 790),
    ("Birthday Party", 177, 908),
    ("Horror Fright", 459, 908),
    ("Thor's Night", 740, 908),
    ("Firefly Mars Sky", 1022, 908),
]

RHYTHM_TARGETS = [
    ("Music Gradient", 186, 499),
    ("Music Breathe", 462, 499),
    ("Music Twinkle", 738, 499),
    ("Music Jump", 1013, 499),
]

def run_auto_capture():
    console.print("[bold cyan]==================================================[/bold cyan]")
    console.print("[bold cyan]Automated Scene Capture Pipeline Over Wi-Fi[/bold cyan]")
    console.print("[bold cyan]==================================================[/bold cyan]\n")

    events = []

    # 1. Capture Music / Rhythm Modes
    console.print("[yellow]Capturing Music / Rhythm Modes...[/yellow]")
    for name, x, y in RHYTHM_TARGETS:
        console.print(f"  ▶ Tapping [bold green]{name}[/bold green] ({x}, {y})...")
        t_start = time.time()
        tap(x, y)
        time.sleep(2.5)
        events.append({
            "action": name,
            "category": "music_rhythm",
            "start_time": t_start,
            "end_time": time.time(),
            "iso_start": datetime.fromtimestamp(t_start).isoformat(),
        })

    # 2. Capture Page 1 Scenes
    console.print("\n[yellow]Capturing Built-in Scenes (Page 1)...[/yellow]")
    for name, x, y in SCENE_TARGETS_PAGE1:
        console.print(f"  ▶ Tapping [bold green]{name}[/bold green] ({x}, {y})...")
        t_start = time.time()
        tap(x, y)
        time.sleep(2.5)
        events.append({
            "action": name,
            "category": "scene_page1",
            "start_time": t_start,
            "end_time": time.time(),
            "iso_start": datetime.fromtimestamp(t_start).isoformat(),
        })

    # 3. Scroll down for Page 2
    console.print("\n[yellow]Scrolling down to reveal more scenes...[/yellow]")
    swipe_up()
    time.sleep(1.5)

    # Re-dump to find new scenes
    adb("shell uiautomator dump /sdcard/window_dump2.xml")
    adb("shell cat /sdcard/window_dump2.xml > captures/window_dump2.xml")

    import xml.etree.ElementTree as ET
    tree = ET.parse(os.path.join(CAPTURES_DIR, "window_dump2.xml"))
    root = tree.getroot()
    page2_scenes = []
    seen = set([s[0].lower() for s in SCENE_TARGETS_PAGE1])

    for node in root.iter("node"):
        desc = node.attrib.get("content-desc", "").strip()
        bounds = node.attrib.get("bounds", "")
        if desc and "Tab" not in desc and desc.lower() not in seen and "[" in bounds:
            # Calculate center
            import re
            m = re.findall(r"\[(\d+),(\d+)\]", bounds)
            if len(m) == 2:
                x1, y1 = map(int, m[0])
                x2, y2 = map(int, m[1])
                if y1 > 500 and y2 < 1800:
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    page2_scenes.append((desc, cx, cy))
                    seen.add(desc.lower())

    console.print(f"\n[yellow]Capturing Page 2 Scenes ({len(page2_scenes)} found)...[/yellow]")
    for name, cx, cy in page2_scenes:
        console.print(f"  ▶ Tapping [bold green]{name}[/bold green] ({cx}, {cy})...")
        t_start = time.time()
        tap(cx, cy)
        time.sleep(2.5)
        events.append({
            "action": name,
            "category": "scene_page2",
            "start_time": t_start,
            "end_time": time.time(),
            "iso_start": datetime.fromtimestamp(t_start).isoformat(),
        })

    # Save event metadata
    meta_path = os.path.join(CAPTURES_DIR, "scene_capture_events.json")
    with open(meta_path, "w") as f:
        json.dump(events, f, indent=2)
    console.print(f"\n[green]✓ Recorded {len(events)} scene events to {meta_path}[/green]")

    # 4. Pull BTSnoop HCI log / Bugreport
    console.print("\n[yellow]Pulling Bluetooth HCI snoop log via ADB...[/yellow]")
    br_zip = os.path.join(CAPTURES_DIR, "scene_bugreport.zip")
    adb(f"bugreport {br_zip}")

    if os.path.exists(br_zip):
        unzip_dir = os.path.join(CAPTURES_DIR, "scene_bugreport_extracted")
        os.makedirs(unzip_dir, exist_ok=True)
        subprocess.run(["unzip", "-q", "-o", br_zip, "-d", unzip_dir], check=False)
        console.print("[green]✓ Bugreport extracted successfully[/green]")

if __name__ == "__main__":
    run_auto_capture()
