import serial
import serial.tools.list_ports
import json
import time
import requests
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.core.fall.fall_state import update_fall_state

SERVER_URL = "http://127.0.0.1:5000/api/device_telemetry"
WORKER_ID = "W1"

def find_esp32_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "CH340" in port.description or "CP210" in port.description or "USB" in port.description:
            return port.device
    if len(ports) > 0:
        return ports[0].device
    return None

def main():
    port = find_esp32_port()
    if not port:
        print("? Không tìm th?y c?ng COM nào c?m m?ch ESP32!")
        print("Vui lòng c?m cáp USB và cài Driver CH340/CP210 n?u c?n.")
        return

    print(f"?? Ðang k?t n?i t?i m?ch t?i c?ng: {port} ...")
    try:
        ser = serial.Serial(port, 115200, timeout=1)
    except Exception as e:
        print(f"? L?i m? c?ng {port}: {e}")
        return

    print("? K?t n?i thành công! Ðang d?i d? li?u...")

    # Tr?ng thái gi? l?p ToF
    current_x = 10.0
    current_y = 50.0
    direction = 1 # 1: di t?i, -1: di lui

    # Luu t?m giá tr? d? mix vào json
    last_hr = 75.0
    last_gas = 0.0 # M?ch ông b?n chua có c?m bi?n MQ4, ta mock cái này thành an toàn 2.5
    last_fall_status = "SAFE"

    # Luu IMU
    ax, ay, az, gx, gy, gz = 0, 1.0, 0, 0, 0, 0

    last_post_time = time.time()

    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "hr":
                        last_hr = float(data.get("bpm", last_hr))
                        print(f"?? Nh?p tim: {last_hr} bpm")
                    elif data.get("type") == "imu":
                        ax = data.get("ax", 0)
                        ay = data.get("ay", 0)
                        az = data.get("az", 0)
                        gx = data.get("gx", 0)
                        gy = data.get("gy", 0)
                        gz = data.get("gz", 0)
                        
                        # Ch?y mô hình ngã
                        fall_res = update_fall_state([ax, ay, az, gx, gy, gz])
                        status = fall_res.get("status", "SAFE")
                        if status == "FALL":
                            last_fall_status = "FALL"
                        elif status == "RECOVERED" or status == "SAFE":
                            last_fall_status = "SAFE"
                except json.JSONDecodeError:
                    pass

            # X? lý c?p nh?t x, y gi? l?p
            current_x += direction * 0.1 # Nhanh/ch?m di b?
            if current_x > 90.0:
                direction = -1
            elif current_x < 10.0:
                direction = 1

            # Khí gas mock ng?u nhiên loanh quanh 2.0 - 5.0
            import random
            last_gas = round(2.0 + random.random() * 3.0, 2)

            # G?i lên API t?i da 2 l?n / giây (0.5s)
            now = time.time()
            if now - last_post_time > 0.5:
                payload = {
                    "worker_id": WORKER_ID,
                    "telemetry": {
                        "x": current_x,
                        "y": current_y,
                        "hr": last_hr,
                        "gas": last_gas,
                        "ax": ax, "ay": ay, "az": az,
                        "gx": gx, "gy": gy, "gz": gz,
                        "fall_alert": last_fall_status
                    }
                }
                requests.post(SERVER_URL, json=payload, timeout=1)
                last_post_time = now

        except KeyboardInterrupt:
            print("?? D?ng d?c m?ch.")
            break
        except Exception as e:
            pass

if __name__ == "__main__":
    main()
