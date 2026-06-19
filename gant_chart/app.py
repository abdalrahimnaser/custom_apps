from datetime import date, timedelta
from pathlib import Path
import json
import uuid

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")

DATA_DIR = Path(__file__).parent / "data"
DATA_FILE = DATA_DIR / "tasks.json"

COLORS = ["#4f86f7", "#22a06b", "#e5484d", "#f5a623", "#9b59b6", "#1abc9c"]


def sample_tasks():
    today = date.today()
    return [
        {"id": str(uuid.uuid4()), "name": "Planning", "start": today.isoformat(), "end": (today + timedelta(days=6)).isoformat(), "color": COLORS[0]},
        {"id": str(uuid.uuid4()), "name": "Design", "start": (today + timedelta(days=5)).isoformat(), "end": (today + timedelta(days=14)).isoformat(), "color": COLORS[1]},
        {"id": str(uuid.uuid4()), "name": "Build", "start": (today + timedelta(days=12)).isoformat(), "end": (today + timedelta(days=28)).isoformat(), "color": COLORS[2]},
        {"id": str(uuid.uuid4()), "name": "Review", "start": (today + timedelta(days=26)).isoformat(), "end": (today + timedelta(days=32)).isoformat(), "color": COLORS[3]},
    ]


def load_tasks():
    if DATA_FILE.exists():
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    tasks = sample_tasks()
    save_tasks(tasks)
    return tasks


def save_tasks(tasks):
    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2)


def validate_task(task):
    required = {"id", "name", "start", "end", "color"}
    if not required.issubset(task.keys()):
        return False
    if not isinstance(task.get("description", ""), str):
        return False
    if not task["name"].strip():
        return False
    if task["start"] > task["end"]:
        return False
    return True


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/tasks")
def get_tasks():
    return jsonify(load_tasks())


@app.put("/api/tasks")
def put_tasks():
    tasks = request.get_json(silent=True)
    if not isinstance(tasks, list):
        return jsonify({"error": "Expected a list of tasks"}), 400
    if not all(isinstance(t, dict) and validate_task(t) for t in tasks):
        return jsonify({"error": "Invalid task data"}), 400
    save_tasks(tasks)
    return jsonify(tasks)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
