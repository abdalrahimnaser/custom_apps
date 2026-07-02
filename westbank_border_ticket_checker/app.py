#!/usr/bin/env python3
"""Flask web app for the JETT VIP border ticket checker."""

from __future__ import annotations

import json
import os
from datetime import date

from flask import Flask, Response, jsonify, render_template, request

from checker_service import date_range, is_cloud_environment, monitor

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify(monitor.status())


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify(monitor.get_config().to_dict())

    data = request.get_json(silent=True) or {}
    try:
        start = date.fromisoformat(str(data.get("start_date", "")))
        end = date.fromisoformat(str(data.get("end_date", "")))
        date_range(start, end)
    except (TypeError, ValueError) as error:
        return jsonify({"error": f"نطاق التواريخ غير صالح: {error}"}), 400

    interval = data.get("interval_seconds", 300)
    try:
        interval = int(interval)
    except (TypeError, ValueError):
        return jsonify({"error": "يجب أن يكون الفاصل الزمني رقماً."}), 400
    if interval < 10:
        return jsonify({"error": "يجب أن يكون الفاصل الزمني 10 ثوانٍ على الأقل."}), 400

    updates = {
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "interval_seconds": interval,
        "notify_sound": bool(data.get("notify_sound", True)),
        "telegram_bot_token": str(data.get("telegram_bot_token", "")).strip(),
        "telegram_chat_id": str(data.get("telegram_chat_id", "")).strip(),
    }
    config = monitor.update_config(updates)
    return jsonify(config.to_dict())


@app.route("/api/scan", methods=["POST"])
def api_scan():
    try:
        monitor.scan_once()
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 409
    return jsonify({"ok": True})


@app.route("/api/monitor/start", methods=["POST"])
def api_monitor_start():
    monitor.start_monitoring()
    return jsonify({"ok": True, "status": monitor.status()})


@app.route("/api/monitor/stop", methods=["POST"])
def api_monitor_stop():
    monitor.stop_monitoring()
    return jsonify({"ok": True, "status": monitor.status()})


@app.route("/api/findings/clear", methods=["POST"])
def api_findings_clear():
    monitor.clear_findings()
    return jsonify({"ok": True, "findings": monitor.get_findings()})


@app.route("/api/findings")
def api_findings():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(monitor.get_findings(limit=limit))


@app.route("/api/logs")
def api_logs():
    since_id = request.args.get("since")
    return jsonify(monitor.get_logs(since_id=since_id))


@app.route("/api/scans")
def api_scans():
    limit = request.args.get("limit", 20, type=int)
    return jsonify(monitor.get_scan_history(limit=limit))


@app.route("/api/events")
def api_events():
    since_id = request.args.get("since")

    def stream():
        event = monitor.subscribe()
        try:
            if since_id is None:
                payload = {
                    "status": monitor.status(),
                    "logs": monitor.get_logs(),
                    "findings": monitor.get_findings(limit=20),
                }
                yield f"data: {json.dumps(payload)}\n\n"

            while True:
                if not event.wait(timeout=25):
                    yield ": keepalive\n\n"
                    continue
                event.clear()
                payload = {
                    "status": monitor.status(),
                    "logs": monitor.get_logs(since_id=since_id),
                    "findings": monitor.get_findings(limit=20),
                }
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            monitor.unsubscribe(event)

    return Response(stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    app.run(debug=not is_cloud_environment(), port=port, threaded=True, host="0.0.0.0")
