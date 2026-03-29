#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// 1. Cấu hình mạng và Server (Backend Flask)
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
String serverUrl = "http://192.168.1.100:5000/api/device_telemetry"; // Thay 192.168.1.100 này thành IPv4 LAN của máy tính chạy server Flask.

// 2. ID để định danh thiết bị Worker Node trên dashboard
const String workerId = "W1";

// 3. Biến toàn cục lấy từ Senor
float currentX = 15.0; // Khoảng cách giả lập lấy từ Anchor 
float currentY = 50.0;
float heartRate = 75.0;
float gasPpm = 2.5;

void setup() {
  Serial.begin(115200);
  
  // Khởi động module WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while(WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[MESH-NODE] Connected to Network!");
}

void loop() {
  // Chu kỳ gửi: 1 lần mỗi giây
  if(WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");

    // ==========================================
    // BƯỚC 1: CẬP NHẬT GIÁ TRỊ TỪ CẢM BIẾN
    // ==========================================
    // * Ở code thực tế, bạn nối dây thiết bị và thay thế bằng các hàm: 
    // heartRate = MAX30102.getHeartRate(); 
    // gasPpm = readMQ4Gas();
    // bool isFalling = mpu.detectFall(); 
    // currentX = doToFRanging();
    
    // Giả lập chút thay đổi cho sinh động
    heartRate = 70 + random(0, 10); 
    gasPpm = 1.0 + random(0, 50) / 10.0;
    
    bool isFalling = false; // "SAFE" hoặc "FALL"
    
    // ==========================================
    // BƯỚC 2: BUILD CHUỖI JSON THEO ĐÚNG API CỦA FLASK
    // ==========================================
    StaticJsonDocument<512> doc; 
    
    doc["worker_id"] = workerId;
    
    JsonObject telemetry = doc.createNestedObject("telemetry");
    telemetry["x"] = currentX;
    telemetry["y"] = currentY;
    telemetry["hr"] = heartRate;
    telemetry["gas"] = gasPpm;
    
    // Thông số gia tốc kế (IMU)
    telemetry["ax"] = 0.0; 
    telemetry["ay"] = 1.0; 
    telemetry["az"] = 0.0;
    telemetry["gx"] = 0.0;
    telemetry["gy"] = 0.0;
    telemetry["gz"] = 0.0;
    
    telemetry["fall_alert"] = isFalling ? "FALL" : "SAFE";

    String jsonPayload;
    serializeJson(doc, jsonPayload);

    // ==========================================
    // BƯỚC 3: GỬI GÓI HTTP POST 
    // ==========================================
    int httpResponseCode = http.POST(jsonPayload);
    
    // In ra cửa sổ debug Serial Monitor
    Serial.print("Đã gửi Payload: ");
    Serial.println(jsonPayload);
    Serial.print("Mã HTTP Response: ");
    Serial.println(httpResponseCode); // Nêú trả về 200 là thành công
    
    http.end();
  } else {
    Serial.println("Lỗi: Mất kết nối WiFi!");
  }
  
  delay(1000); 
}
