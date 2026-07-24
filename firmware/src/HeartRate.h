#pragma once
#include <Arduino.h>
#include <Wire.h>

struct HeartRateStats {
    uint32_t ir;             // Raw IR (realtime)
    bool     fingerDetected; // Có ngón tay
    int      bpm;            // BPM trung bình 5s
    bool     isNewResult;    // Vừa tính xong chu kỳ 5s
    float    chipTemp;       // Nhiệt độ chip MAX30102 (°C)
};

bool heartrate_begin(TwoWire &wire);
void heartrate_update(HeartRateStats &out);

// Cảm biến có đang trả lời không. heartrate_update() tự dò lại mỗi 5 s nếu mất,
// nên giá trị này có thể chuyển từ false sang true trong lúc chạy.
bool heartrate_present();

// Lần khởi tạo gần nhất mất mấy lần thử (1 = nhận ngay). >1 nghĩa là cảm biến
// đáp chậm/chập chờn — theo dõi con số này để biết mối hàn có vấn đề không.
int  heartrate_attempts();