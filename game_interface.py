"""
Ra.One Motion Gaming — PC Game Interface Bridge
================================================
Receives UDP JSON packets from the ESP32 controller and maps
detected actions to Tekken 3 keyboard inputs using pynput.

Tekken 3 (via ePSXe emulator) default keybinds:
  Arrow keys = movement/direction
  A = Punch (Left punch)
  S = Kick  (Left kick)
  Z = Block
  X = Right Punch
  C = Right Kick

Install dependencies:
  pip install pynput

Usage:
  python3 game_interface.py
"""

import socket
import json
import threading
import time
from pynput.keyboard import Key, Controller, KeyCode
from collections import deque

# ─── CONFIG ──────────────────────────────────────────────────────────────────
UDP_HOST = "0.0.0.0"
UDP_PORT = 4210
BUFFER_SIZE = 256

# ─── ACTION → KEY MAPPING (Tekken 3 via ePSXe) ───────────────────────────────
# Modify these to match your emulator keybindings
ACTION_MAP = {
    "PUNCH":   KeyCode.from_char('a'),    # Left Punch
    "KICK":    KeyCode.from_char('s'),    # Left Kick
    "BLOCK":   KeyCode.from_char('z'),    # Block
    "JUMP":    Key.up,                    # Up arrow (jump)
    "SPECIAL": [                          # Combo: Right Punch + Right Kick
        KeyCode.from_char('x'),
        KeyCode.from_char('c'),
    ],
}

# Hold duration (seconds) for each key press
KEY_HOLD = {
    "PUNCH":   0.08,
    "KICK":    0.10,
    "BLOCK":   0.15,
    "JUMP":    0.12,
    "SPECIAL": 0.20,
}

# ─── STATE ───────────────────────────────────────────────────────────────────
keyboard = Controller()
action_history = deque(maxlen=20)  # For debug display
stats = {"PUNCH": 0, "KICK": 0, "BLOCK": 0, "JUMP": 0, "SPECIAL": 0, "NONE": 0}


# ─── KEY PRESS HANDLER ───────────────────────────────────────────────────────
def press_action(action_name: str, sensor_data: dict):
    """Press the key(s) mapped to the given action name."""
    keys = ACTION_MAP.get(action_name)
    if keys is None:
        return

    hold_time = KEY_HOLD.get(action_name, 0.08)
    stats[action_name] = stats.get(action_name, 0) + 1

    def _press():
        if isinstance(keys, list):
            # Combo: press all simultaneously
            for k in keys:
                keyboard.press(k)
            time.sleep(hold_time)
            for k in keys:
                keyboard.release(k)
        else:
            keyboard.press(keys)
            time.sleep(hold_time)
            keyboard.release(keys)

    t = threading.Thread(target=_press, daemon=True)
    t.start()

    ts = sensor_data.get("ts", 0)
    log = f"[{ts:>8}ms] {action_name:<8} | aX:{sensor_data.get('axG', 0):+.2f} aY:{sensor_data.get('ayG', 0):+.2f} aZ:{sensor_data.get('azG', 0):+.2f}"
    action_history.append(log)
    print(log)


# ─── UDP LISTENER ────────────────────────────────────────────────────────────
def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_HOST, UDP_PORT))
    print(f"[UDP] Listening on {UDP_HOST}:{UDP_PORT}")

    while True:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            payload = json.loads(data.decode("utf-8"))
            action = payload.get("action", "NONE")

            if action != "NONE":
                press_action(action, payload)

        except json.JSONDecodeError:
            print(f"[WARN] Malformed packet: {data}")
        except Exception as e:
            print(f"[ERROR] {e}")


# ─── STATS PRINTER ───────────────────────────────────────────────────────────
def print_stats():
    """Periodically print action statistics."""
    while True:
        time.sleep(10)
        print("\n─── ACTION STATS ───────────────────────────────")
        for action, count in stats.items():
            bar = "█" * min(count, 40)
            print(f"  {action:<8} {bar} {count}")
        print("────────────────────────────────────────────────\n")


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
def main():
    print("=" * 52)
    print("  Ra.One Motion Gaming — Game Interface Bridge")
    print("  Tekken 3 Controller Active")
    print("=" * 52)
    print("\nAction → Key Mapping:")
    for action, key in ACTION_MAP.items():
        print(f"  {action:<10} → {key}")
    print("\nWaiting for ESP32 controller...\n")

    # Start UDP listener thread
    listener = threading.Thread(target=udp_listener, daemon=True)
    listener.start()

    # Start stats printer thread
    stats_printer = threading.Thread(target=print_stats, daemon=True)
    stats_printer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[EXIT] Game bridge stopped.")


if __name__ == "__main__":
    main()
