import sys
import time
import random
import requests
from backend.core.fall.fall_features import load_txt_file

HR_URL = "http://127.0.0.1:5000/hr"
FALL_URL = "http://127.0.0.1:5000/fall"

def main(fall_txt_path):
    print(f"🚀 Simulating HR + FALL from: {fall_txt_path}")

    data = load_txt_file(fall_txt_path)

    base_hr = 75  # nhịp tim nền
    hr = base_hr

    for i, row in enumerate(data):
        # -------------------
        # 1️⃣ SEND FALL DATA
        # -------------------
        requests.post(FALL_URL, json={
            "samples": [row.tolist()]
        })

        # -------------------
        # 2️⃣ SEND HR DATA
        # -------------------
        # HR tăng dần khi gần ngã
        if i > len(data) * 0.4:
            hr += random.randint(0, 2)
        else:
            hr += random.randint(-1, 1)

        hr = max(55, min(hr, 180))

        requests.post(HR_URL, json={
            "hr": hr
        })

        print(f"Sent HR={hr}, Acc/Gyro sample {i+1}")

        time.sleep(0.05)  # ~20Hz (chậm hơn fall)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m tools.simulate_hr_fall path/to/fall_file.txt")
        sys.exit(1)

    main(sys.argv[1])

    
    #python -m tools.simulate_hr_fall data/fall_raw/non_fall/case_001_machinery.txt
    
    #chạy thử với mã trên nhé
