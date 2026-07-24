#pragma once
#include <Arduino.h>

// Cau hinh mang luu trong NVS (flash), khai bao mot lan qua Serial roi giu mai
// - khong can sua config.h va nap lai firmware moi khi doi WiFi.
// Gia tri trong config.h chi la MAC DINH khi NVS con trong.
//
// Lenh go vao Serial monitor (115200, gui kem xuong dong):
//     help
//     show
//     wifi <ssid> <password>      password de trong = mang mo
//     url  <http://ip:5000/api/device_telemetry>
//     id   <WK_102>
//     clear                       xoa het, quay ve mac dinh trong config.h
//     reboot

struct NetConfig {
    String ssid;
    String pass;
    String url;
    String workerId;
};

// Doc cau hinh tu NVS (rot ve mac dinh config.h neu chua co). Goi trong setup().
void netcfg_begin();

// Cau hinh dang dung.
const NetConfig &netcfg();

// Doc lenh tu Serial. Tra ve true khi SSID/mat khau vua doi -> caller nen
// ket noi lai WiFi. Goi lien tuc trong loop(), khong block.
bool netcfg_service(Stream &io);
