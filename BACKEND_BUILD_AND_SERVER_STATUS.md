# SafeWork Backend Build Guide & Server Status

Cap nhat: 2026-07-25
Server: `500310048-GPU-01`  
Domain kiem tra: `https://safework.ctslab.net`

Tai lieu nay ghi lai cach backend dang duoc build/deploy tren server hien tai,
cach rebuild an toan, va nhung diem can chu y khi noi firmware ESP32-S3/DWM3000
vao backend.

> Phan lich su ben duoi giu lai de truy vet deployment cu. Muc 0 la quy trinh
> hien hanh cho he 2 anchor + 1 worker, thay the cac mo ta cu ve single/three
> anchor trong tai lieu nay.

## 0. Quy trinh hien hanh: 2 anchor UWB + BNO08x (2-D co rang buoc)

He nay chi co hai khoang cach `d1`, `d2`, nen phan mem khong duoc tu nhan la
toa do 2-D khi worker nam tren duong noi anchor. Backend chi bat `UWB_2D_FUSION`
khi khu vuc lam viec nam hoan toan mot phia duong A1->A2; `WORK_AREA_POINT`
chon phia do. `UWB_LINE_FALLBACK=true` va `UWB_2D_FUSION=true` la xung dot va
backend se tu choi fix thay vi chuyen thanh toa do gia.

### Deploy an toan

1. Do `ANCHOR_BASELINE_M` giua tam pha antenna, khong do giua PCB. Voi lap dat
   hien tai gia tri nay la `2.00` m.
2. Dat ba antenna cung do cao. Neu khong the, khai bao
   `UWB_D1_HEIGHT_DELTA_M` / `UWB_D2_HEIGHT_DELTA_M` (cao anchor tru cao tag,
   met). DW3000 do range xien; backend tu chuyen thanh range ngang cho map.
3. De `UWB_LINE_FALLBACK=false`, `UWB_2D_FUSION=false`, `UWB_CALIBRATED=false`
   trong luc chua calibration. Firmware moi gui `range_seq`, `range_age_ms`,
   `range_epoch`, `range_trusted`; fusion production yeu cau range pair moi va
   dong bo, khong tai su dung HTTP packet cu.
4. Tai mot diem da do bang thuoc, giu worker **dung yen**. Gia tri
   `known_d1_m`, `known_d2_m` la slant distance da tinh ca chenh cao:
   `sqrt(horizontal^2 + height_delta^2)`. Bat capture (chi doc raw range,
   khong tu ghi offset):

   ```bash
   curl -X POST http://127.0.0.1:6868/api/uwb/calibration/start \
     -H 'Content-Type: application/json' \
     -d '{"worker_id":"WK_102","known_d1_m":1.0,"known_d2_m":1.0}'
   curl http://127.0.0.1:6868/api/uwb/calibration/WK_102
   ```

   Capture can 80 mau dung yen; no reject mau BNO dang quay/di chuyen, range
   stale/duplicate va chi tra `recommended_offsets_m`. Khong co endpoint nao
   tu ap offset.
5. Kiem tra offset o it nhat ba diem off-line, sau do thay the (khong cong don)
   `UWB_D1_OFFSET_M`, `UWB_D2_OFFSET_M`, dat `UWB_CALIBRATED=true` neu residual
   dat yeu cau. Boi la hai anchor, hay uu tien vung co giao cat hai vong tron
   60-120 do va cach baseline it nhat khoang 1 m khi baseline 2 m.
6. Chi luc do dat `UWB_2D_FUSION=true` va rebuild. EKF cap nhat truc tiep cap
   range, gate NLOS/innovation, giu dung mot phia anchor, ZUPT khi BNO bao dung
   yen, va khong bao gio publish toa do chi tu IMU. `UWB_IMU_FUSION` /
   `IMU_ACCEL_FRAME_CALIBRATED` van de `false` cho den khi da commission day du
   huong/mount BNO08x; BNO van duoc dung de giam jitter va phat hien quay.

