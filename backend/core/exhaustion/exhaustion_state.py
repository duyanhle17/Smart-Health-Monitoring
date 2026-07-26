"""
Exhaustion streaming inference  (SafeWork)
==========================================
Suy luận kiệt sức THỜI GIAN THỰC cho từng worker từ luồng telemetry
(nhịp tim MAX30102 + thân nhiệt MAX30205 [+ huyết áp nếu có]). Cùng khuôn
với backend/core/fall/fall_state.py: giữ buffer + trạng thái theo worker,
model hỏng thì fallback về công thức sinh lý (PSI) nên KHÔNG bao giờ chết.

Dùng trong route telemetry của backend, ví dụ:
    from backend.core.exhaustion.exhaustion_state import update_exhaustion_state
    res = update_exhaustion_state(worker_id, {
        "hr": 118, "temp": 37.4, "bp_map": None, "activity": 0.6,
        "timestamp": time.time(),
    })
    # res -> {"status":"MODERATE","score":6.1,"level":2,"load":0.44,"source":"model"}
"""

import os
import time
from collections import deque

import numpy as np
import joblib

from backend.core.exhaustion.exhaustion_labels import (
    PhysiologyConfig, update_fatigue_load, exhaustion_score,
    score_to_level, LEVELS, LEVEL_THRESHOLDS,
)
from backend.core.exhaustion.exhaustion_features import extract_window_features

_root = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_root, "models", "exhaustion_model.pkl")

try:
    _bundle = joblib.load(MODEL_PATH)
    _model = _bundle["model"]
    _cfg = _bundle.get("cfg", PhysiologyConfig())
    _window_min = _bundle.get("window_min", 5.0)
except Exception as e:  # pragma: no cover - vẫn chạy được nếu chưa train
    print(f"[Warning] Chưa nạp được exhaustion model ({MODEL_PATH}): {e}")
    _bundle, _model = None, None
    _cfg = PhysiologyConfig()
    _window_min = 5.0

# Cần tối thiểu bao nhiêu mẫu trong cửa sổ mới tin model (tránh khởi động lạnh)
MIN_SAMPLES = 8
# Làm mượt điểm bằng EMA
SCORE_EMA_ALPHA = 0.3
# Vùng chết (deadband) quanh mỗi ngưỡng cấp độ, tính bằng điểm: cấp chỉ đổi khi
# điểm vượt ngưỡng thêm biên này -> không nhấp nháy ở ranh giới, nhưng status
# vẫn bám sát score (không phụ thuộc đồng hồ treo tường).
LEVEL_MARGIN = 0.3


def _level_with_hysteresis(cur, score):
    target = score_to_level(score)
    if target > cur and score < LEVEL_THRESHOLDS[cur] + LEVEL_MARGIN:
        return cur
    if target < cur and cur >= 1 and score > LEVEL_THRESHOLDS[cur - 1] - LEVEL_MARGIN:
        return cur
    return target


_state = {}


def _get(worker_id):
    if worker_id not in _state:
        _state[worker_id] = {
            "buf": deque(),               # (t_min, hr, temp, bp_map, activity)
            "load": 0.0,
            "last_hr": _cfg.hr_rest,
            "shift_start": None,
            "last_ts": None,
            "score_ema": 0.0,
            "_ema_init": False,
            "level": 0,
        }
    return _state[worker_id]


def _clean_hr(v, last_good):
    lo, hi = _cfg.hr_valid
    if v is not None and np.isfinite(v) and lo <= v <= hi:
        return float(v)
    return last_good


def reset_worker(worker_id):
    """Gọi khi bắt đầu ca mới hoặc worker offline lâu."""
    _state.pop(worker_id, None)


def update_exhaustion_state(worker_id, sample):
    """
    sample: {"hr":?, "temp":?(opt), "bp_map":?(opt), "activity":?(opt),
             "timestamp": epoch_seconds(opt)}
    Trả dict: status/level/score/load/source.
    """
    st = _get(worker_id)
    now = float(sample.get("timestamp") or time.time())
    if st["shift_start"] is None:
        st["shift_start"] = now
    # Ngắt quãng dài -> coi như ca mới (tránh cộng dồn load qua đêm)
    if st["last_ts"] is not None and (now - st["last_ts"]) > 600:
        reset_worker(worker_id)
        st = _get(worker_id)
        st["shift_start"] = now

    dt_min = 0.0 if st["last_ts"] is None else max(0.0, (now - st["last_ts"]) / 60.0)
    st["last_ts"] = now
    t_min = (now - st["shift_start"]) / 60.0

    hr = _clean_hr(sample.get("hr"), st["last_hr"])
    st["last_hr"] = hr
    st["load"] = update_fatigue_load(st["load"], hr, dt_min, _cfg)

    temp = sample.get("temp")
    bp = sample.get("bp_map")
    act = sample.get("activity")
    st["buf"].append({"t_min": t_min, "hr": hr,
                      "temp": temp if temp is not None else None,
                      "bp_map": bp if bp is not None else None,
                      "activity": act if act is not None else None})
    # cắt buffer về đúng cửa sổ thời gian
    while st["buf"] and (t_min - st["buf"][0]["t_min"]) > _window_min:
        st["buf"].popleft()

    window = list(st["buf"])
    source = "model"
    if _model is not None and len(window) >= MIN_SAMPLES:
        vec, _ = extract_window_features(window, fatigue_load=st["load"],
                                         shift_duration_min=t_min, cfg=_cfg)
        raw = float(np.clip(_model.predict(vec.reshape(1, -1))[0], 0, 10))
    else:
        # fallback công thức thuần khi thiếu model / chưa đủ mẫu
        source = "formula"
        raw = exhaustion_score(
            hr=hr, temp=temp, bp_map=bp, fatigue_load=st["load"], cfg=_cfg)

    # làm mượt điểm bằng EMA (khởi tạo bằng giá trị đầu, tránh kéo từ 0 lên)
    if not st["_ema_init"]:
        st["score_ema"] = raw
        st["_ema_init"] = True
    else:
        st["score_ema"] = (1 - SCORE_EMA_ALPHA) * st["score_ema"] + SCORE_EMA_ALPHA * raw
    score = st["score_ema"]

    # đổi cấp có vùng chết -> status bám score nhưng không nhấp nháy ở ranh giới
    st["level"] = _level_with_hysteresis(st["level"], score)

    return {
        "status": LEVELS[st["level"]],
        "level": st["level"],
        "score": round(score, 2),
        "instant_score": round(raw, 2),
        "load": round(st["load"], 3),
        "source": source,
        "n_samples": len(window),
        "timestamp": now,
    }
