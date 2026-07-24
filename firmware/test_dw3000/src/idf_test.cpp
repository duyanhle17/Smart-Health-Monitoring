// =====================================================================
//  DW3000 old-wiring — DECISIVE sweep: mode x input_delay, two-phase read,
//  and a BIT-LEVEL scan for DEV_ID (0xDECA0302) at ANY bit offset.
//
//  Build:  pio run -e idf -t upload   (board usbmodem1101, OLD wiring)
//  Pins:  SCK=11 MOSI=9 MISO=12 CS=10 RST=17.  3.3V only.
//
//  If DEV_ID appears byte-aligned (bitoff 0) for some combo -> FIXED.
//  If it appears at a fixed nonzero bitoff -> software-recoverable.
//  If never (-1) -> the multi-byte transfer loses sync (SI limit); the
//  clean fix is the IOMUX board.
// =====================================================================
#include <Arduino.h>
#include "driver/spi_master.h"

#define PIN_SCK   11
#define PIN_MOSI   9
#define PIN_MISO  12
#define PIN_CS    10
#define PIN_RST   17
#define DW_SPI_HOST  SPI2_HOST

static spi_device_handle_t dw_spi = nullptr;

void busInit() {
    spi_bus_config_t b = {};
    b.mosi_io_num = PIN_MOSI; b.miso_io_num = PIN_MISO; b.sclk_io_num = PIN_SCK;
    b.quadwp_io_num = -1; b.quadhd_io_num = -1; b.max_transfer_sz = 0;
    b.flags = SPICOMMON_BUSFLAG_MASTER;
    ESP_ERROR_CHECK(spi_bus_initialize(DW_SPI_HOST, &b, SPI_DMA_DISABLED));
}

void addDevice(uint32_t hz, int mode, int input_delay_ns) {
    spi_device_interface_config_t d = {};
    d.command_bits = 0; d.address_bits = 0; d.dummy_bits = 0;
    d.mode = mode; d.clock_speed_hz = hz; d.input_delay_ns = input_delay_ns;
    d.spics_io_num = PIN_CS; d.queue_size = 1; d.flags = 0;   // full-duplex, two-phase framing
    ESP_ERROR_CHECK(spi_bus_add_device(DW_SPI_HOST, &d, &dw_spi));
}

void readRegN(uint8_t hdr0, uint8_t hdr1, bool ext, uint8_t *out, int n) {
    uint8_t hdr[2] = {hdr0, hdr1}; int hlen = ext ? 2 : 1;
    spi_device_acquire_bus(dw_spi, portMAX_DELAY);
    spi_transaction_t th = {};
    th.flags = SPI_TRANS_CS_KEEP_ACTIVE; th.length = hlen * 8; th.tx_buffer = hdr;
    spi_device_polling_transmit(dw_spi, &th);
    spi_transaction_t tb = {};
    tb.length = n * 8; tb.rxlength = n * 8; tb.tx_buffer = NULL; tb.rx_buffer = out;
    spi_device_polling_transmit(dw_spi, &tb);
    spi_device_release_bus(dw_spi);
}

// scan every BIT offset for DEV_ID wire pattern (02 03 CA DE, MSB-first)
int findDevIdBit(uint8_t *rx, int n) {
    const uint8_t target[4] = {0x02, 0x03, 0xCA, 0xDE};
    int totalbits = n * 8;
    for (int off = 0; off + 32 <= totalbits; off++) {
        bool ok = true;
        for (int b = 0; b < 32 && ok; b++) {
            int rb = (rx[(off + b) / 8] >> (7 - ((off + b) % 8))) & 1;
            int tb = (target[b / 8] >> (7 - (b % 8))) & 1;
            if (rb != tb) ok = false;
        }
        if (ok) return off;
    }
    return -1;
}

void dwHardReset() {
    pinMode(PIN_RST, OUTPUT); digitalWrite(PIN_RST, LOW); delay(2);
    pinMode(PIN_RST, INPUT);  delay(5);
}

void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis(); while (!Serial && millis() - t0 < 2000) {}
    Serial.println("\n=== DW3000 old-wiring DECISIVE sweep (mode x input_delay, bit-scan) ===");
    busInit();
    dwHardReset();
}

void loop() {
    const int delays[] = {0, 20, 40, 60, 80, 100};
    for (int mode = 0; mode <= 3; mode++) {
        for (int di = 0; di < 6; di++) {
            addDevice(2000000, mode, delays[di]);
            uint8_t rx[12] = {0};
            readRegN(0x40, 0x00, true, rx, 12);
            spi_bus_remove_device(dw_spi); dw_spi = nullptr;
            int bo = findDevIdBit(rx, 12);
            Serial.printf("m=%d id=%3d: %02X %02X %02X %02X %02X %02X %02X %02X | DEVID bitoff=%d %s\n",
                mode, delays[di], rx[0],rx[1],rx[2],rx[3],rx[4],rx[5],rx[6],rx[7],
                bo, bo == 0 ? "<<< CLEAN!" : (bo > 0 ? "(recoverable)" : ""));
        }
    }
    Serial.println("--- sweep done (repeat in 5s) ---");
    delay(5000);
}
