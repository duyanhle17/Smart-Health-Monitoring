import requests
import time

hrs = [
    72,73,71,74,75,
    76,78,77,79,80,
    82,84,83,85,87,
    90,92,95,98,100,
    103,106,110,115,120,
    125,130,135,140,145,
    148,150,147,145,142,
    138,135,132,128,125,
    122,118,115,112,108,
    105,102,98,95,92
]

URL = "http://127.0.0.1:8080/hr"

print("🚀 START HR TEST\n")

for i, hr in enumerate(hrs, start=1):
    r = requests.post(URL, json={"hr": hr})
    data = r.json()

    print(
        f"[{i:02d}] HR={hr:>3} | "
        f"RULE={data['rule_status']:<12} | "
        f"ML={data['ml_status']:<9} | "
        f"DANGER={data['is_danger']}"
    )

    time.sleep(1)   # giả lập ESP32 gửi mỗi 1s

print("\n✅ TEST FINISHED")
