#include "HeartRate.h"
#include "MAX30105.h"

// ── DSP state ──────────────────────────────────────────────
static MAX30105 _sensor;
static float    _dc       = 0;      // baseline (DC) follower
static float    _lp       = 0;      // band-passed, zero-mean PPG
static float    _prevLp   = 0;
static float    _env      = 0;      // amplitude envelope: fast attack, slow decay
static bool     _rising   = false;
static uint32_t _lastBeatMs = 0;
static uint16_t _lastIbiMs = 0;     // most recent inter-beat interval

// A beat is a local maximum of the band-passed pulse that rises above
// THRESHOLD_FRACTION of the tracked amplitude envelope. Because the envelope
// keeps decaying between beats (it is not only updated when a beat is
// confirmed), the threshold follows the real signal level even across a missed
// beat. The previous scheme updated its amplitude estimate ONLY on accepted
// beats, so on a weak, drifting wrist PPG it starved to 1-2 detections per
// window and never reached the >=3 beats needed to publish a rate.
static constexpr float THRESHOLD_FRACTION = 0.35f;
static constexpr float ENVELOPE_DECAY     = 0.99f;   // ~2 s time constant at 50 Hz
static constexpr float PEAK_MIN_AMPLITUDE = 12.0f;   // absolute noise floor
// Perfusion index below this means the pulsatile component is too small to
// trust; the DSP still runs but the reading is flagged low quality.
static constexpr float MIN_PERFUSION_PCT  = 0.05f;
// IR DC floor that means "skin is on the sensor". Tuned for wrist/arm wear,
// where reflected IR is far weaker than at a fingertip. See use site.
static constexpr uint32_t CONTACT_IR_THRESHOLD = 30000;

// ── Beat buffer: sliding window of recent beats ─────────────
// BPM refreshes every BPM_UPDATE_MS (feels live) but is averaged over the beats
// from the last HR_WINDOW_MS (stays smooth). Decoupling the two is what lets a
// 2 s update stay stable even at a resting rate, where 2 s alone would hold
// only ~2 beats. SpO2 keeps its own longer window.
static constexpr uint32_t BPM_UPDATE_MS  = 2000;
static constexpr uint32_t HR_WINDOW_MS   = 6000;
static constexpr uint32_t SPO2_WINDOW_MS = 5000;
static constexpr int BUF  = 16;
static float    _buf[BUF];          // recent beat rates (bpm)
static uint32_t _bufAt[BUF];        // millis timestamp of each beat
static int      _beatCount    = 0;  // beats currently held (<= BUF)
static uint32_t _lastBpmUpdate = 0;
static uint32_t _spo2Start     = 0;
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
static int  _computeBpm(const float *rates, int n, uint8_t &qualityOut);

