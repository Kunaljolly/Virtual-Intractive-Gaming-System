"""
Ra.One Motion Gaming — Calibration & Threshold Tuner
=====================================================
Connect to the ESP32 over Serial, display live sensor values,
and help tune the action-detection thresholds interactively.

Usage:
  python3 calibration_tool.py --port COM3        (Windows)
  python3 calibration_tool.py --port /dev/ttyUSB0 (Linux/Mac)

Install:
  pip install pyserial rich
"""

import argparse
import json
import threading
import time
import serial
from dataclasses import dataclass, asdict
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.columns import Columns

console = Console()

# ─── THRESHOLD CONFIG (mirrors firmware Thresholds struct) ───────────────────
@dataclass
class Thresholds:
    punchAccelX:    float = 2.5
    kickAccelZ:     float = 2.0
    jumpAccelY:     float = 2.8
    blockGyroZ:     float = 150.0
    specialGyroAll: float = 200.0
    flexPunchMin:   int   = 2800
    flexBlockMin:   int   = 2600
    flexKickMin:    int   = 2700
    cooldownMs:     int   = 400

thresh = Thresholds()

# ─── LIVE DATA ───────────────────────────────────────────────────────────────
live_data = {
    "action": "---", "axG": 0.0, "ayG": 0.0, "azG": 0.0,
    "gxDps": 0.0, "gyDps": 0.0, "gzDps": 0.0, "ts": 0,
    "maxAxG": 0.0, "maxAyG": 0.0, "maxAzG": 0.0,
    "maxGx": 0.0, "maxGy": 0.0, "maxGz": 0.0,
}

action_counts = {"PUNCH": 0, "KICK": 0, "BLOCK": 0, "JUMP": 0, "SPECIAL": 0}
lock = threading.Lock()


# ─── SERIAL READER ───────────────────────────────────────────────────────────
def serial_reader(port: str, baud: int = 115200):
    try:
        ser = serial.Serial(port, baud, timeout=1)
        console.print(f"[green]Connected to {port}[/green]")
    except serial.SerialException as e:
        console.print(f"[red]Cannot open {port}: {e}[/red]")
        return

    while True:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line.startswith("{"):
                data = json.loads(line)
                with lock:
                    live_data.update(data)
                    # Track maximums for threshold suggestion
                    live_data["maxAxG"] = max(live_data["maxAxG"], abs(data.get("axG", 0)))
                    live_data["maxAyG"] = max(live_data["maxAyG"], abs(data.get("ayG", 0)))
                    live_data["maxAzG"] = max(live_data["maxAzG"], abs(data.get("azG", 0)))
                    live_data["maxGx"]  = max(live_data["maxGx"],  abs(data.get("gxDps", 0)))
                    live_data["maxGy"]  = max(live_data["maxGy"],  abs(data.get("gyDps", 0)))
                    live_data["maxGz"]  = max(live_data["maxGz"],  abs(data.get("gzDps", 0)))

                    action = data.get("action", "NONE")
                    if action in action_counts:
                        action_counts[action] += 1

        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        except Exception as e:
            console.print(f"[red]Serial error: {e}[/red]")
            break


# ─── RICH DASHBOARD ──────────────────────────────────────────────────────────
def build_dashboard():
    with lock:
        d = live_data.copy()
        t = asdict(thresh)
        ac = action_counts.copy()

    # Sensor table
    sensor_table = Table(title="Live Sensor Data", border_style="blue")
    sensor_table.add_column("Axis", style="bold")
    sensor_table.add_column("Value", justify="right")
    sensor_table.add_column("Peak", justify="right", style="yellow")

    sensor_table.add_row("accel X (g)",  f"{d['axG']:+.3f}", f"{d['maxAxG']:.3f}")
    sensor_table.add_row("accel Y (g)",  f"{d['ayG']:+.3f}", f"{d['maxAyG']:.3f}")
    sensor_table.add_row("accel Z (g)",  f"{d['azG']:+.3f}", f"{d['maxAzG']:.3f}")
    sensor_table.add_row("gyro X (°/s)", f"{d['gxDps']:+.1f}", f"{d['maxGx']:.1f}")
    sensor_table.add_row("gyro Y (°/s)", f"{d['gyDps']:+.1f}", f"{d['maxGy']:.1f}")
    sensor_table.add_row("gyro Z (°/s)", f"{d['gzDps']:+.1f}", f"{d['maxGz']:.1f}")

    action_color = {
        "PUNCH": "red", "KICK": "magenta", "BLOCK": "cyan",
        "JUMP": "green", "SPECIAL": "yellow", "---": "white"
    }
    last_color = action_color.get(d["action"], "white")

    # Action panel
    action_panel = Panel(
        f"[bold {last_color}]{d['action']}[/bold {last_color}]\n\n" +
        "\n".join(f"{a}: {c}" for a, c in ac.items()),
        title="Actions Detected",
        border_style=last_color,
    )

    # Threshold table
    thresh_table = Table(title="Current Thresholds", border_style="green")
    thresh_table.add_column("Parameter")
    thresh_table.add_column("Value", justify="right")
    thresh_table.add_column("Unit")
    for k, v in t.items():
        thresh_table.add_row(k, str(v), "g / °/s / ADC / ms")

    return Columns([sensor_table, action_panel, thresh_table])


# ─── THRESHOLD TUNER ─────────────────────────────────────────────────────────
def tune_thresholds():
    console.print("\n[bold yellow]─── Threshold Tuner ───[/bold yellow]")
    console.print("Perform the action, then enter the observed peak value.")
    console.print("(Press Enter to keep current value)\n")

    fields = asdict(thresh)
    for field, current in fields.items():
        try:
            val = input(f"  {field} [{current}]: ").strip()
            if val:
                if isinstance(current, int):
                    setattr(thresh, field, int(val))
                else:
                    setattr(thresh, field, float(val))
        except (ValueError, EOFError):
            pass

    console.print("\n[green]Thresholds updated![/green]")
    console.print("Copy these to your firmware Thresholds struct:\n")
    for field, val in asdict(thresh).items():
        console.print(f"  .{field} = {val},")


# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Ra.One Calibration Tool")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    t = threading.Thread(target=serial_reader, args=(args.port, args.baud), daemon=True)
    t.start()

    console.print("[bold green]Ra.One Calibration Tool[/bold green]")
    console.print("Commands: [d] dashboard  [t] tune thresholds  [r] reset peaks  [q] quit\n")

    with Live(build_dashboard(), refresh_per_second=10, console=console) as live:
        while True:
            live.update(build_dashboard())
            time.sleep(0.1)


if __name__ == "__main__":
    main()