Build/restart:

```bash
cd /home/namnx/NamBuw/SafeWork/Smart-Health-Monitoring
git pull --ff-only origin main
docker compose -p safework -f docker-compose.deploy.yml up -d --build backend frontend
curl http://127.0.0.1:6868/api/health
```

## 1. Repo va branch

Thu muc `/home/namnx/NamBuw/SafeWork` khong phai git repo. Git repo that su la:

```bash
cd /home/namnx/NamBuw/SafeWork/Smart-Health-Monitoring
```

Remote:

```text
origin https://github.com/duyanhle17/Smart-Health-Monitoring
```

Trang thai luc kiem tra ban dau, truoc khi push tai lieu nay:

- Local branch: `main`
- Local HEAD: `50d201984356055e5826a51d5613596550333f67`
- `origin/main`: `642d55ced51b7ff54696e86dc31aa14e71d48101`
- Local dang behind `origin/main` 2 commit.
- Co file untracked: `P_innovation_25_26.md`
- Da clone ban fresh de doi chieu tai `/tmp/safework-fresh-clone-20260724`.

Quan trong: container dang chay khop checksum voi local working tree tai thoi
diem kiem tra ban dau, nhung chua chay code moi nhat tren `origin/main`. Neu sau
do repository duoc pull/push them commit, container van khong tu doi cho den khi
chay lai `docker compose ... up -d --build`.

## 2. Ket luan deploy hien tai

Luot public hien tai:

```text
Browser
  -> Cloudflare DNS / Cloudflare Tunnel
  -> cloudflared tren server nay
  -> localhost:6868
  -> Docker container safework_frontend:5173
  -> Vite dev server proxy /api, /latest_status, /socket.io
  -> Docker container safework_backend:5000
```

Bang chung da kiem tra:

- `safework.ctslab.net` resolve ve Cloudflare IP, khong tro truc tiep ve public IP server.
- Request HTTPS toi domain lam tang counter cua `cloudflared` metrics port `20245`.
- Local nginx host khong co config `safework.ctslab.net`.
- Port host `6868` dang publish vao container frontend.
- Backend khong publish port ra host trong file deploy; backend chi nam trong Docker network.

Nghia la neu ESP32 o cung LAN muon gui vao deployment hien tai, URL de POST nen la:

```text
http://<server-lan-ip>:6868/api/device_telemetry
```

hoac qua public domain:

```text
https://safework.ctslab.net/api/device_telemetry
```

Khong dung `http://<server-lan-ip>:5000/...` cho deploy hien tai, vi backend port
`5000` khong duoc map ra host trong `docker-compose.deploy.yml`.

## 3. Docker services dang chay

Kiem tra dung project name:

```bash
docker compose -p safework -f docker-compose.deploy.yml ps
```

Ket qua luc kiem tra:

```text
safework_backend    Up 3 weeks   5000/tcp
safework_frontend   Up 3 weeks   0.0.0.0:6868->5173/tcp
safework_simulator  Up 3 weeks
```

Luu y nho nhung de nham: neu chay thieu `-p safework`, lenh `docker compose -f
docker-compose.deploy.yml ps` co the hien bang trong, du container van dang chay.

Image dang chay:

```text
safework-backend   created 2026-06-29T19:06:36Z
safework-frontend  created 2026-06-29T19:06:36Z
safework-simulator created 2026-06-29T18:48:11Z
```

## 4. Deploy file hien tai

File deploy: `docker-compose.deploy.yml`

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: safework_backend
    environment:
      - PORT=5000
      - DATABASE_URL=sqlite:////app/data/local.db
    volumes:
      - safework_db:/app/data
    expose:
      - "5000"

  simulator:
    build:
      context: .
      dockerfile: backend/Dockerfile.simulator
    container_name: safework_simulator
    environment:
      - BACKEND_URL=http://backend:5000

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: safework_frontend
    ports:
      - "6868:5173"
    environment:
      - VITE_BACKEND_URL=http://backend:5000
