#include "HeartRate.h"
#include "MAX30105.h"

// ── DSP state ──────────────────────────────────────────────
static MAX30105 _sensor;
static float    _dc       = 0;
static float    _lp       = 0;
static float    _prevLp   = 0;
static float    _valley   = 0;      // running minimum of _lp since the last beat
static bool     _rising   = false;
static uint32_t _lastBeatMs = 0;
static float    _acAmp    = 0;      // EMA of validated beat prominence (adaptive)
static uint16_t _lastIbiMs = 0;     // most recent inter-beat interval

// A fixed 20-count prominence threshold either missed beats when perfusion was
// low (weak PPG on a cold/loose finger reads too slow) or fired on the dicrotic
// notch when perfusion was high (reads too fast). Gate each candidate beat on a
// fraction of the tracked AC amplitude instead, with an absolute floor so pure
// noise on an empty sensor cannot manufacture beats.
static constexpr float PEAK_FRACTION      = 0.35f;
static constexpr float PEAK_MIN_PROMINENCE = 12.0f;
// Perfusion index below this means the pulsatile component is too small to
// trust; the DSP still runs but the reading is flagged low quality.
static constexpr float MIN_PERFUSION_PCT  = 0.05f;

// ── Window 5s ──────────────────────────────────────────────
static constexpr int BUF  = 30;
static float    _buf[BUF];
static int      _beatCount    = 0;
static uint32_t _windowStart  = 0;
static int      _lastValidBpm = 0;
static float    _lastTemp     = 0.0f;
static uint8_t  _quality      = 0;
static float    _perfusion    = 0.0f;

// ── SpO2: tỉ số biên độ Red/IR (ratio-of-ratios) trên cửa sổ 5 s ──────────
// SpO2 ≈ A - B·R, với R = (AC_red/DC_red)/(AC_ir/DC_ir). Hằng số A,B là kinh
// nghiệm — PHẢI hiệu chỉnh lại với máy đo SpO2 chuẩn khi commission. Cần đèn đỏ
// sáng hơn mức chỉ-đo-nhịp để thành phần đập của kênh đỏ vượt sàn nhiễu.
static int      _spo2      = 0;
static bool     _spo2Valid = false;
static double   _irSumW = 0, _redSumW = 0;
static uint32_t _irMinW = 0, _irMaxW = 0, _redMinW = 0, _redMaxW = 0;
static uint32_t _sampW  = 0;
static constexpr float SPO2_CAL_A = 104.0f;
static constexpr float SPO2_CAL_B = 17.0f;
static constexpr uint8_t SPO2_MIN_QUALITY = 40;   // chỉ tin SpO2 khi HR đủ sạch

// ── Trạng thái cảm biến ────────────────────────────────────
static TwoWire *_wire    = nullptr;
static bool     _present = false;
static int      _attempts = 0;      // số lần thử của lần khởi tạo gần nhất
static uint32_t _lastProbe = 0;
#define MAX30102_ADDR   0x57
#define REPROBE_MS      5000

// ── Forward declarations ────────────────────────────────────
static void _reset();
static int  _trimmedMean(uint8_t &qualityOut);

// ───────────────────────────────────────────────────────────
// Thử khởi tạo 1 lần. MAX30102 cần vài chục ms sau khi có nguồn mới đáp I2C,
// nên gọi ngay sau Wire.begin() hay trượt — thử lại vài nhịp.
static bool _tryBegin() {
    if (!_sensor.begin(*_wire, I2C_SPEED_FAST, MAX30102_ADDR)) return false;
    _sensor.setup(0x1F, 8, 2, 400, 411, 4096);
    // Đèn đỏ để mức đo được SpO2 (ngang IR), không còn 0x0A của chế độ chỉ-nhịp.
    // IR vẫn dùng cho DSP nhịp tim; tăng dòng đỏ không ảnh hưởng kênh IR.
    _sensor.setPulseAmplitudeRed(0x24);
    _sensor.setPulseAmplitudeGreen(0);
    _reset();
    return true;
}

bool heartrate_begin(TwoWire &wire) {
    _wire = &wire;
    for (int attempt = 1; attempt <= 3; attempt++) {
        delay(50);                     // chờ cảm biến ổn định sau khi cấp nguồn
        _attempts = attempt;
        if (_tryBegin()) { _present = true; break; }
    }
    _lastProbe = millis();
    return _present;
}

bool heartrate_present()  { return _present; }
int  heartrate_attempts() { return _attempts; }

