#pragma once
// =====================================================================
//  SafeWork firmware - shared configuration
//  Board: 4d_systems_esp32s3_gen4_r8n16  (ESP32-S3, 3.3V logic)
//  Role selected at compile time by PlatformIO build flag:
//      -D ROLE_TAG      -> Worker node (initiator + sensors + WiFi)
//      -D ROLE_ANCHOR   -> Anchor node (responder only)
//  and -D ANCHOR_ID=<n> for each anchor build (this build: 1 or 2)
// =====================================================================

// ---------------------------------------------------------------------
//  DW3000 (UWB) wiring -- MUST match how you soldered the adapter.
//
//  *** CRITICAL: use the ESP32-S3 FSPI **IOMUX** pins, not arbitrary GPIOs. ***
//  Routing SPI through the GPIO matrix corrupts multi-byte SPI on the S3:
//  2-byte-header (extended) reads come back bit-shifted and ALL register
//  writes fail -- while a plain 1-byte DEV_ID read can still look fine, so
//  the fault hides until dwt_configure() dies with a PLL LOCK error.
//  Verified on hardware: with the IOMUX pins below, extended reads AND
//  writes are clean; with SCK=11/MOSI=9/MISO=12 they are not.
//
//  FSPI IOMUX: SCK=12 (FSPICLK), MOSI=11 (FSPID), MISO=13 (FSPIQ), CS=10 (FSPICS0).
//  RST/IRQ are ordinary GPIOs. Avoid GPIO0/3/45/46 (strap), 19/20 (USB),
//  26-37 (flash/PSRAM), 43/44 (UART0), and 8/9 (I2C sensors, below).
//  Keep the DW3000_PIN_* build flags in platformio.ini in sync with these.
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
//  Anchor layout. The tag reports raw distances (d1..dN, in metres) and
//  the backend solves for (x, y) - the anchors' own coordinates live in
//  backend/core/position_engine.py, not here.
//
//  With 2 anchors the two range circles meet at TWO points, mirrored
//  about the line joining the anchors. Place both anchors along one edge
//  of the working area so the mirror solution falls outside the map and
//  the backend can discard it (or let the BNO08x pick the branch).
//  Keep the baseline as long as you can, and avoid working right on the
//  line through both anchors - accuracy collapses there.
// ---------------------------------------------------------------------
#define NUM_ANCHORS  2
// Anchor IDs the tag ranges against are 1..NUM_ANCHORS; build each anchor
// with -DANCHOR_ID=<n>. d1 = anchor 1, d2 = anchor 2 in the telemetry JSON.

// ---------------------------------------------------------------------
//  Worker / node identity
// ---------------------------------------------------------------------
#define WORKER_ID    "WK_102"   // must match a Personnel row in the backend

// ---------------------------------------------------------------------
//  I2C sensors on the TAG (BNO08x + MAX30102 + MAX30205 share one bus)
// ---------------------------------------------------------------------
#define I2C_SDA        8
#define I2C_SCL        9
#define BNO08X_ADDR    0x4A     // 0x4A (SA0=GND) or 0x4B (SA0=3V3)
// MAX30102 is fixed 0x57 inside the HeartRate driver.
// MAX30205 (body temperature) is strap-selected somewhere in 0x48..0x4F, so
// BodyTemp probes that range at boot and skips 0x4A/0x4B (the BNO08x).

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
