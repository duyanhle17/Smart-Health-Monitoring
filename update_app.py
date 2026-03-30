import os

with open('backend/app.py', 'r') as f:
    content = f.read()

content = content.replace("from flask import Flask, request, jsonify, render_template", "from flask import Flask, request, jsonify, render_template\nfrom flask_socketio import SocketIO\nfrom flask_sqlalchemy import SQLAlchemy")

content = content.replace("app = Flask(__name__)\nCORS(app)", """app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

class Personnel(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    zone = db.Column(db.String(50), nullable=True)

with app.app_context():
    db.create_all()
    # Mock data if empty
    if not Personnel.query.first():
        db.session.add(Personnel(id='WK_102', name='A. Chen', zone='GAMMA_STAGE'))
        db.session.add(Personnel(id='WK_048', name='J. Vance', zone='ALPHA_LEFT'))
        db.session.add(Personnel(id='WK_089', name='M. Johnson', zone='BETA_RIGHT'))
        db.session.add(Personnel(id='WK_004', name='E. Davis', zone='CENTER_PATH'))
        db.session.commit()
""")

content = content.replace("return jsonify({\"status\": \"ACK\"})", """
    socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones})
    return jsonify({"status": "ACK"})""")

content = content.replace("return jsonify({\"status\": \"ACK\", \"zone\": zone_id})", """
        socketio.emit('latest_status', {"workers": list(workers.values()), "zones": zones})
        return jsonify({"status": "ACK", "zone": zone_id})""")

content = content.replace("app.run(host=\"0.0.0.0\", port=5000)", "socketio.run(app, host=\"0.0.0.0\", port=int(os.environ.get('PORT', 5000)), allow_unsafe_werkzeug=True)")

content += """
@app.route("/api/personnel", methods=["GET"])
def get_personnel():
    people = Personnel.query.all()
    return jsonify([{'id': p.id, 'name': p.name, 'zone': p.zone} for p in people])
"""

with open('backend/app.py', 'w') as f:
    f.write(content)
