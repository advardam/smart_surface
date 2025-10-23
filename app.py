#!/usr/bin/env python3
"""
app.py - Smart Surface & Shape Detector Flask backend

Routes:
 - /dashboard        -> UI
 - /measure          -> single distance + temp + color read (buzz)
 - /check_shape      -> take 5 distance reads, analyze shape, return readings (buzz)

Notes:
 - Attempts to import Adafruit sensor libs; if not present, returns placeholder values.
 - Uses gpiozero DistanceSensor and Buzzer when available.
 - Uses luma SSD1306 for OLED display if available.
 - Disables Flask reloader to avoid "GPIO busy" issues.
"""

import time
import statistics
import socket
import sys
import atexit
import signal

from flask import Flask, render_template, jsonify
import RPi.GPIO as GPIO

# gpiozero (for DistanceSensor and Buzzer)
try:
    from gpiozero import DistanceSensor, Buzzer
    GPIOZERO_AVAILABLE = True
except Exception:
    GPIOZERO_AVAILABLE = False

# OLED (luma) and PIL
try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    from PIL import Image, ImageDraw, ImageFont
    LUMA_AVAILABLE = True
except Exception:
    LUMA_AVAILABLE = False

# Optional Adafruit libraries for TCS34725 & MLX90614
# If not installed, we provide safe fallbacks that return None or placeholder values.
try:
    import board
    import busio
    # tcs34725 (Adafruit)
    try:
        import adafruit_tcs34725
        TCS_AVAILABLE = True
    except Exception:
        TCS_AVAILABLE = False

    # mlx90614 (Adafruit) - usually via adafruit_mlx90614 or simple smbus
    try:
        import adafruit_mlx90614
        MLX_AVAILABLE = True
    except Exception:
        MLX_AVAILABLE = False
except Exception:
    TCS_AVAILABLE = False
    MLX_AVAILABLE = False

app = Flask(__name__)

# ---------------------------
# Configurable pins & params
# ---------------------------
TRIGGER_PIN = 23
ECHO_PIN = 24
BUZZER_PIN = 17
OLED_I2C_ADDR = 0x3C
I2C_PORT = 1

# Globals
sensor = None
buzzer = None
oled = None
font = None
i2c_bus = None
tcs = None
mlx = None