void heartrate_update(HeartRateStats &out) {
    uint32_t now = millis();

    // Không có cảm biến: KHÔNG được đọc I2C mỗi vòng lặp. getIR() của thư viện
    // poll FIFO tới 250 ms mỗi lần gọi -> loop() sẽ bò. Thay vào đó dò lại mỗi
    // 5 s để mối hàn chập chờn tự phục hồi mà không cần khởi động lại.
    if (!_present) {
        out = HeartRateStats{};
        out.chipTemp = _lastTemp;
        if (now - _lastProbe >= REPROBE_MS) {
            _lastProbe = now;
            _present = _tryBegin();
        }
        return;
    }

    uint32_t ir  = _sensor.getIR();
    uint32_t red = _sensor.getRed();

    out.isNewResult    = false;
    out.ir             = ir;
    out.chipTemp       = _lastTemp;
    out.perfusion      = _perfusion;
    out.lastIbiMs      = _lastIbiMs;
    out.beatsInWindow  = (uint8_t)_beatCount;
    out.quality        = _quality;
    out.spo2           = _spo2;
    out.spo2Valid      = _spo2Valid;

    // ── Kiểm tra ngón tay ───────────────────────────────────
    if (ir < 50000) {
        _reset();
        out.fingerDetected = false;
        out.bpm            = 0;
        out.quality        = 0;
        out.perfusion      = 0.0f;
        out.spo2           = 0;
        out.spo2Valid      = false;
        return;
    }
    out.fingerDetected = true;

    // ── SpO2: gom min/max/tổng của IR & Red trong cửa sổ (chỉ khi có ngón tay) ──
    if (_sampW == 0) { _irMinW = _irMaxW = ir; _redMinW = _redMaxW = red; }
    else {
        if (ir  < _irMinW)  _irMinW  = ir;   if (ir  > _irMaxW)  _irMaxW  = ir;
        if (red < _redMinW) _redMinW = red;  if (red > _redMaxW) _redMaxW = red;
    }
    _irSumW += ir; _redSumW += red; _sampW++;

    // ── DSP: phát hiện đỉnh ────────────────────────────────
    if (_dc == 0) _dc = ir;
    _dc = 0.95f * _dc + 0.05f * (float)ir;
    float ac = (float)ir - _dc;
    _lp = _lp + 0.2f * (ac - _lp);

    // Track the trough between beats so a peak's prominence is measured against
    // the real valley, not a stale post-peak level.
    if (_lp < _valley) _valley = _lp;

    if (_lp > _prevLp) {
        _rising = true;
    } else {
        if (_rising) {
            // _prevLp was a local maximum. Its prominence over the trough since
            // the last beat is the beat amplitude; compare it to an adaptive
            // threshold rather than a fixed count.
            const float prominence = _prevLp - _valley;
            const float threshold = max(PEAK_FRACTION * _acAmp, PEAK_MIN_PROMINENCE);
            if (prominence > threshold) {
                if (_lastBeatMs > 0 && (now - _lastBeatMs > 250)) {
                    const uint32_t ibi = now - _lastBeatMs;
                    float rate = 60000.0f / (float)ibi;
                    if (rate > 40 && rate < 220 && _beatCount < BUF) {
                        _buf[_beatCount++] = rate;
                        _lastIbiMs = (uint16_t)ibi;
                    }
                }
                _lastBeatMs = now;
                _acAmp = (_acAmp <= 0.0f) ? prominence
                                          : 0.8f * _acAmp + 0.2f * prominence;
                _valley = _lp;   // start a fresh trough search for the next beat
            }
        }
        _rising = false;
    }
    _prevLp = _lp;

    // Perfusion index: pulsatile amplitude relative to the DC level. Low PI is
    // the classic marker of an unreliable PPG reading (cold, loose, or moving).
    _perfusion = (_dc > 0.0f) ? (100.0f * _acAmp / _dc) : 0.0f;
    out.perfusion = _perfusion;

    // ── Chu kỳ 5 giây ──────────────────────────────────────
    if (now - _windowStart > 5000) {
        uint8_t windowQuality = 0;
        out.bpm         = _trimmedMean(windowQuality);
        _quality        = windowQuality;
        out.quality     = windowQuality;
        out.isNewResult = true;

        _lastTemp    = _sensor.readTemperature();
        out.chipTemp = _lastTemp;

        // ── SpO2 từ tỉ số biên độ Red/IR trên cửa sổ vừa qua ──
        _spo2Valid = false;
        if (_sampW > 0) {
            float dcIr  = (float)(_irSumW  / _sampW);
            float dcRed = (float)(_redSumW / _sampW);
            float acIr  = (float)(_irMaxW  - _irMinW);
            float acRed = (float)(_redMaxW - _redMinW);
            if (dcIr > 0.0f && dcRed > 0.0f && acIr > 0.0f) {
                float R = (acRed / dcRed) / (acIr / dcIr);
                // Chỉ tin SpO2 khi R hợp lệ, nhịp đủ sạch và tưới máu đủ.
                if (R > 0.3f && R < 3.4f &&
                    windowQuality >= SPO2_MIN_QUALITY &&
                    _perfusion >= MIN_PERFUSION_PCT) {
                    float s = SPO2_CAL_A - SPO2_CAL_B * R;
                    _spo2      = (int)max(70.0f, min(100.0f, s));
                    _spo2Valid = true;
                }
            }
        }
        out.spo2      = _spo2;
        out.spo2Valid = _spo2Valid;
        _irSumW = _redSumW = 0; _sampW = 0;   // mở cửa sổ SpO2 mới

        out.beatsInWindow = (uint8_t)_beatCount;
        _beatCount   = 0;
        _windowStart = now;
    } else {
        out.bpm = _lastValidBpm;
    }
}

