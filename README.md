# Ra.One Motion Gaming Controller
### Inspired by PlayStation Move + Ra.One (2011)
**Technologies:** ESP32 · MPU6050 · Flex Sensors · Arduino · Python

---

## Hardware Wiring

```
ESP32 Pin   →  Component
─────────────────────────────────────────────────
GPIO 21     →  MPU6050 SDA
GPIO 22     →  MPU6050 SCL
3.3V        →  MPU6050 VCC
GND         →  MPU6050 GND

GPIO 34     →  Flex Sensor (Punch / Forearm) + 47kΩ pull-down to GND
GPIO 35     →  Flex Sensor (Block / Upper Arm) + 47kΩ pull-down to GND
GPIO 32     →  Flex Sensor (Kick / Leg) + 47kΩ pull-down to GND
3.3V        →  Flex Sensor other end (voltage divider)
GPIO 2      →  Built-in LED (action feedback)
```

**Flex Sensor Voltage Divider:**
```
3.3V ──[Flex Sensor]──┬──[47kΩ]── GND
                      │
                   GPIO_PIN (ADC reads voltage here)
```

---

## Project Structure

```
raone_motion_gaming/
├── firmware/
│   └── main_firmware.ino      ← Upload to ESP32
├── game_plugin/
│   └── game_interface.py      ← Run on PC during gaming
├── calibration/
│   └── calibration_tool.py    ← Run to tune thresholds
└── docs/
    └── README.md              ← This file
```

---

## Setup Steps

### 1. Arduino Libraries (install via Library Manager)
- `MPU6050` by Electronic Cats
- `ArduinoJson` by Benoit Blanchon
- `WiFi` (built-in ESP32 core)

### 2. Firmware Upload
1. Open `firmware/main_firmware.ino` in Arduino IDE
2. Set your WiFi SSID/password and PC IP address in the config section
3. Select Board: **ESP32 Dev Module**
4. Upload at 921600 baud

### 3. PC Setup
```bash
pip install pynput pyserial rich
```

### 4. Calibration
```bash
python3 calibration/calibration_tool.py --port /dev/ttyUSB0
```
- Perform each action (punch, kick, etc.) while watching peak values
- Note the peak accelerometer/gyro readings
- Update thresholds in firmware to ~70% of your observed peaks

### 5. Launch Game Bridge
```bash
python3 game_plugin/game_interface.py
```
- Open Tekken 3 in ePSXe emulator
- The bridge translates ESP32 UDP packets → keyboard inputs

---

## Movement → Action Mapping

| Body Movement            | Detected As | Tekken 3 Key |
|--------------------------|-------------|--------------|
| Sharp forward arm thrust | PUNCH       | A            |
| Flex forearm + push      | PUNCH       | A            |
| Downward leg swing       | KICK        | S            |
| Cross-arm guard          | BLOCK       | Z            |
| Upward jump              | JUMP        | ↑ Arrow      |
| 360° spin + thrust       | SPECIAL     | X + C combo  |

---

## Tuning Tips

- **False positives:** Increase the threshold value (less sensitive)
- **Missed actions:** Decrease the threshold value (more sensitive)
- **Cooldown:** Increase `cooldownMs` to prevent rapid repeated triggers
- **Latency:** Reduce `delay(10)` in firmware loop (caution: heat)
- **Noise:** Enable MPU6050 low-pass filter in firmware for smoother data

---

## Architecture Overview

```
[Body Movement]
      │
[Flex Sensors + MPU6050]
      │ raw ADC + I2C
[ESP32 Firmware]
      │ calibrate + threshold + classify
[Action: PUNCH/KICK/...]
      │ UDP JSON packet (WiFi)
[PC Game Bridge (Python)]
      │ pynput keyboard injection
[Tekken 3 / ePSXe]
      │
[Character Action on Screen]
```
<img width="916" height="1454" alt="image" src="https://github.com/user-attachments/assets/ca4ac24b-182e-45d6-888e-0f65905daf74" />

---

*"Ra.One can't be defeated — but your opponents can."*