# ---------------------------
# Utility helpers
# ---------------------------
def get_local_ip():
    """Return the Pi's local IP address (best effort)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # doesn't need to be reachable
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# ---------------------------
# Initialization
# ---------------------------
def init_hardware():
    """Initialize sensors, OLED and buzzer safely. Call at startup and on-demand."""
    global sensor, buzzer, oled, font, i2c_bus, tcs, mlx

    # cleanup prior state first
    try:
        GPIO.cleanup()
    except Exception:
        pass

    # init gpiozero DistanceSensor
    if GPIOZERO_AVAILABLE:
        try:
            if sensor is None:
                sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIGGER_PIN, max_distance=2)
                print("✅ Ultrasonic DistanceSensor ready.")
        except Exception as e:
            print("⚠️ Ultrasonic init failed:", e)
            sensor = None
    else:
        print("⚠️ gpiozero not available; ultrasonic disabled.")

    # buzzer via gpiozero if available, else RPi.GPIO fallback
    if GPIOZERO_AVAILABLE:
        try:
            if buzzer is None:
                buzzer = Buzzer(BUZZER_PIN)
                print("✅ Buzzer ready (gpiozero).")
        except Exception as e:
            print("⚠️ Buzzer init failed (gpiozero):", e)
            buzzer = None
    else:
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(BUZZER_PIN, GPIO.OUT)
            buzzer = None  # we'll toggle via RPi.GPIO in functions
            print("⚠️ gpiozero missing; buzzer will use RPi.GPIO fallback.")
        except Exception as e:
            print("⚠️ Buzzer init failed (RPi.GPIO):", e)
            buzzer = None

    # OLED (luma)
    if LUMA_AVAILABLE:
        try:
            if oled is None:
                serial = i2c(port=I2C_PORT, address=OLED_I2C_ADDR)
                oled = ssd1306(serial)
                font = ImageFont.load_default()
                print("✅ OLED ready.")
        except Exception as e:
            print("⚠️ OLED init failed:", e)
            oled = None
    else:
        print("⚠️ luma or PIL not available; OLED disabled.")

    # I2C bus for Adafruit sensors (best effort)
    try:
        if board is not None:
            import busio as _busio
            i2c_bus = _busio.I2C(board.SCL, board.SDA)
    except Exception:
        i2c_bus = None

    # TCS34725 color sensor
    if TCS_AVAILABLE and i2c_bus is not None:
        try:
            if tcs is None:
                tcs = adafruit_tcs34725.TCS34725(i2c_bus)
                print("✅ TCS34725 color sensor ready.")
        except Exception as e:
            print("⚠️ TCS34725 init failed:", e)
            tcs = None
    else:
        if not TCS_AVAILABLE:
            print("⚠️ adafruit_tcs34725 not installed; color sensor disabled.")

    # MLX90614 temperature sensor
    if MLX_AVAILABLE and i2c_bus is not None:
        try:
            if mlx is None:
                mlx = adafruit_mlx90614.MLX90614(i2c_bus)
                print("✅ MLX90614 ready.")
        except Exception as e:
            print("⚠️ MLX90614 init failed:", e)
            mlx = None
    else:
        if not MLX_AVAILABLE:
            print("⚠️ adafruit_mlx90614 not installed; temperature sensor disabled.")

# initialize at startup
init_hardware()

# ---------------------------
# OLED helper
# ---------------------------
def show_on_oled(line1, line2=""):
    if oled is None:
        # print fallback
        print("OLED:", line1, line2)
        return
    try:
        with Image.new("1", oled.size) as image:
            draw = ImageDraw.Draw(image)
            draw.text((5, 5), line1, font=font, fill=255)
            if line2:
                draw.text((5, 30), line2, font=font, fill=255)
            oled.display(image)
    except Exception as e:
        print("OLED display error:", e)

# ---------------------------
# Sensor reading helpers
# ---------------------------
def read_distance():
    """Return distance in cm or -1 on error."""
    global sensor
    if sensor is None:
        init_hardware()
    if sensor is None:
        return -1
    try:
        # gpiozero DistanceSensor returns meters
        d_m = sensor.distance
        if d_m is None:
            return -1
        return round(d_m * 100, 2)
    except Exception as e:
        print("Distance read error:", e)
        return -1

def read_color():
    """Return a simplified color name or None"""
    global tcs
    if tcs is None:
        return None
    try:
        r, g, b, _ = tcs.color_raw
        # very rough heuristic to map to color names
        if r > g and r > b:
            return "Red"
        if g > r and g > b:
            return "Green"
        if b > r and b > g:
            return "Blue"
        return "Unknown"
    except Exception as e:
        print("Color read error:", e)
        return None

def read_temperature():
    """Return object temp in C (MLX90614) or None"""
    global mlx
    if mlx is None:
        return None
    try:
        temp = mlx.object_temperature
        return round(temp, 2)
    except Exception as e:
        print("Temp read error:", e)
        return None

# ---------------------------
# Buzzer helper
# ---------------------------
def buzz(duration=0.15):
    """Buzz once. Uses gpiozero Buzzer if available, else RPi.GPIO fallback."""
    global buzzer
    try:
        if buzzer is not None:
            # gpiozero Buzzer
            buzzer.beep(on_time=duration, off_time=0.05, n=1, background=False)
        else:
            # RPi.GPIO fallback
            GPIO.output(BUZZER_PIN, GPIO.HIGH)
            time.sleep(duration)
            GPIO.output(BUZZER_PIN, GPIO.LOW)
    except Exception as e:
        print("Buzz error:", e)

# ensure RPi.GPIO mode if using fallback
if not GPIOZERO_AVAILABLE:
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUZZER_PIN, GPIO.OUT)
    except Exception:
        pass

# ---------------------------
# Shape detection
# ---------------------------
def analyze_shape(distances):
    """Simple shape heuristics based on variation of distance readings."""
    if not distances:
        return "Unknown"
    # compute variation
    try:
        variation = statistics.pstdev(distances)
    except Exception:
        variation = 0
    if variation < 0.5:
        return "Flat Surface"
    elif variation < 2:
        return "Curved Surface"
    else:
        return "Irregular Surface"

# ---------------------------
# Cleanup
# ---------------------------
def cleanup_all(*args):
    print("Cleaning up hardware and GPIO...")
    try:
        if sensor is not None:
            try:
                sensor.close()
            except Exception:
                pass
        if buzzer is not None:
            try:
                buzzer.close()
            except Exception:
                pass
        if oled is not None:
            try:
                show_on_oled("Shutting down", "")
            except Exception:
                pass
    except Exception:
        pass
    try:
        GPIO.cleanup()
    except Exception:
        pass
    # don't sys.exit here when called by atexit
    # but if called via signal, exit.
    if args:
        sys.exit(0)

atexit.register(cleanup_all)
signal.signal(signal.SIGINT, cleanup_all)
signal.signal(signal.SIGTERM, cleanup_all)

# ---------------------------
# Flask routes
# ---------------------------
@app.route("/")
def root():
    return "Smart Surface Backend - go to /dashboard"

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/measure")
def measure():
    """Single read: distance, temp, color. Buzz once. Return JSON."""
    d = read_distance()
    temp = read_temperature()
    color = read_color()
    # show on OLED
    try:
        display_line1 = f"D: {d} cm" if d >= 0 else "D: --"
        display_line2 = f"T: {temp} C" if temp is not None else f"Color: {color or '--'}"
        show_on_oled(display_line1, display_line2)
    except Exception:
        pass
    # buzz
    try:
        buzz(0.12)
    except Exception:
        pass
    return jsonify({"distance": d, "temperature": temp, "color": color})

@app.route("/check_shape")
def check_shape_route():
    """
    Take 5 distance readings (0.5s apart), analyze shape, return:
    { distances: [..], average: X, variation: Y, shape: str, color: str, temperature: val }
    """
    readings = []
    for _ in range(5):
        d = read_distance()
        readings.append(d if d >= 0 else 0)
        time.sleep(0.45)  # small delay between reads

    avg = round(statistics.mean(readings), 2)
    variation = round(statistics.pstdev(readings), 2) if len(readings) > 1 else 0.0
    shape = analyze_shape(readings)
    color = read_color()
    temp = read_temperature()

    # show on OLED
    try:
        show_on_oled(f"Shape: {shape}", f"Davg:{avg}cm T:{temp if temp is not None else '--'}")
    except Exception:
        pass

    # buzz once to indicate completion
    try:
        buzz(0.2)
    except Exception:
        pass

    # Provide a "performance" metric for pie chart (normalized simple heuristics)
    def perf_score(val):
        if val is None:
            return 10
        # for temperature: assume if available -> high score
        return 90

    # color/shape/temperature "scores" (toy example: if reading exists => high)
    color_score = 90 if color else 10
    shape_score = 90 if shape else 10
    temp_score = 90 if temp is not None else 10

    return jsonify({
        "distances": readings,
        "average": avg,
        "variation": variation,
        "shape": shape,
        "color": color,
        "temperature": temp,
        "scores": {
            "color": color_score,
            "shape": shape_score,
            "temperature": temp_score
        }
    })

# ---------------------------
# Run app
# ---------------------------
if __name__ == "__main__":
    print(f"Starting Smart Surface app on {get_local_ip()}:5000")
    # show IP on OLED at startup
    try:
        show_on_oled("Server:", f"{get_local_ip()}:5000")
    except Exception:
        pass

    # IMPORTANT: disable reloader to avoid GPIO busy due to multi-process reloads
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
