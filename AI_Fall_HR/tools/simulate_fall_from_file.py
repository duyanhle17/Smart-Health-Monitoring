import sys
import time
import requests
from src.fall.fall_features import load_txt_file

URL = "http://127.0.0.1:8080/fall"

def main(path):
    print(f"📤 Sending fall data from: {path}")
    data = load_txt_file(path)

    for row in data:
        requests.post(URL, json={
            "samples": [row.tolist()]
        })
        time.sleep(0.005)  # ~200Hz

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/simulate_fall_from_file.py path/to/file.txt")
        sys.exit(1)

    main(sys.argv[1])
    print("\n✅ Simulation finished.")