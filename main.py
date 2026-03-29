"""
Smart Health Monitoring - FastAPI Backend v3.0
===============================================
Server nhận dữ liệu từ ESP32 Mesh Network (HR, Fall IMU),
lưu vào SQLite, và broadcast real-time qua WebSocket.

Hỗ trợ:
  - ESP32 Mesh gửi POST qua mạng khác (CORS enabled)
  - Gộp dữ liệu HR + Fall trong 1 gói tin duy nhất (/data)
  - Hoặc gửi riêng lẻ (/hr, /fall)
  - WebSocket push real-time tới Dashboard
  - API health check (/health)

Khởi chạy:
    python main.py
    # hoặc:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import time
import logging
from collections import deque
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database import engine, get_db, Base
from src.models import HeartRateRecord, FallRecord
from src.rules import rule_based_hr
from src.fall.fall_state import update_fall_state, fall_state

# ==============================================================
# LOGGING
# ==============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("mining-server")


# ==============================================================
# CONFIG
# ==============================================================
DISPLAY_INTERVAL = 5  # giây – gom HR trung bình mỗi 5s

display_hr_buffer: deque = deque()
last_display_time: float = 0
display_hr_value = None


# ==============================================================
# PYDANTIC SCHEMAS
# ==============================================================
class HRData(BaseModel):
    """Gói tin nhịp tim từ ESP32."""
    hr: float = Field(..., description="Heart rate (bpm)")


class FallData(BaseModel):
    """Gói tin IMU cho Fall Detection từ ESP32."""
    samples: List[List[float]] = Field(
        ..., description="Danh sách mẫu IMU [ax,ay,az,gx,gy,gz]"
    )


class MeshData(BaseModel):
    """
    Gói tin tổng hợp từ ESP32 Mesh Node.
    Mesh gateway gom cả HR + IMU rồi gửi 1 lần.
    """
    node_id: Optional[str] = Field(None, description="ID của node mesh (vd: 'node_01')")
    hr: Optional[float] = Field(None, description="Heart rate (bpm) - nếu có")
    samples: Optional[List[List[float]]] = Field(
        None, description="IMU samples [ax,ay,az,gx,gy,gz] - nếu có"
    )


# ==============================================================
# WEBSOCKET CONNECTION MANAGER
# ==============================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🔌 WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"🔌 WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Gửi dữ liệu JSON tới tất cả client đang kết nối."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# ==============================================================
# GLOBAL STATE
# ==============================================================
latest_hr_state = {
    "hr": None,
    "rule_status": None,
    "rule_message": None,
    "is_danger": False,
    "timestamp": 0,
}

latest_fall_state = {
    "status": "WAITING",
    "prob": 0.0,
    "timestamp": 0,
}


# ==============================================================
# APP LIFESPAN
# ==============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database initialized.")
    logger.info("🚀 Server ready at http://0.0.0.0:8000")
    yield
    logger.info("🛑 Server shutting down.")


# ==============================================================
# FASTAPI APP + CORS (cho ESP32 mesh gửi từ mạng khác)
# ==============================================================
app = FastAPI(
    title="⛏️ Smart Mining Safety",
    description="API Server nhận tín hiệu từ ESP32 Mesh và hiển thị real-time",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS: Cho phép ESP32 (hoặc bất kỳ thiết bị nào) gửi từ IP khác
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Cho phép tất cả origins
    allow_credentials=True,
    allow_methods=["*"],        # GET, POST, PUT, DELETE...
    allow_headers=["*"],        # Tất cả headers
)

templates = Jinja2Templates(directory="templates")


# ==============================================================
# WEB: Trang Dashboard
# ==============================================================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


# ==============================================================
# API: Health Check (kiểm tra server còn sống không)
# ==============================================================
@app.get("/health")
async def health_check():
    return {
        "status": "OK",
        "server": "Smart Mining Safety",
        "version": "3.0.0",
        "uptime": time.time(),
        "ws_clients": len(manager.active_connections),
    }


# ==============================================================
# API: Nhận gói tin tổng hợp từ Mesh Gateway  ★ ENDPOINT CHÍNH ★
# ==============================================================
@app.post("/data")
async def receive_mesh_data(data: MeshData, db: Session = Depends(get_db)):
    """
    Endpoint chính cho ESP32 Mesh Gateway.
    Nhận đồng thời HR + IMU trong 1 gói tin.

    Body JSON ví dụ:
    {
        "node_id": "node_01",
        "hr": 78.5,
        "samples": [[10,-255,3,0,1,-2], ...]
    }
    """
    node_id = data.node_id or "unknown"
    response = {"status": "OK", "node_id": node_id}

    # ── Xử lý HR nếu có ──
    if data.hr is not None:
        hr_result = _process_hr(data.hr, db)
        response["hr"] = hr_result

    # ── Xử lý Fall (IMU) nếu có ──
    if data.samples:
        fall_result = _process_fall(data.samples, db)
        response["fall"] = fall_result

    # Broadcast tới Dashboard
    await manager.broadcast(_build_status_payload())

    logger.info(f"📡 [{node_id}] HR={data.hr} | IMU_samples={len(data.samples) if data.samples else 0}")
    return response


# ==============================================================
# API: Nhận nhịp tim (endpoint riêng, backward compatible)
# ==============================================================
@app.post("/hr")
async def receive_hr(data: HRData, db: Session = Depends(get_db)):
    hr_result = _process_hr(data.hr, db)
    await manager.broadcast(_build_status_payload())
    return {"status": "OK", **hr_result}


# ==============================================================
# API: Nhận IMU (endpoint riêng, backward compatible)
# ==============================================================
@app.post("/fall")
async def receive_fall(data: FallData, db: Session = Depends(get_db)):
    fall_result = _process_fall(data.samples, db)
    await manager.broadcast(_build_status_payload())
    return {"status": "OK", **fall_result}


# ==============================================================
# API: Trạng thái mới nhất (fallback HTTP polling)
# ==============================================================
@app.get("/latest_status")
async def latest_status():
    return _build_status_payload()


# ==============================================================
# API: Lịch sử HR (cho biểu đồ)
# ==============================================================
@app.get("/hr_history")
async def hr_history(limit: int = 100, db: Session = Depends(get_db)):
    records = (
        db.query(HeartRateRecord)
        .order_by(HeartRateRecord.id.desc())
        .limit(limit)
        .all()
    )
    records.reverse()
    return [
        {
            "id": r.id,
            "hr": r.hr,
            "rule_status": r.rule_status,
            "is_danger": r.is_danger,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


# ==============================================================
# WEBSOCKET: Real-time cho Frontend Dashboard
# ==============================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json(_build_status_payload())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ==============================================================
# INTERNAL: Xử lý HR
# ==============================================================
def _process_hr(hr: float, db: Session) -> dict:
    global last_display_time, display_hr_value

    now = time.time()
    display_hr_buffer.append(hr)

    if now - last_display_time >= DISPLAY_INTERVAL and len(display_hr_buffer) > 0:
        display_hr_value = int(sum(display_hr_buffer) / len(display_hr_buffer))
        display_hr_buffer.clear()
        last_display_time = now

    hr_show = display_hr_value if display_hr_value is not None else int(hr)

    rule_status, rule_msg = rule_based_hr(hr_show)
    is_danger = rule_status.startswith("DANGER")

    latest_hr_state.update({
        "hr": hr_show,
        "rule_status": rule_status,
        "rule_message": rule_msg,
        "is_danger": is_danger,
        "timestamp": now,
    })

    record = HeartRateRecord(
        hr=hr_show, rule_status=rule_status,
        rule_message=rule_msg, is_danger=is_danger,
    )
    db.add(record)
    db.commit()

    return {"hr": hr_show, "status": rule_status, "message": rule_msg, "danger": is_danger}


# ==============================================================
# INTERNAL: Xử lý Fall (IMU)
# ==============================================================
def _process_fall(samples: List[List[float]], db: Session) -> dict:
    result = {"status": "WAITING", "prob": 0.0}

    for s in samples:
        if len(s) == 6:
            result = update_fall_state(s)

    latest_fall_state.update({
        "status": result.get("status", "WAITING"),
        "prob": result.get("prob", 0.0),
        "timestamp": time.time(),
    })

    record = FallRecord(
        status=latest_fall_state["status"],
        probability=latest_fall_state["prob"],
    )
    db.add(record)
    db.commit()

    return {"status": latest_fall_state["status"], "prob": latest_fall_state["prob"]}


# ==============================================================
# HELPER: Build payload gửi FE
# ==============================================================
def _build_status_payload() -> dict:
    f_status = fall_state.get("status", "WAITING")
    f_prob = fall_state.get("prob", 0.0)
    alert = latest_hr_state["is_danger"] or f_status == "FALL"

    return {
        "hr": latest_hr_state["hr"],
        "hr_danger": latest_hr_state["is_danger"],
        "hr_message": latest_hr_state["rule_message"],
        "fall_status": f_status,
        "fall_prob": f_prob,
        "alert": alert,
    }


# ==============================================================
# RUN
# ==============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