```

Frontend Dockerfile dang chay `npm run dev -- --host 0.0.0.0`, nen public site
hien tra HTML co React Refresh/Vite dev client. Day la demo deployment, chua phai
static production build.

## 5. Backend thuc te duoc deploy

Backend deploy la Flask + Flask-SocketIO trong:

```text
backend/app.py
```

Khong phai `main.py`. File `main.py` la FastAPI cu/thu nghiem va khong duoc
Dockerfile deploy goi.

Backend Dockerfile:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
ENV PYTHONPATH=/app
CMD ["python", "backend/app.py"]
```

Database:

- SQLite URL: `sqlite:////app/data/local.db`
- Docker volume: `safework_safework_db`
- File trong container: `/app/data/local.db`

Log can chu y:

- Code tao `DATA_DIR = backend/data`, nen `hardware_telemetry.log` hien nam o
  `/app/backend/data/hardware_telemetry.log`, khong nam trong volume `/app/data`.
- File log nay dang 0 byte luc kiem tra, nghia la chua thay luong hardware that
  ghi log gan day. Simulator van dang tao du lieu realtime.
- Neu muon log hardware persist qua rebuild, nen sua backend de ghi vao `/app/data`.

## 6. API backend can dung

Khong co endpoint `/api/health` trong backend hien tai. `/api/health` tra 404.
Dung cac endpoint sau de health check:

```bash
curl http://127.0.0.1:6868/latest_status
curl http://127.0.0.1:6868/api/personnel
curl http://127.0.0.1:6868/api/anchors
curl "http://127.0.0.1:6868/socket.io/?EIO=4&transport=polling"
```

Endpoint chinh cho thiet bi:

```http
POST /api/device_telemetry
Content-Type: application/json
```

Payload backend local/deployed `50d2019` dang doc:

```json
{
  "worker_id": "WK_102",
  "telemetry": {
    "hr": 82,
    "temp": 36.8,
    "ch4": 0.4,
    "co": 5.0,
    "d1": 12.4,
    "d2": 20.1,
    "d3": 18.0,
    "yaw": 0,
    "ax": 0.0,
    "ay": 0.0,
    "az": 9.8,
    "gx": 0.0,
    "gy": 0.0,
    "gz": 0.0,
    "fall_alert": "SAFE"
  }
}
```

Behavior hien tai:

- Neu `telemetry.d1` ton tai, backend tinh toa do bang single-anchor:
  `d1 + yaw`. `d2/d3` van duoc parse nhung khong thuc su dung trong
  `position_engine.py` local.
- Neu khong co `d1`, backend lay `telemetry.x` va `telemetry.y`.
- `fall_alert == "DANGER"` se bien thanh `fall_status = "FALL"`.
- ML fall model co trong repo, nhung endpoint hien tai tin truc tiep
  `fall_alert`; ham `update_fall_state` khong duoc goi trong route nay.
- Backend emit Socket.IO event `latest_status` cho frontend.

Endpoint cho anchor moi truong:

```http
POST /api/anchor_telemetry
```

Payload:

```json
{
  "anchor_id": "ANC_STAGE",
  "telemetry": {
    "ch4": 0.5,
    "co": 6.0
  }
}
```

Frontend doc:

- `GET /api/anchors`
- Socket.IO path `/socket.io`
- event `latest_status`
- `/latest_status` la fallback/polling endpoint.

## 7. Cach build va chay backend

### Chay deploy hien tai tren server

```bash
cd /home/namnx/NamBuw/SafeWork/Smart-Health-Monitoring
docker compose -p safework -f docker-compose.deploy.yml up -d --build backend frontend
```

Neu can du lieu simulator:

```bash
docker compose -p safework -f docker-compose.deploy.yml up -d --build simulator
```

Neu dang test voi phan cung that, nen tat simulator de tranh du lieu gia chen
vao dashboard:

```bash
docker compose -p safework -f docker-compose.deploy.yml stop simulator
```

