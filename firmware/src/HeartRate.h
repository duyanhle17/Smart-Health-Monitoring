#pragma once
#include <Arduino.h>
#include <Wire.h>

struct HeartRateStats {
    uint32_t ir;             // Raw IR (realtime)
    bool     fingerDetected; // Có ngón tay
    int      bpm;            // BPM trung bình 5s (chỉ cập nhật khi chất lượng đạt)
    bool     isNewResult;    // Vừa tính xong chu kỳ 5s
    float    chipTemp;       // Nhiệt độ chip MAX30102 (°C)
    // Chất lượng tín hiệu để backend/consumer biết CÓ tin được nhịp tim không,
    // thay vì nhận một con số bịa ra từ nhiễu chuyển động.
    uint8_t  quality;        // 0..100: kết hợp perfusion + độ đều nhịp + số beat
    float    perfusion;      // Perfusion index = 100 * AC/DC, thước đo biên độ PPG
    uint16_t lastIbiMs;      // Khoảng cách 2 nhịp gần nhất (ms), 0 nếu chưa có
    uint8_t  beatsInWindow;  // Số beat hợp lệ gom được trong cửa sổ 5 s
    int      spo2;           // SpO2 % (0 = chưa/không đo được)
    bool     spo2Valid;      // Đủ tưới máu + chất lượng để tin SpO2
};

bool heartrate_begin(TwoWire &wire);
void heartrate_update(HeartRateStats &out);

// Cảm biến có đang trả lời không. heartrate_update() tự dò lại mỗi 5 s nếu mất,
// nên giá trị này có thể chuyển từ false sang true trong lúc chạy.
bool heartrate_present();

// Lần khởi tạo gần nhất mất mấy lần thử (1 = nhận ngay). >1 nghĩa là cảm biến
// đáp chậm/chập chờn — theo dõi con số này để biết mối hàn có vấn đề không.
int  heartrate_attempts();