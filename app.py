from flask import Flask, render_template, request, redirect, url_for, jsonify
import paho.mqtt.client as mqtt
import threading
import json

app = Flask(__name__)

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPICS = [
    ("chiller/status/temps", 0),
    ("chiller/status/pump", 0),
    ("chiller/status/chiller", 0),
    ("chiller/status/setpoint", 0),
    ("chiller/status/ahu_call", 0),
    ("chiller/status/manual_override_pump", 0),
    ("chiller/status/manual_override_chiller", 0),
    ("chiller/status/manual_override_ahu", 0)
]

mqtt_data = {
    "temps": {},
    "pump": "Unknown",
    "chiller": "Unknown",
    "setpoint": None,
    "ahu_call": "Unknown",
    "manual_override_pump": "Inactive",
    "manual_override_chiller": "Inactive",
    "manual_override_ahu": "Inactive"
}

mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT with result code {rc}")
    client.subscribe(MQTT_TOPICS)

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    print(f"[MQTT] {topic}: {payload}")

    if topic == "chiller/status/temps":
        try:
            mqtt_data["temps"] = json.loads(payload)
        except json.JSONDecodeError:
            mqtt_data["temps"] = {}
    elif topic == "chiller/status/pump":
        mqtt_data["pump"] = payload
    elif topic == "chiller/status/chiller":
        mqtt_data["chiller"] = payload
    elif topic == "chiller/status/setpoint":
        try:
            mqtt_data["setpoint"] = float(payload)
        except ValueError:
            mqtt_data["setpoint"] = None
    elif topic == "chiller/status/ahu_call":
        mqtt_data["ahu_call"] = payload
    elif topic == "chiller/status/manual_override_pump":
        mqtt_data["manual_override_pump"] = payload
    elif topic == "chiller/status/manual_override_chiller":
        mqtt_data["manual_override_chiller"] = payload
    elif topic == "chiller/status/manual_override_ahu":
        mqtt_data["manual_override_ahu"] = payload

def mqtt_loop():
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_forever()

mqtt_thread = threading.Thread(target=mqtt_loop)
mqtt_thread.daemon = True
mqtt_thread.start()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        pump_cmd = request.form.get("pump")
        chiller_cmd = request.form.get("chiller")
        setpoint_cmd = request.form.get("setpoint")
        ahu_call_cmd = request.form.get("ahu_call")

        if pump_cmd in ["on", "off", "clear"]:
            mqtt_client.publish("chiller/control/pump", pump_cmd)
        if chiller_cmd in ["on", "off", "clear"]:
            mqtt_client.publish("chiller/control/chiller", chiller_cmd)
        if setpoint_cmd:
            try:
                sp_val = float(setpoint_cmd)
                mqtt_client.publish("chiller/control/setpoint", str(sp_val))
            except ValueError:
                pass
        if ahu_call_cmd in ["on", "off", "clear"]:
            mqtt_client.publish("chiller/control/cooling", ahu_call_cmd)  # fixed topic name to "cooling"

        return redirect(url_for("index"))

    # Compute full chiller call for display
    ahu_active = mqtt_data["ahu_call"] == "Active"
    chiller_on = mqtt_data["chiller"] == "Chiller On"
    full_chiller_call = "Cooling On" if chiller_on and ahu_active else "Cooling Off"

    return render_template("index.html", data=mqtt_data, full_chiller_call=full_chiller_call)

@app.route("/data")
def data():
    ahu_active = mqtt_data["ahu_call"] == "Active"
    chiller_on = mqtt_data["chiller"] == "Chiller On"
    full_chiller_call = "Cooling On" if chiller_on and ahu_active else "Cooling Off"

    return jsonify({
        "temps": mqtt_data["temps"],
        "setpoint": mqtt_data["setpoint"],
        "pump": mqtt_data["pump"],
        "chiller": mqtt_data["chiller"],
        "ahu_call": mqtt_data["ahu_call"],
        "manual_override_pump": mqtt_data["manual_override_pump"],
        "manual_override_chiller": mqtt_data["manual_override_chiller"],
        "manual_override_ahu": mqtt_data["manual_override_ahu"],
        "full_chiller_call": full_chiller_call
    })

@app.route("/clear-overrides", methods=["POST"])
def clear_overrides():
    # Publish 'clear' command to each manual override topic to reset overrides
    mqtt_client.publish("chiller/control/pump", "clear")
    mqtt_client.publish("chiller/control/chiller", "clear")
    mqtt_client.publish("chiller/control/cooling", "clear")  # AHU call override uses 'cooling' topic in your existing code

    # Also update local state immediately (optional, since MQTT messages should update this soon)
    mqtt_data["manual_override_pump"] = None
    mqtt_data["manual_override_chiller"] = None
    mqtt_data["manual_override_ahu"] = None

    return ("", 204)  # HTTP 204 No Content means success with no body

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)