Xem log:

```bash
docker compose -p safework -f docker-compose.deploy.yml logs -f backend
docker compose -p safework -f docker-compose.deploy.yml logs -f frontend
docker compose -p safework -f docker-compose.deploy.yml logs -f simulator
```

Restart nhanh khong rebuild:

```bash
docker compose -p safework -f docker-compose.deploy.yml restart backend frontend
```

### Chay backend local khong Docker

```bash
cd /home/namnx/NamBuw/SafeWork/Smart-Health-Monitoring
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=sqlite:///local.db PORT=5000 python backend/app.py
```

Sau do test:

```bash
curl http://127.0.0.1:5000/latest_status
curl http://127.0.0.1:5000/api/personnel
```

### Chay full local dev compose

File `docker-compose.yml` la ban dev co MySQL va map backend ra port `5000`.
No khac voi deploy public:

```bash
docker compose up -d --build db backend frontend
```

Dung ban nay khi can ESP32 goi truc tiep `http://<host-ip>:5000/...`.

## 8. Firmware folder doc nhanh

Thu muc chinh:

```text
firmware/
  platformio.ini
  src/config.h
  src/main.cpp
  src/uwb.cpp
  src/uwb.h
  src/HeartRate.cpp
  src/HeartRate.h
  lib/Dw3000/
  test_dw3000/
  problem.md
```

Y tuong firmware local `50d2019`:

- Mot codebase co role theo PlatformIO env:
  - `env:tag`: worker node, UWB initiator + BNO08x + MAX30102 + WiFi HTTP POST.
  - `env:anchor1/2/3`: anchor responder UWB.
- Hardware local README ghi: ESP32-S3 + DWM3000 + BNO08x + MAX30102.
- MAX30102 dang tra heart-rate va chip temperature; chua co body temperature that.
- Chua co gas sensor trong build firmware hien tai; `ch4/co` dang gui `0`.
- UWB dung Single-Sided Two-Way Ranging theo Makerfabs/Qorvo DW3000 example.

Build/flash theo local README:

```bash
cd firmware
pio run -e anchor1 -t upload
pio run -e anchor2 -t upload
pio run -e anchor3 -t upload
pio run -e tag -t upload
pio device monitor
```

Can sua truoc khi flash:

```text
firmware/src/config.h
  WORKER_ID
  WIFI_SSID
  WIFI_PASS
  BACKEND_URL
```

Voi server deploy hien tai, `BACKEND_URL` nen tro qua frontend proxy:

```c
#define BACKEND_URL "http://<server-lan-ip>:6868/api/device_telemetry"
```

hoac public HTTPS neu firmware TLS/cert da on:

```c
#define BACKEND_URL "https://safework.ctslab.net/api/device_telemetry"
```

## 9. Firmware/backend mismatch can xu ly

Day la phan quan trong nhat neu can demo voi hardware that.

### 9.1 Payload distance dang lech nhau

Firmware local `50d2019` dang tao payload:

```json
{
  "worker_id": "WK_102",
  "telemetry": {
    "hr": 82,
    "temp": 30.1,
    "spo2": 0,
    "ch4": 0,
    "co": 0,
    "yaw": 143.2,
    "steps": 51,
    "acc": 1.03
  },
  "distances": {
    "ANC_STAGE": 12.4,
    "ANC_LEFT": 30.1,
    "ANC_RIGHT": 35.7
  }
}
```

Backend local/deployed lai chi doc `telemetry.d1/d2/d3`, khong doc object
`distances`. Neu flash firmware y nguyen local `50d2019`, UWB distance se khong
cap nhat vi tri tren backend.

Co 2 cach sua:

1. Sua firmware local de gui flat key trong `telemetry`:

```json
{
  "worker_id": "WK_102",
  "telemetry": {
    "hr": 82,
    "temp": 30.1,
    "ch4": 0,
    "co": 0,
    "yaw": 143.2,
    "d1": 12.4,
    "d2": 30.1,
    "d3": 35.7
  }
}
```

