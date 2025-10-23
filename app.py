from flask import Flask, render_template, jsonify
from gpiozero import DistanceSensor
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageDraw, ImageFont
import statistics
import time
import signal
import sys
import atexit

app = Flask(__name__)

# --- Safe hardware setup ---
def init_hardware():
    """Safely initialize GPIO and OLED display."""
    global sensor, oled, font

    try:
        # Ultrasonic sensor
        sensor = DistanceSensor(echo=24, trigger=23, max_distance=2)
        print("Ultrasonic sensor initialized successfully.")
    except Exception as e:
        print(f"Warning: Sensor init failed — {e}")

    try:
        # OLED setup
        serial = i2c(port=1, address=0x3C)
        oled = ssd1306(serial)
        font = ImageFont.load_default()
        print("OLED initialized successfully.")
    except Exception as e:
        print(f"Warning: OLED init failed — {e}")

# Initialize at startup
init_hardware()


def show_on_oled(line1, line2=""):
    """Display text on OLED."""
    try:
        with Image.new("1", oled.size) as image:
            draw = ImageDraw.Draw(image)
            draw.text((5, 10), line1, font=font, fill=255)
            draw.text((5, 30), line2, font=font, fill=255)
            oled.display(image)
    except Exception as e:
        print(f"OLED display error: {e}")


# --- Helper functions ---
def get_distance():
    distance_cm = round(sensor.distance * 100, 2)
    print(f"Measured Distance: {distance_cm} cm")
    show_on_oled("Distance:", f"{distance_cm} cm")
    return distance_cm


def detect_shape():
    distances = []
    for _ in range(5):
        dist = round(sensor.distance * 100, 2)
        distances.append(dist)
        time.sleep(0.5)

    avg = round(statistics.mean(distances), 2)
    variation = round(statistics.pstdev(distances), 2)

    if variation < 0.5:
        shape = "Flat Surface"
    elif variation < 2:
        shape = "Curved Surface"
    else:
        shape = "Irregular Surface"

    show_on_oled("Shape:", shape)
    print(f"Distances: {distances} | Shape: {shape}")
    return {"distances": distances, "average": avg, "variation": variation, "shape": shape}


# --- Cleanup before exit ---
def cleanup_hardware(*args):
    """Ensure clean GPIO and OLED shutdown."""
    print("\nCleaning up GPIO and OLED...")
    try:
        show_on_oled("Shutting down", "")
        sensor.close()
    except Exception as e:
        print(f"Cleanup error: {e}")
    sys.exit(0)


# Register cleanup on exit or interrupt
atexit.register(cleanup_hardware)
signal.signal(signal.SIGINT, cleanup_hardware)
signal.signal(signal.SIGTERM, cleanup_hardware)


# --- Flask routes ---
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/measure")
def measure():
    distance = get_distance()
    return jsonify({"distance": distance})


@app.route("/check_shape")
def check_shape():
    result = detect_shape()
    return jsonify(result)


# --- Run Flask safely ---
if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    except KeyboardInterrupt:
        cleanup_hardware()

