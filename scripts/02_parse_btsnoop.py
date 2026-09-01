#!/usr/bin/env python3
"""
02_parse_btsnoop.py
Parses Android BTSnoop HCI logs, extracts BLE ATT Write/Notify frames,
and correlates them with timestamps from 01_adb_capture_sync.py.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from rich.console import Console
from rich.table import Table

console = Console()

OPCODE_NAMES = {
    "0x52": "ATT_WRITE_CMD",
    "0x12": "ATT_WRITE_REQ",
    "0x13": "ATT_WRITE_RSP",
    "0x1b": "ATT_HANDLE_VALUE_NTF",
    "0x1d": "ATT_HANDLE_VALUE_IND",
}


def parse_with_pyshark(pcap_path: str, target_handle: str | None = None) -> list[dict]:
    import pyshark

    records = []
    console.print(f"[cyan]Parsing {pcap_path} with PyShark (tshark)...[/cyan]")

    cap = pyshark.FileCapture(
        pcap_path,
        display_filter="btatt",
        keep_packets=False,
    )

    for pkt in cap:
        try:
            if not hasattr(pkt, "btatt"):
                continue

            att = pkt.btatt
            epoch = float(pkt.sniff_timestamp)
            opcode_raw = getattr(att, "opcode", None) or getattr(att, "opcode_tree", None)
            opcode = str(opcode_raw) if opcode_raw else ""
            
            handle = getattr(att, "handle", "N/A")
            value = getattr(att, "value", None) or getattr(att, "value_raw", "")
            
            # Format value string
            clean_value = "".join(str(value).split(":")).replace("0x", "").upper()
            
            if target_handle and handle != target_handle:
                continue

            records.append({
                "epoch": epoch,
                "iso_time": datetime.fromtimestamp(epoch).isoformat(),
                "opcode": opcode,
                "opcode_name": OPCODE_NAMES.get(opcode.lower(), opcode),
                "handle": handle,
                "value": clean_value,
                "length": len(clean_value) // 2 if clean_value else 0,
            })
        except Exception:
            continue

    cap.close()
    return records


def parse_with_scapy(pcap_path: str) -> list[dict]:
    from scapy.all import rdpcap, Raw

    console.print(f"[yellow]PyShark failed or unavailable. Falling back to Scapy...[/yellow]")
    packets = rdpcap(pcap_path)
    records = []

    for pkt in packets:
        if pkt.haslayer(Raw):
            load = bytes(pkt[Raw].load)
            # Basic heuristic for ATT over L2CAP (CID 0x0004)
            if len(load) >= 3 and load[0] in [0x12, 0x52, 0x1B, 0x1D]:
                opcode = f"0x{load[0]:02x}"
                handle = f"0x{load[2]:02x}{load[1]:02x}"
                val = load[3:].hex().upper()
                epoch = float(pkt.time)
                records.append({
                    "epoch": epoch,
                    "iso_time": datetime.fromtimestamp(epoch).isoformat(),
                    "opcode": opcode,
                    "opcode_name": OPCODE_NAMES.get(opcode.lower(), opcode),
                    "handle": handle,
                    "value": val,
                    "length": len(val) // 2,
                })
    return records


def correlate_actions(records: list[dict], events: list[dict]) -> list[dict]:
    """Correlates records with closest manual action event based on epoch timestamp."""
    for rec in records:
        rec_time = rec["epoch"]
        closest_event = None
        min_diff = float("inf")

        for event in events:
            evt_time = event.get("timestamp", event.get("start_time", 0.0))
            diff = abs(rec_time - evt_time)
            if diff < min_diff and diff < 4.0:  # Match within 4 seconds
                min_diff = diff
                closest_event = event

        if closest_event:
            rec["action"] = closest_event.get("action", closest_event.get("name", "Unknown"))
            rec["note"] = f"Aligned with '{rec['action']}' (dt={min_diff:.2f}s)"
        else:
            rec["action"] = "N/A"
            rec["note"] = ""

    return records


def main():
    parser = argparse.ArgumentParser(description="Parse Bluetooth HCI snoop logs for ATT packets.")
    parser.add_argument("--snoop", required=True, help="Path to btsnoop_hci.log or .pcap file")
    parser.add_argument("--session", required=False, help="Path to session JSON from 01_adb_capture_sync.py")
    parser.add_argument("--handle", required=False, help="Filter for specific ATT handle (e.g. 0x002e)")
    parser.add_argument("--out", required=False, help="Output CSV/JSON base path")
    args = parser.parse_args()

    if not os.path.exists(args.snoop):
        console.print(f"[bold red]File not found:[/bold red] {args.snoop}")
        sys.exit(1)

    try:
        records = parse_with_pyshark(args.snoop, args.handle)
    except Exception as e:
        console.print(f"[red]PyShark parsing error: {e}[/red]")
        records = parse_with_scapy(args.snoop)

    if not records:
        console.print("[bold red]No ATT packets found in capture.[/bold red]")
        sys.exit(0)

    if args.session and os.path.exists(args.session):
        with open(args.session, "r") as f:
            session_data = json.load(f)
            events = session_data if isinstance(session_data, list) else session_data.get("events", [])
            records = correlate_actions(records, events)

    # Render summary table
    table = Table(title="Extracted BLE ATT Writes & Notifications")
    table.add_column("Timestamp", style="cyan", no_wrap=True)
    table.add_column("Opcode", style="magenta")
    table.add_column("Handle", style="green")
    table.add_column("Action", style="yellow")
    table.add_column("Payload (Hex)", style="bold white")

    for r in records[:50]:  # Display top 50 in CLI
        table.add_row(
            r["iso_time"].split("T")[1][:12],
            r["opcode_name"],
            r["handle"],
            r.get("action", ""),
            r["value"]
        )

    console.print(table)
    if len(records) > 50:
        console.print(f"[dim]... and {len(records) - 50} more records[/dim]")

    # Export outputs
    base_out = args.out or os.path.splitext(args.snoop)[0] + "_parsed"
    csv_file = f"{base_out}.csv"
    json_file = f"{base_out}.json"

    with open(json_file, "w") as f:
        json.dump(records, f, indent=2)

    if records:
        keys = list(records[0].keys())
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(records)

    console.print(f"\n[green]Saved structured payloads to:[/green]\n  - {json_file}\n  - {csv_file}")


if __name__ == "__main__":
    main()