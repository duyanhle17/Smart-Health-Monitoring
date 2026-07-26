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

// Skin->body temperature offset. The MAX30205 measures SKIN temperature, which
// sits several degrees below core body temperature. This fixed offset lifts the
// reported value toward a body-temperature figure. WARNING: a constant offset
// is only an approximation - it is calibrated for typical indoor contact, and
// will over-read (false fever) with firmer/warmer contact or under-read in the
// cold. Tune to your placement; a real skin->core estimate needs an ambient
// reference. Set 0.0 to report raw skin temperature.
#define TEMP_SKIN_TO_BODY_OFFSET_C   6.5f

// ---------------------------------------------------------------------
//  WiFi + backend (TAG only)
// ---------------------------------------------------------------------
// Wi-Fi credentials are normally entered through the SafeWork setup portal
// (or the serial `wifi` command) and kept in NVS. These are only fallbacks
// for a newly flashed board.
#define WIFI_SSID      "YOUR_WIFI"
#define WIFI_PASS      "YOUR_PASSWORD"
// Public production ingress. For a local/LAN deployment use
// http://<server-lan-ip>:6868/api/device_telemetry -- not port 5000.
#define BACKEND_URL    "https://safework.ctslab.net/api/device_telemetry"

// If the tag has no usable Wi-Fi connection, it opens an AP named
// SafeWork-Setup-<last-6-MAC-hex>. Connect with this password and browse to
// http://192.168.4.1 to enter Wi-Fi, backend URL and worker ID.
#define WIFI_PORTAL_AP_PREFIX    "SafeWork-Setup-"
#define WIFI_PORTAL_AP_PASSWORD  "safework"

// UWB is sampled independently from the HTTPS sender.  The cloud connection
// may take hundreds of milliseconds, but that must not pause radio/BNO08x
// sampling or turn a smooth walk into one update per TLS handshake.
#define UWB_SAMPLE_PERIOD_MS       200   // 5 paired d1+d2 samples / second
// Match the sampler: at 400 ms every second measured pair was overwritten in
// the one-slot queue before it reached the solver, halving the backend
// filter's input rate for no gain. If one HTTPS POST is slower than this
// period the queue still coalesces safely - read the telemetry_net serial log
// for the measured POST latency before blaming the radio for a slow marker.
#define TELEMETRY_PERIOD_MS        200   // target server update cadence
#define UWB_INTER_ANCHOR_GUARD_MS    8   // responder re-arm time after a poll

// NLOS heuristic from the DW3000 CIA diagnostics: receive level minus
// first-path level, formed so the absolute-power constant and the accumulator
// count cancel. Under ~6 dB is clean line-of-sight; above ~10-12 dB the first
// path is buried (worker's body, racking) and the range reads long. Flag,
// never drop: a body-shadowed anchor returns five equally-biased samples, so
// the median cannot help, but the backend can widen that range's variance
// instead of losing the whole fix.
#define UWB_NLOS_DELTA_DB        12.0f
