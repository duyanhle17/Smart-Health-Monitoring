# SafeWork Firmware (ESP32-S3 + DWM3000 + BNO08x + MAX30102 + MAX30205)

One codebase, two roles selected by PlatformIO environment:

| Node | What it does | Hardware |
|---|---|---|
| **Tag** (`env:tag`) | UWB initiator: ranges every anchor, reads vitals (MAX30102 + MAX30205) and motion/heading (BNO08x), POSTs telemetry to the backend over WiFi | ESP32-S3 + DWM3000 + BNO08x + MAX30102 + MAX30205 |
| **Anchor** (`env:anchor1/2`) | UWB responder for its own ID | ESP32-S3 + DWM3000 |

Current build: **2 anchors + 1 tag**.

## File layout
```
firmware/
  platformio.ini      envs: tag, anchor1, anchor2 (+ *u variants for CH343 boards)
  src/config.h        <-- EDIT: pins, WiFi, backend URL, worker id
  src/uwb.h/.cpp      DW3000 SS-TWR (initiator + responder), multi-anchor by ID
  src/HeartRate.*     MAX30102 heart-rate DSP
  src/BodyTemp.*      MAX30205 body temperature (address auto-probed 0x48..0x4F)
  src/main.cpp        role logic (tag vs anchor)
  lib/Dw3000/         vendored Makerfabs DW3000 driver, SPI forced to 2 MHz
```

## Which env do I flash?
Two board variants are in use and they need different serial flags:

| Board | USB id | Env |
|---|---|---|
| native USB (USB-Serial/JTAG) | `303A:1001` | `tag`, `anchor1`, `anchor2` |
| CH343 USB-UART bridge | `1A86:*` | `tagu`, `anchor1u`, `anchor2u` |

Flash a CH343 board with the native-USB env and the monitor stays silent — that is
the only difference (`ARDUINO_USB_CDC_ON_BOOT`).

## Setup (once)
1. **DW3000 driver:** vendored in `firmware/lib/Dw3000/` — nothing to copy. Pins are set
   from `-DDW3000_PIN_*` in `platformio.ini` and must match `src/config.h`.
2. **Configure WiFi over serial — no reflash needed.** The tag keeps SSID / password /
   backend URL / worker id in NVS; the values in `config.h` are only the fallback when
   NVS is empty. Open the monitor and type:
   ```
   help                                              list the commands
   show                                              print the current config
   wifi MyNetwork mypassword                         set SSID + password, reconnects at once
   url http://192.168.1.100:5000/api/device_telemetry
   id WK_102                                         must exist in the Personnel table
   clear                                             wipe NVS, fall back to config.h
   ```
   Settings survive power cycles and reflashes, so a helmet can be provisioned at the
   desk and then run on battery.

## Build & flash
```bash
cd firmware
pio run -e anchor1 -t upload     # anchor #1, place it, power from 3.3V
pio run -e anchor2 -t upload     # anchor #2
pio run -e tag     -t upload     # worker helmet
pio device monitor               # watch JSON logs
```
Anchors print a heartbeat every 2 s with how many polls they have answered — use it
to confirm an anchor is alive and hearing the tag.

Before touching the main firmware, `test_dw3000/` has standalone bring-up sketches:
`hwcheck` (I2C scan + DEV_ID), `maxtest` (MAX30102 + MAX30205), `uwbimu`
(DWM3000 + BNO08x together), `initiator`/`responder` (raw ranging pair).

## ⚠️ Wiring — FSPI IOMUX pins, not arbitrary GPIOs
| DWM3000 | ESP32-S3 | | I2C sensors | ESP32-S3 |
|---|---|---|---|---|
| SPICLK | GPIO12 | | SDA | GPIO8 |
| SPIMOSI | GPIO11 | | SCL | GPIO9 |
| SPIMISO | GPIO13 | | | |
| SPICSn | GPIO10 | | | |
| IRQ | GPIO18 | | | |
| RSTn | GPIO17 | | | |

Routing DW3000 SPI through the GPIO matrix corrupts multi-byte transfers on the S3:
extended reads come back bit-shifted and register writes fail, while a plain 1-byte
DEV_ID read still looks fine — so the fault hides until `dwt_configure()` dies with a
PLL LOCK error. See `problem.md` for the full debug log.

## ⚠️ Before powering the DWM3000
- **3.3 V only.** Power VDD from the ESP32-S3 **3V3** pin, never 5V/VIN/USB — 5V is
  above the 4.0V absolute max and kills the module instantly.
- ESP32-S3 is 3.3V logic → wire SPI **directly, no level shifter**.
- Measure the rail (~3.3V) **before** inserting the module; check VCC/GND polarity.
- RSTn open-drain only (never drive it hard HIGH).

## ⚠️ Ranging accuracy: antenna-delay calibration
`UWB_ANT_DLY` in `config.h` (16385) is a default. Place two nodes a **known** distance
apart (e.g. 1.0 m) and adjust `UWB_ANT_DLY` on tag + anchors until the reported range
matches. Do this once.

## Telemetry format
The backend reads the ranges as flat `d1`..`dN` keys **inside** `telemetry`
(`backend/app.py`), where `d1` = anchor 1 and `d2` = anchor 2. A range that failed this
cycle is omitted so the backend keeps the last known fix.
```json
{
  "worker_id": "WK_102",
  "telemetry": { "hr": 82, "temp": 36.6, "spo2": 0, "ch4": 0, "co": 0,
                 "yaw": 143.2, "steps": 51, "acc": 1.03,
                 "ax": 0.01, "ay": 0.02, "az": 1.00,
                 "d1": 12.40, "d2": 30.10 }
}
```

## Status / TODO
- **Verified on hardware (3 boards, 2026-07-24):** DW3000 `DEV_ID=0xDECA0302`, PLL locks,
  both anchors answer only their own ID, tag reports `d1`/`d2` every 800 ms with ~±7 cm
  of jitter. MAX30205 found at 0x4C, BNO08x reports rotation vector + accelerometer.
- **`UWB_ANT_DLY` is NOT calibrated yet** — ranges read roughly 1.2 m long. Calibrate
  before trusting any position (see the section above).
- `XTRIM OTP READ FAIL` at boot is benign: the module has no crystal-trim value burned
  into OTP, so the driver keeps the default. PLL still locks.
- `temp` is real body temperature from the MAX30205; it falls back to the MAX30102
  chip temperature if the sensor is not found at boot.
- No gas sensor on this build → `ch4`/`co` are 0 (simulated on the dashboard).
- Backend now solves the real 2-anchor geometry (`backend/core/position_engine.py`).
  **Set `ANCHOR_BASELINE_M` there to the measured distance between your two anchors** —
  it is the only thing converting UWB metres into the map's 0-100 units.
- MAX30102 is occasionally missing at boot (`MAX30102 not found`, I2C error -1) while
  the other two I2C devices enumerate fine — suspect a marginal joint on its SDA/SCL/VIN.
  When that happens `hr` stays 0.
- SS-TWR ranges anchors sequentially; for many tags add time-slotting / DS-TWR later.
