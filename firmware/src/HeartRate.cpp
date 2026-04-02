#include "HeartRate.h"
#include "MAX30105.h"

// ── DSP state ──────────────────────────────────────────────
static MAX30105 _sensor;
static float    _dc       = 0;
static float    _lp       = 0;
static float    _prevLp   = 0;
static float    _lastValley = 0;
static bool     _rising   = false;
static uint32_t _lastBeatMs = 0;

// ── Window 5s ──────────────────────────────────────────────
static constexpr int BUF  = 30;
static float    _buf[BUF];
static int      _beatCount    = 0;
static uint32_t _windowStart  = 0;
static int      _lastValidBpm = 0;
static float    _lastTemp     = 0.0f;

// ── Forward declarations ────────────────────────────────────
static void _reset();
static int  _trimmedMean();

// ───────────────────────────────────────────────────────────
bool heartrate_begin(TwoWire &wire) {
    if (!_sensor.begin(wire, I2C_SPEED_FAST)) return false;
    _sensor.setup(0x1F, 8, 2, 400, 411, 4096);
    _sensor.setPulseAmplitudeRed(0x0A);
    _sensor.setPulseAmplitudeGreen(0);
    _reset();
    return true;
}

void heartrate_update(HeartRateStats &out) {
    uint32_t ir  = _sensor.getIR();
    uint32_t now = millis();

    out.isNewResult    = false;
    out.ir             = ir;
    out.chipTemp       = _lastTemp;

    // ── Kiểm tra ngón tay ───────────────────────────────────
    if (ir < 50000) {
        _reset();
        out.fingerDetected = false;
        out.bpm            = 0;
        return;
    }
    out.fingerDetected = true;

    // ── DSP: phát hiện đỉnh ────────────────────────────────
    if (_dc == 0) _dc = ir;
    _dc = 0.95f * _dc + 0.05f * (float)ir;
    float ac = (float)ir - _dc;
    _lp = _lp + 0.2f * (ac - _lp);

    if (_lp > _prevLp) {
        _rising = true;
    } else {
        if (_rising) {
            if (_prevLp - _lastValley > 20.0f) {
                if (_lastBeatMs > 0 && (now - _lastBeatMs > 250)) {
                    float rate = 60000.0f / (float)(now - _lastBeatMs);
                    if (rate > 40 && rate < 220 && _beatCount < BUF) {
                        _buf[_beatCount++] = rate;
                    }
                }
                _lastBeatMs = now;
            }
            _lastValley = _lp;
        }
        _rising = false;
    }
    _prevLp = _lp;

    // ── Chu kỳ 5 giây ──────────────────────────────────────
    if (now - _windowStart > 5000) {
        out.bpm         = _trimmedMean();
        out.isNewResult = true;

        _lastTemp    = _sensor.readTemperature();
        out.chipTemp = _lastTemp;

        _beatCount   = 0;
        _windowStart = now;
    } else {
        out.bpm = _lastValidBpm;
    }
}

// ── Private helpers ────────────────────────────────────────
static void _reset() {
    _dc = _lp = _prevLp = _lastValley = 0;
    _rising       = false;
    _beatCount    = 0;
    _windowStart  = millis();
    _lastValidBpm = 0;
    // _lastTemp giữ nguyên — tránh nhảy về 0
}

static int _trimmedMean() {
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

    _lastValidBpm = (int)(sum / cnt);
    return _lastValidBpm;
}