// ───────────────────────────────────────────────────────────
// Thử khởi tạo 1 lần. MAX30102 cần vài chục ms sau khi có nguồn mới đáp I2C,
// nên gọi ngay sau Wire.begin() hay trượt — thử lại vài nhịp.
static bool _tryBegin() {
    if (!_sensor.begin(*_wire, I2C_SPEED_FAST, MAX30102_ADDR)) return false;
    _sensor.setup(0x1F, 8, 2, 400, 411, 4096);
    // Đèn đỏ để mức đo được SpO2 (ngang IR), không còn 0x0A của chế độ chỉ-nhịp.
    // IR vẫn dùng cho DSP nhịp tim; tăng dòng đỏ không ảnh hưởng kênh IR.
    _sensor.setPulseAmplitudeRed(0x24);
    // IR ở 0x1F (~6.4 mA). Bản 0x3F đã đẩy ADC IR 18-bit tới trần 262143 khi
    // áp ĐẦU NGÓN TAY (gần, phản xạ mạnh) -> DC bị clip phẳng, mất hẳn AC nên
    // không phát hiện được nhịp. 0x1F cho ~50k ở CẢ cổ tay lẫn ngón tay, cách
    // xa cả trần bão hoà lẫn sàn tiếp xúc 30k.
    _sensor.setPulseAmplitudeIR(0x1F);
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

    // ── Kiểm tra tiếp xúc da ────────────────────────────────
    // 30000, không phải 50000: 50k hợp cho ĐẦU NGÓN TAY, nhưng đây là thiết bị
    // ĐEO ở cổ tay/cánh tay nơi IR phản xạ về thấp hơn nhiều (đo thực ~45k khi
    // đeo, <15k khi tháo ra), nên ngưỡng 50k loại nhầm da đeo hợp lệ.
    if (ir < CONTACT_IR_THRESHOLD) {
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

    // ── DSP: bandpass + envelope-based adaptive peak detection ──
    // DC follower removes the baseline. Kept slow (~0.24 Hz) so it does not eat
    // pulse energy even at a 40 bpm (0.67 Hz) rate.
    if (_dc == 0) _dc = ir;
    _dc = 0.97f * _dc + 0.03f * (float)ir;
    float ac = (float)ir - _dc;
    // Low-pass the AC to ~2.4 Hz: keeps the pulse up to ~150 bpm while rejecting
    // high-frequency noise. _lp is the zero-mean band-passed pulse.
    _lp = _lp + 0.30f * (ac - _lp);

    // Amplitude envelope: jump up to each excursion, then decay slowly. The
    // threshold is a fraction of this envelope, so it keeps tracking the real
    // signal level across a missed beat instead of collapsing — the key to
    // catching a weak, drifting wrist PPG reliably.
    const float mag = fabsf(_lp);
    if (mag > _env) _env = mag;                 // instant attack
    else            _env = ENVELOPE_DECAY * _env;   // slow decay
    const float threshold = THRESHOLD_FRACTION * _env;

    // Beat = local maximum of _lp that clears the adaptive threshold, subject to
    // a 300 ms refractory (=> <= 200 bpm, and one detection per pulse).
    if (_lp > _prevLp) {
        _rising = true;
    } else {
        if (_rising && _prevLp > threshold && _prevLp > PEAK_MIN_AMPLITUDE) {
            if (_lastBeatMs == 0) {
                _lastBeatMs = now;              // first beat: start the clock
            } else if (now - _lastBeatMs > 300) {
                const uint32_t ibi = now - _lastBeatMs;
                float rate = 60000.0f / (float)ibi;
                if (rate > 40 && rate < 200) {
                    if (_beatCount < BUF) {
                        _buf[_beatCount] = rate; _bufAt[_beatCount] = now; _beatCount++;
                    } else {                       // ring full: drop the oldest
                        for (int k = 1; k < BUF; k++) { _buf[k-1] = _buf[k]; _bufAt[k-1] = _bufAt[k]; }
                        _buf[BUF-1] = rate; _bufAt[BUF-1] = now;
                    }
                    _lastIbiMs = (uint16_t)ibi;
                }
                _lastBeatMs = now;              // advance only on an accepted beat
            }
            // A peak inside the refractory window is a dicrotic notch / ripple:
            // ignore it and do NOT advance the clock.
        }
        _rising = false;
    }
    _prevLp = _lp;

    // Perfusion index: envelope amplitude relative to the DC level. Low PI is
    // the classic marker of an unreliable PPG reading (cold, loose, or moving).
    _perfusion = (_dc > 0.0f) ? (100.0f * _env / _dc) : 0.0f;
    out.perfusion = _perfusion;

    // ── BPM: làm mới mỗi 2 s, trung bình các nhịp trong 6 s gần nhất ──
    if (now - _lastBpmUpdate >= BPM_UPDATE_MS) {
        _lastBpmUpdate = now;
        // Bỏ các nhịp cũ hơn cửa sổ trung bình để mạch ngừng thì số tự phân rã,
        // giữ đúng cặp rate<->timestamp (nén tại chỗ, không sắp xếp _buf).
        int w = 0;
        for (int i = 0; i < _beatCount; i++) {
            if (now - _bufAt[i] <= HR_WINDOW_MS) { _buf[w] = _buf[i]; _bufAt[w] = _bufAt[i]; w++; }
        }
        _beatCount = w;
        uint8_t q = 0;
        _lastValidBpm = _computeBpm(_buf, _beatCount, q);
        _quality = q;
        out.isNewResult = true;
    }
    out.bpm           = _lastValidBpm;
    out.quality       = _quality;
    out.beatsInWindow = (uint8_t)_beatCount;

    // ── SpO2 + nhiệt độ chip: cửa sổ 5 s độc lập ──
    if (now - _spo2Start >= SPO2_WINDOW_MS) {
        _spo2Start = now;
        _lastTemp    = _sensor.readTemperature();
        out.chipTemp = _lastTemp;

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
                    _quality >= SPO2_MIN_QUALITY &&
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
    }
}

// ── Private helpers ────────────────────────────────────────
static void _reset() {
    _dc = _lp = _prevLp = _env = 0;
    _rising        = false;
    _beatCount     = 0;
    _lastBpmUpdate = millis();
    _spo2Start     = millis();
    _lastValidBpm  = 0;
    _lastIbiMs     = 0;
    _quality       = 0;
    _perfusion     = 0.0f;
    _spo2          = 0;
    _spo2Valid     = false;
    _irSumW = _redSumW = 0; _sampW = 0;
    // _lastTemp giữ nguyên — tránh nhảy về 0
}

// Robust window BPM plus a 0..100 quality score. The score falls with a low
// perfusion index, too few beats, or beat-to-beat scatter (the fingerprint of
// motion). When quality is poor the previous good BPM is HELD rather than
// overwritten with a motion-corrupted average, so a walking worker's reading
// degrades gracefully instead of jumping.
static int _computeBpm(const float *rates, int n, uint8_t &qualityOut) {
    qualityOut = 0;
    if (n < 3) return _lastValidBpm;

    // Sort a COPY: _buf must stay in time order so its rate<->timestamp pairing
    // with _bufAt survives for the sliding-window prune.
    float s[BUF];
    for (int i = 0; i < n && i < BUF; i++) s[i] = rates[i];
    for (int i = 1; i < n; i++) {           // insertion sort
        const float v = s[i];
        int j = i;
        while (j > 0 && s[j-1] > v) { s[j] = s[j-1]; j--; }
        s[j] = v;
    }

    // Bỏ 1 đầu + 1 đuôi nếu đủ mẫu
    int start = (n >= 5) ? 1 : 0;
    int end   = (n >= 5) ? n - 1 : n;

    float sum = 0; int cnt = 0;
    for (int i = start; i < end; i++) { sum += s[i]; cnt++; }
    if (cnt == 0) return _lastValidBpm;
    const float mean = sum / cnt;

    // Coefficient of variation of the trimmed beats. A clean pulse has tightly
    // clustered instantaneous rates; motion scatters them.
    float var = 0;
    for (int i = start; i < end; i++) {
        const float d = s[i] - mean;
        var += d * d;
    }
    const float cv = (mean > 0) ? (sqrtf(var / cnt) / mean) : 1.0f;

    // Blend three independent quality cues into 0..100.
    const float countScore = min(1.0f, (float)n / 8.0f);               // ≥8 beats is healthy
    const float perfScore  = min(1.0f, _perfusion / 0.5f);             // PI ≥0.5 % is strong
    // Zero the steadiness cue exactly at the publish gate (cv 0.35), not before
    // it: otherwise a BPM that is still accepted (cv ≤ 0.35) could carry
    // quality=0 and be discarded downstream as if it were garbage.
    const float steadyScore = max(0.0f, 1.0f - cv / 0.35f);            // CV ≥0.35 → 0
    const float q = 100.0f * countScore * perfScore * steadyScore;
    qualityOut = (uint8_t)max(0.0f, min(100.0f, q));

    // Reject outright when too weak or too jittery to believe; hold the last
    // trusted BPM instead of publishing a fabricated one.
    if (_perfusion < MIN_PERFUSION_PCT || cv > 0.35f) {
        return _lastValidBpm;
    }

    _lastValidBpm = (int)(mean + 0.5f);
    return _lastValidBpm;
}