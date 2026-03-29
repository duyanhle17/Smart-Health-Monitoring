#include <WiFi.h>

void setup() {
  Serial.begin(115200);
  
  // Thiết lập WiFi ở chế độ Station
  WiFi.mode(WIFI_STA);
  
  // In địa chỉ MAC ra Serial Monitor
  Serial.println();
  Serial.print("ESP32 Board MAC Address:  ");
  Serial.println(WiFi.macAddress());
}

void loop() {
  // Không cần làm gì trong loop
}
