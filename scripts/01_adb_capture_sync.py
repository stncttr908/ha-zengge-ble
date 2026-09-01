#!/usr/bin/env python3
"""
01_adb_capture_sync.py
Interactive CLI to record labeled actions against an Android device and pull
the Bluetooth HCI snoop log directly via ADB.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()

CAPTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "captures"))
os.makedirs(CAPTURES_DIR, exist_ok=True)

SNOOP_SEARCH_PATHS = [
    "/sdcard/Android/data/btsnoop_hci.log",
    "/sdcard/btsnoop_hci.log",
    "/sdcard/Android/data/com.android.bluetooth/files/btsnoop_hci.log",
    "/sdcard/Download/btsnoop_hci.log",
    "/data/misc/bluetooth/logs/btsnoop_hci.log",
    "/data/misc/bluetooth/btsnoop_hci.log",
    "/data/log/bt/btsnoop_hci.log",
]


def run_adb(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    full_cmd = ["adb"] + cmd
    return subprocess.run(full_cmd, capture_output=True, text=True, check=check)


def check_adb_connection():
    try:
        res = run_adb(["devices"])
        lines = [line.strip() for line in res.stdout.strip().split("\n")[1:] if line.strip()]
        if not lines or not any("\tdevice" in line for line in lines):
            console.print("[bold red]No authorized ADB devices found.[/bold red]")
            console.print("Ensure USB debugging is enabled and the computer is authorized on the tablet.")
            sys.exit(1)
        console.print(f"[bold green]Connected device:[/bold green] {lines[0]}")
    except FileNotFoundError:
        console.print("[bold red]'adb' binary not found in PATH.[/bold red]")
        sys.exit(1)


def pull_snoop_log(target_path: str) -> bool:
    console.print("[cyan]Searching known snoop log paths...[/cyan]")
    for path in SNOOP_SEARCH_PATHS:
        check = run_adb(["shell", f"ls {path}"], check=False)
        if check.returncode == 0 and "No such file" not in check.stdout:
            console.print(f"[green]Found log at {path}. Pulling...[/green]")
            pull = run_adb(["pull", path, target_path], check=False)
            if pull.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                return True

    # Scan via shell find command
    console.print("[cyan]Scanning /sdcard for btsnoop files...[/cyan]")
    scan = run_adb(["shell", "find /sdcard -type f -name '*btsnoop*' 2>/dev/null"], check=False)
    found_paths = [p.strip() for p in scan.stdout.strip().split("\n") if p.strip()]
    for p in found_paths:
        console.print(f"[green]Found dynamically located log: {p}. Pulling...[/green]")
        pull = run_adb(["pull", p, target_path], check=False)
        if pull.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
            return True

    # Fallback to bugreport
    console.print("[yellow]Direct extraction failed. Generating ADB bugreport (this may take ~30-60s)...[/yellow]")
    temp_zip = os.path.join(CAPTURES_DIR, "bugreport_temp.zip")
    br = run_adb(["bugreport", temp_zip], check=False)
    if br.returncode == 0 and os.path.exists(temp_zip):
        unzip_dir = os.path.join(CAPTURES_DIR, "bugreport_extracted")
        os.makedirs(unzip_dir, exist_ok=True)
        subprocess.run(["unzip", "-q", "-o", temp_zip, "-d", unzip_dir], check=False)
        
        for root, _, files in os.walk(unzip_dir):
            for f in files:
                if ("btsnoop" in f.lower() or f.endswith(".cfa") or f.endswith(".log")) and not f.startswith("dumpstate"):
                    src = os.path.join(root, f)
                    if os.path.getsize(src) > 0:
                        subprocess.run(["cp", src, target_path], check=True)
                        console.print(f"[green]Successfully extracted snoop log from bugreport: {f}[/green]")
                        return True

    return False


def main():
    console.rule("[bold cyan]BLE HCI Action-Labeled Capture Tool[/bold cyan]")
    check_adb_connection()

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_json = os.path.join(CAPTURES_DIR, f"session_{session_id}.json")
    target_snoop = os.path.join(CAPTURES_DIR, f"btsnoop_{session_id}.log")

    actions_template = [
        ("INITIAL_CONNECT", "Open companion app and connect to the lamp"),
        ("POWER_ON", "Tap Power ON"),
        ("COLOR_RED", "Set pure RED (#FF0000)"),
        ("COLOR_GREEN", "Set pure GREEN (#00FF00)"),
        ("COLOR_BLUE", "Set pure BLUE (#0000FF)"),
        ("BRIGHTNESS_10", "Set brightness to 10%"),
        ("BRIGHTNESS_50", "Set brightness to 50%"),
        ("BRIGHTNESS_100", "Set brightness to 100%"),
        ("WARM_WHITE", "Set warm white / low color temp (if supported)"),
        ("COOL_WHITE", "Set cool white / high color temp (if supported)"),
        ("POWER_OFF", "Tap Power OFF"),
    ]

    recorded_events = []

    console.print("\n[yellow]Instructions:[/yellow]")
    console.print("1. Perform the requested action on the tablet companion app.")
    console.print("2. Immediately press [Enter] right after triggering the action.")
    console.print("3. Type 'skip' to skip an action or 'done' to finish early.\n")

    for label, desc in actions_template:
        res = Prompt.ask(f"[bold yellow]Perform action:[/bold yellow] [bold white]{desc}[/bold white] (label: {label})")
        if res.strip().lower() == "done":
            break
        if res.strip().lower() == "skip":
            continue

        timestamp = time.time()
        recorded_events.append({
            "action": label,
            "description": desc,
            "timestamp": timestamp,
            "iso_time": datetime.fromtimestamp(timestamp).isoformat()
        })
        console.print(f"Recorded [green]{label}[/green] at {datetime.fromtimestamp(timestamp).strftime('%H:%M:%S.%f')[:-3]}")

    while Confirm.ask("Add any custom action?"):
        custom_label = Prompt.ask("Action label (e.g. EFFECT_RAINBOW)").strip().upper()
        custom_desc = Prompt.ask("Description")
        Prompt.ask(f"[bold yellow]Perform action now:[/bold yellow] {custom_desc}, then press Enter")
        timestamp = time.time()
        recorded_events.append({
            "action": custom_label,
            "description": custom_desc,
            "timestamp": timestamp,
            "iso_time": datetime.fromtimestamp(timestamp).isoformat()
        })

    with open(session_json, "w") as f:
        json.dump({"session_id": session_id, "events": recorded_events}, f, indent=2)

    console.print(f"\n[green]Saved labeled timestamps to:[/green] {session_json}")

    console.print("\n[cyan]Toggling Bluetooth to flush log buffers...[/cyan]")
    run_adb(["shell", "cmd", "bluetooth_manager", "disable"], check=False)
    time.sleep(1)
    run_adb(["shell", "cmd", "bluetooth_manager", "enable"], check=False)
    time.sleep(2)

    if pull_snoop_log(target_snoop):
        console.print(f"[bold green]Log file successfully saved to:[/bold green] {target_snoop}")
        console.print(f"\nRun the parser:\n  python scripts/02_parse_btsnoop.py --snoop {target_snoop} --session {session_json}")
    else:
        console.print("[bold red]Failed to retrieve btsnoop_hci.log automatically.[/bold red]")
        console.print("Please test running: adb bugreport captures/bugreport.zip manually to check permissions.")


if __name__ == "__main__":
    main()
