from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime
import sqlite3
import os

app = Flask(__name__)
CORS(app)

DATABASE_PATH = "museum.db"

VALID_ROOMS = ["room_A", "room_B"]
VALID_DIRECTIONS = ["enter", "exit"]


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS room_state (
            room TEXT PRIMARY KEY,
            count INTEGER NOT NULL,
            last_update TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            sensor_id TEXT,
            room TEXT NOT NULL,
            direction TEXT NOT NULL,
            detected INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            count_after INTEGER NOT NULL,
            is_error INTEGER NOT NULL DEFAULT 0,
            error_message TEXT
        )
    """)

    for room in VALID_ROOMS:
        cursor.execute("""
            INSERT OR IGNORE INTO room_state (room, count, last_update)
            VALUES (?, ?, ?)
        """, (room, 0, None))

    conn.commit()
    conn.close()


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Museum IoT Flask backend is running",
        "dashboard": "/dashboard",
        "state_api": "/api/state",
        "events_api": "/api/events"
    })


@app.route("/dashboard", methods=["GET"])
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/presence", methods=["POST"])
def receive_presence_event():
    data = request.get_json()

    if data is None:
        return jsonify({
            "error": "Missing JSON body"
        }), 400

    device_id = data.get("device_id", "unknown_device")
    sensor_id = data.get("sensor_id", "unknown_sensor")
    room = data.get("room")
    direction = data.get("direction")
    detected = data.get("detected", True)

    if room not in VALID_ROOMS:
        return jsonify({
            "error": "Invalid room. Use room_A or room_B."
        }), 400

    if direction not in VALID_DIRECTIONS:
        return jsonify({
            "error": "Invalid direction. Use enter or exit."
        }), 400

    if not isinstance(detected, bool):
        return jsonify({
            "error": "detected must be true or false."
        }), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT count FROM room_state WHERE room = ?", (room,))
    current_count = cursor.fetchone()["count"]

    is_error = False
    error_message = None

    if detected:
        if direction == "enter":
            new_count = current_count + 1

        elif direction == "exit":
            if current_count == 0:
                new_count = 0
                is_error = True
                error_message = "Exit detected while room count is already 0"
            else:
                new_count = current_count - 1
    else:
        new_count = current_count

    timestamp = datetime.now().isoformat(timespec="seconds")

    cursor.execute("""
        UPDATE room_state
        SET count = ?, last_update = ?
        WHERE room = ?
    """, (new_count, timestamp, room))

    cursor.execute("""
        INSERT INTO events (
            device_id, sensor_id, room, direction, detected,
            timestamp, count_after, is_error, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        device_id,
        sensor_id,
        room,
        direction,
        1 if detected else 0,
        timestamp,
        new_count,
        1 if is_error else 0,
        error_message
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "message": "Presence event received",
        "event": {
            "device_id": device_id,
            "sensor_id": sensor_id,
            "room": room,
            "direction": direction,
            "detected": detected,
            "timestamp": timestamp,
            "count_after": new_count,
            "is_error": is_error,
            "error_message": error_message
        }
    }), 200


@app.route("/api/state", methods=["GET"])
def get_state():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT room, count, last_update FROM room_state")
    rows = cursor.fetchall()

    conn.close()

    state = {}
    for row in rows:
        state[row["room"]] = {
            "count": row["count"],
            "last_update": row["last_update"]
        }

    return jsonify(state)


@app.route("/api/events", methods=["GET"])
def get_events():
    limit = request.args.get("limit", default=20, type=int)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, device_id, sensor_id, room, direction, detected,
            timestamp, count_after, is_error, error_message
        FROM events
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    events = []
    for row in rows:
        events.append({
            "id": row["id"],
            "device_id": row["device_id"],
            "sensor_id": row["sensor_id"],
            "room": row["room"],
            "direction": row["direction"],
            "detected": bool(row["detected"]),
            "timestamp": row["timestamp"],
            "count_after": row["count_after"],
            "is_error": bool(row["is_error"]),
            "error_message": row["error_message"]
        })

    return jsonify(events)


@app.route("/api/reset", methods=["POST"])
def reset_counts():
    conn = get_db_connection()
    cursor = conn.cursor()

    timestamp = datetime.now().isoformat(timespec="seconds")

    for room in VALID_ROOMS:
        cursor.execute("""
            UPDATE room_state
            SET count = 0, last_update = ?
            WHERE room = ?
        """, (timestamp, room))

    conn.commit()
    conn.close()

    return jsonify({
        "message": "Room counts reset to zero"
    })


if __name__ == "__main__":
    init_database()

    # host="0.0.0.0" is important so the ESP8266 can reach the Flask server
    app.run(debug=True, host="0.0.0.0", port=5000)