2. Hoac pull `origin/main` moi nhat va rebuild backend + flash firmware cung
mot commit. `origin/main` da co commit `2fe1edf feat: add two-anchor UWB telemetry
support`, trong do firmware gui `d1/d2` flat va backend tinh vi tri 2-anchor.

Khuyen nghi: dung cach 2 cho demo UWB, nhung phai rebuild server:

```bash
git pull --ff-only origin main
docker compose -p safework -f docker-compose.deploy.yml up -d --build backend frontend
```

Sau do flash firmware tu cung commit.

### 9.2 Pin/SPI DWM3000 dang co lich su debug mau thuan

Local `firmware/problem.md` ghi log debug cu: doc DEV_ID on voi
`SCK=11, MOSI=9, MISO=12, CS=10`, va de nghi doi code tu `12/11/13` sang
`11/9/12`.

Nhung `origin/main` moi hon da sua tai lieu/test theo huong nguoc lai: dung FSPI
IOMUX cua ESP32-S3:

```text
SCK=12, MOSI=11, MISO=13, CS=10, RST=17, IRQ=18
```

va ha DW3000 SPI speed xuong 2 MHz trong driver. Vi vay khong nen chi doc
`problem.md` local roi sua tay. Nen chot 1 commit firmware duy nhat, flash ca
tag/anchor theo commit do, va test bang `firmware/test_dw3000` truoc.

Test toi thieu:

```bash
cd firmware/test_dw3000
pio run -e check -t upload
pio device monitor
```

Expected DEV_ID:

```text
0xDECA0302
```

Neu UWB init fail:

- DWM3000 chi cap 3.3V, khong cap 5V/VIN.
- Day SPI that ngan, uu tien < 5 cm.
- Dung cung pin set trong `config.h` va `platformio.ini`.
- Neu dung local `50d2019`, driver van de `_fastSPI = 8000000L`; problem.md
  khuyen ha ve 2 MHz. `origin/main` da co thay doi nay.

## 10. Tinh trang server hien tai

Tom tat thuc te luc kiem tra:

- Public site dang online tai `https://safework.ctslab.net`.
- Root tra HTML Vite dev server, title `SafeWork`.
- `/latest_status`, `/api/personnel`, `/api/anchors`, `/api/scenario` tra OK.
- `/api/health` tra 404 vi backend khong co route nay.
- Simulator dang day du lieu realtime, nen dashboard co worker/gas/HR gia lap.
- Chua co bang chung hardware real dang day log gan day: `hardware_telemetry.log`
  trong container dang 0 byte.
- Cloudflare Tunnel la duong public; nginx tren host khong phuc vu domain nay.
- Backend dang dung SQLite trong Docker volume, khong dung MySQL cho deploy.
- Tai thoi diem kiem tra ban dau, local source dang sau `origin/main` 2 commit.
  Neu muon dung firmware UWB moi tren server dang chay, can pull va rebuild dong
  bo container, khong chi push code len GitHub.

## 11. Checklist deploy an toan tiep theo

1. Chon target code:
   - Giu local `50d2019` neu chi can dashboard/simulator hien tai.
   - Pull `origin/main` neu can UWB 2-anchor va firmware contract moi.
2. Neu test hardware that, stop simulator truoc.
3. Chot `BACKEND_URL` trong firmware theo deploy thuc te:
   - `http://<server-lan-ip>:6868/api/device_telemetry` cho LAN.
   - Hoac public HTTPS neu firmware TLS on.
4. Dam bao firmware gui dung payload backend dang doc (`telemetry.d1/d2/d3` voi
   local deploy, hoac `d1/d2` voi `origin/main`).
5. Rebuild backend/frontend sau moi lan pull code.
6. Test endpoints `/latest_status`, `/api/personnel`, `/api/anchors`.
7. Test Socket.IO bang frontend hoac polling handshake.
8. Theo doi log backend va xac nhan co hardware telemetry real.
