# SafeWork Firmware (ESP32-S3 + DWM3000 + BNO08x + MAX30102)

One codebase, two roles selected by PlatformIO environment:

| Node | What it does | Hardware |
|---|---|---|
| **Tag** (`env:tag`) | UWB initiator: ranges every anchor, reads vitals (MAX30102) + motion/heading (BNO08x), POSTs telemetry to the backend over WiFi | ESP32-S3 + DWM3000 + BNO08x + MAX30102 |
| **Anchor** (`env:anchor1/2/3`) | UWB responder for its own ID | ESP32-S3 + DWM3000 |

Build: 3 anchors + 1 tag = your 4× ESP32-S3 / 4× DWM3000.

## File layout
```
firmware/
  platformio.ini      envs: tag, anchor1, anchor2, anchor3
  src/config.h        <-- EDIT: pins, WiFi, backend URL, worker id
  src/uwb.h/.cpp      DW3000 SS-TWR (initiator + responder), multi-anchor by ID
  src/HeartRate.*     MAX30102 heart-rate DSP (reused)
  src/main.cpp        role logic (tag vs anchor)
  lib/Dw3000/         vendored Makerfabs DW3000 driver (pins via -D, ready to build)
```

## Setup (once)
1. **DW3000 driver:** already vendored in `firmware/lib/Dw3000/` — no manual copy needed.
   Its pins are set to match `src/config.h` via `-DDW3000_PIN_*` in `platformio.ini`.
2. **Fill `src/config.h`:** `WIFI_SSID`, `WIFI_PASS`, `BACKEND_URL` (the server LAN IP, e.g.
   `http://192.168.1.100:5000/api/device_telemetry`), and `WORKER_ID` (must exist in the Personnel table).

## Build & flash
```bash
cd firmware
pio run -e anchor1 -t upload     # flash anchor #1, place it, power from 3.3V
pio run -e anchor2 -t upload     # anchor #2
pio run -e anchor3 -t upload     # anchor #3
pio run -e tag     -t upload     # worker helmet
pio device monitor               # watch JSON logs
```

## ⚠️ Before powering the DWM3000 (learned the hard way)
- **3.3 V only.** Power VDD from the ESP32-S3 **3V3** pin, never 5V/VIN/USB — 5V is above the 4.0V absolute max and kills the module instantly.
- ESP32-S3 is 3.3V logic → wire SPI **directly, no level shifter**.
- Measure the rail with a meter (~3.3V) **before** inserting the module; check VCC/GND polarity (adapter has no protection).
- RSTn open-drain only (never drive it hard HIGH).

## ⚠️ Ranging accuracy: antenna-delay calibration
`UWB_ANT_DLY` in `config.h` (16385) is a default. Place two nodes a **known** distance apart
(e.g. 1.0 m) and adjust `UWB_ANT_DLY` on tag + anchors until the reported range matches. Do this once.

## Telemetry format (matches backend `/api/device_telemetry`)
```json
{
  "worker_id": "WK_102",
  "telemetry": { "hr": 82, "temp": 30.1, "spo2": 0, "ch4": 0, "co": 0,
                 "yaw": 143.2, "steps": 51, "acc": 1.03 },
  "distances": { "ANC_STAGE": 12.4, "ANC_LEFT": 30.1, "ANC_RIGHT": 35.7 }
}
```

## Status / TODO
- UWB SS-TWR core is faithful to the official Makerfabs example; **needs on-hardware testing**.
- `temp` is the MAX30102 **chip** temperature, not body temperature — add a MAX30205 for real thermal data.
- No gas sensor on this build → `ch4`/`co` are 0 (simulated on the dashboard).
- SS-TWR ranges anchors sequentially; for many tags add time-slotting / DS-TWR later.
