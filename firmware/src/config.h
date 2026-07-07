#pragma once
// =====================================================================
//  SafeWork firmware - shared configuration
//  Board: 4d_systems_esp32s3_gen4_r8n16  (ESP32-S3, 3.3V logic)
//  Role selected at compile time by PlatformIO build flag:
//      -D ROLE_TAG      -> Worker node (initiator + sensors + WiFi)
//      -D ROLE_ANCHOR   -> Anchor node (responder only)
//  and -D ANCHOR_ID=<n> for each anchor build (1,2,3...)
// =====================================================================

// ---------------------------------------------------------------------
//  DW3000 (UWB) wiring  -- MUST match how you soldered the YCHIOT adapter.
//  NOTE: the Makerfabs "Dw3000" library keeps its own pin defines
//  (DW3000_PIN_RST / _IRQ / _CS) in its port header. If those don't match
//  the values below, edit the library header OR keep these in sync.
//  ESP32-S3 routes SPI over the GPIO matrix, so any free pin works.
//  Avoid: GPIO0/3/45/46 (strap), 19/20 (USB), 26-37 (flash/PSRAM), 43/44.
// ---------------------------------------------------------------------
#define DW_PIN_SCK   12
#define DW_PIN_MOSI  11
#define DW_PIN_MISO  13
#define DW_PIN_CS    10
#define DW_PIN_IRQ   18
#define DW_PIN_RST   17

// UWB channel/params must be IDENTICAL on tag and all anchors.
#define UWB_CHANNEL  5      // 5 (6.5 GHz) or 9 (8 GHz)

// Antenna delay - CALIBRATE per design! Measure a known distance and
// tune this until the reported range matches. Same value tag & anchors.
#define UWB_ANT_DLY  16385

// ---------------------------------------------------------------------
//  Anchor layout  (known fixed coordinates, in metres, sent to backend
//  for reference; the tag reports raw distances, backend trilaterates)
// ---------------------------------------------------------------------
#define NUM_ANCHORS  3
// Anchor IDs the tag will range against (1..NUM_ANCHORS)

// ---------------------------------------------------------------------
//  Worker / node identity
// ---------------------------------------------------------------------
#define WORKER_ID    "WK_102"   // must match a Personnel row in the backend

// ---------------------------------------------------------------------
//  I2C sensors on the TAG (BNO08x + MAX30102 share one bus)
// ---------------------------------------------------------------------
#define I2C_SDA        8
#define I2C_SCL        9
#define BNO08X_ADDR    0x4A     // 0x4A (SA0=GND) or 0x4B (SA0=3V3)
// MAX30102 is fixed 0x57 inside the HeartRate driver.

// ---------------------------------------------------------------------
//  WiFi + backend (TAG only) -- FILL THESE IN
// ---------------------------------------------------------------------
#define WIFI_SSID      "YOUR_WIFI"
#define WIFI_PASS      "YOUR_PASSWORD"
// Backend device_telemetry endpoint. Use the LAN IP of the server,
// e.g. http://192.168.1.100:5000/api/device_telemetry
#define BACKEND_URL    "http://192.168.1.100:5000/api/device_telemetry"

// Telemetry send period (ms)
#define TELEMETRY_PERIOD_MS  800
