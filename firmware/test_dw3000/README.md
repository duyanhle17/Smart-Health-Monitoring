# DWM3000 test (ESP32-S3)

Quick way to verify a DWM3000 works — especially useful after soldering, and
after you've already lost modules to wiring/5V mistakes.

## Wiring (3.3 V ONLY)
| DWM3000 | ESP32-S3 |
|---|---|
| VDD3V3 | **3V3** (never 5V/VIN/USB) |
| GND | GND |
| SPICLK | GPIO12 |
| SPIMOSI | GPIO11 |
| SPIMISO | GPIO13 |
| SPICSn | GPIO10 |
| IRQ | GPIO18 |
| RSTn | GPIO17 |

## Before building
The **`Dw3000`** library is shared from `../lib` (via `lib_extra_dirs` in
`platformio.ini`) and its pins are set via `-DDW3000_PIN_*` — nothing to copy.

## Test 1 — is this ONE module alive? (only 1 DWM3000 needed)
```bash
pio run -e check -t upload
pio device monitor          # 115200 baud
```
Expected output:
```
IDLE_RC=ok  DEV_ID=0xDECA0302  -> DW3000 ALIVE :)  (module + SPI + power OK)
```
Reading the result:
| Output | Meaning |
|---|---|
| `DEV_ID=0xDECA0302 ... ALIVE` | ✅ module works, SPI + power correct |
| `0x00000000` or `0xFFFFFFFF ... DEAD or SPI miswired` | ❌ check CS/MISO/MOSI/SCK, GND, and that VDD is **3.3V** |
| `IDLE_RC=FAIL` | power/reset problem — verify 3.3V and RST wiring |
| `0xDECA0130` | that's a **DW1000**, not a DW3000 |

## Test 2 — ranging (needs 2 modules, do later)
Flash `responder` on one board and `initiator` on the other:
```bash
pio run -e responder -t upload   # board A (anchor)
pio run -e initiator -t upload   # board B (tag)  -> prints "dist = X.XX m"
```
Then calibrate `TX_ANT_DLY/RX_ANT_DLY` against a known distance.