// ── Private helpers ────────────────────────────────────────
static void _reset() {
    _dc = _lp = _prevLp = _valley = 0;
    _rising       = false;
    _beatCount    = 0;
    _windowStart  = millis();
    _lastValidBpm = 0;
    _acAmp        = 0;
    _lastIbiMs    = 0;
    _quality      = 0;
    _perfusion    = 0.0f;
    _spo2         = 0;
    _spo2Valid    = false;
    _irSumW = _redSumW = 0; _sampW = 0;
    // _lastTemp giữ nguyên — tránh nhảy về 0
}

// Robust window BPM plus a 0..100 quality score. The score falls with a low
// perfusion index, too few beats, or beat-to-beat scatter (the fingerprint of
// motion). When quality is poor the previous good BPM is HELD rather than
// overwritten with a motion-corrupted average, so a walking worker's reading
// degrades gracefully instead of jumping.
static int _trimmedMean(uint8_t &qualityOut) {
    qualityOut = 0;
    if (_beatCount < 3) return _lastValidBpm;

    // Bubble sort tăng dần
    for (int i = 0; i < _beatCount - 1; i++)
        for (int j = 0; j < _beatCount - i - 1; j++)
            if (_buf[j] > _buf[j+1]) {
                float tmp  = _buf[j];
                _buf[j]    = _buf[j+1];
                _buf[j+1]  = tmp;
            }

    // Bỏ 1 đầu + 1 đuôi nếu đủ mẫu
    int start = (_beatCount >= 5) ? 1 : 0;
    int end   = (_beatCount >= 5) ? _beatCount - 1 : _beatCount;

    float sum = 0; int cnt = 0;
    for (int i = start; i < end; i++) { sum += _buf[i]; cnt++; }
    if (cnt == 0) return _lastValidBpm;
    const float mean = sum / cnt;

    // Coefficient of variation of the trimmed beats. A clean pulse has tightly
    // clustered instantaneous rates; motion scatters them.
    float var = 0;
    for (int i = start; i < end; i++) {
        const float d = _buf[i] - mean;
        var += d * d;
    }
    const float cv = (mean > 0) ? (sqrtf(var / cnt) / mean) : 1.0f;

    // Blend three independent quality cues into 0..100.
    const float countScore = min(1.0f, (float)_beatCount / 8.0f);      // ≥8 beats/5 s is healthy
    const float perfScore  = min(1.0f, _perfusion / 0.5f);             // PI ≥0.5 % is strong
    const float steadyScore = max(0.0f, 1.0f - cv / 0.25f);            // CV ≥0.25 → 0
    const float q = 100.0f * countScore * perfScore * steadyScore;
    qualityOut = (uint8_t)max(0.0f, min(100.0f, q));

    // Reject the window outright when it is too weak or too jittery to believe;
    // hold the last trusted BPM instead of publishing a fabricated one.
    if (_perfusion < MIN_PERFUSION_PCT || cv > 0.35f) {
        return _lastValidBpm;
    }

    _lastValidBpm = (int)(mean + 0.5f);
    return _lastValidBpm;
}