# server.py
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "Server is running"

@app.route("/data", methods=["POST"])
def receive_data():
    data = request.json
    print("HR nhận được:", data)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
