#!/usr/bin/env python3
"""
Smart Surface & Shape Detection Dashboard
Raspberry Pi 5

Features:
 - Measure Distance (single)
 - Measure Shape (15 readings -> mean/std -> classification) + show 15-point line chart
 - Test Ultrasonic-absorbing Material (20 readings -> mean/std -> classification) + show 20-point line chart
 - Read color (TCS34725) and temps (MLX90614) and show on dashboard + OLED
 - Calculate speed of sound from ambient temperature and show effect on ultrasonic accuracy
 - Buzzer beep and OLED update on every measurement
 - Safe sensor init, cleanup, automatic reinit if possible
"""

import os
import time
import statistics
import threading
import signal
from flask import Flask, render_template, jsonify
# hardware libs
from gpiozero import DistanceSensor, Buzzer
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageDraw, ImageFont
import board, busio

# optional Adafruit sensors (may raise if not installed)
try:
    import adafruit_tcs34725
except Exception:
    adafruit_tcs34725 = None
try:
    import adafruit_mlx90614
except Exception:
    adafruit_mlx90614 = None

# ---------- CONFIG ----------
TRIGGER_PIN = 23
ECHO_PIN = 24
BUZZER_PIN = 18
OLED_I2C_ADDR = 0x3C
I2C_PORT = 1

# thresholds (tune for your setup)
SHAPE_FLAT_STD = 0.3        # std dev < 0.3 cm => flat
SHAPE_CURVED_STD = 1.0      # std dev < 1.0 cm => slightly curved
MATERIAL_ABSORB_STD = 1.5   # higher std dev => likely absorbing / reflective problems
MISSING_ECHO_THRESHOLD = 0.3 # fraction of missing readings to flag unreliable readings

# ---------- GLOBALS ----------
app = Flask(__name__, static_folder="static")
sensor = None
buzzer = None
oled = None
font = None
i2c_bus = None
color_sensor = None
mlx = None

# ensure thread-safety for hardware access
hw_lock = threading.Lock()

# ---------- SAFE INIT FUNCTIONS ----------
def init_hardware():
    global sensor, buzzer, oled, font, i2c_bus, color_sensor, mlx
    # DistanceSensor may raise if pins are busy — try/except
    try:
        sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIGGER_PIN, max_distance=2)
    except Exception as e:
        print("Warning: DistanceSensor init failed:", e)
        sensor = None

    try:
        buzzer = Buzzer(BUZZER_PIN)
    except Exception as e:
        print("Warning: Buzzer init failed:", e)
        buzzer = None

    # OLED via luma
    try:
        serial = i2c(port=I2C_PORT, address=OLED_I2C_ADDR)
        oled = ssd1306(serial)
        font = ImageFont.load_default()
    except Exception as e:
        print("Warning: OLED init failed:", e)
        oled = None
        font = None

    # I2C bus and sensors
    try:
        i2c_bus = busio.I2C(board.SCL, board.SDA)
    except Exception as e:
        print("Warning: I2C bus init failed:", e)
        i2c_bus = None

    if i2c_bus:
        if adafruit_tcs34725:
            try:
                color_sensor = adafruit_tcs34725.TCS34725(i2c_bus)
                color_sensor.integration_time = 50
                color_sensor.gain = 4
            except Exception as e:
                print("Warning: TCS34725 init failed:", e)
                color_sensor = None
        if adafruit_mlx90614:
            try:
                mlx = adafruit_mlx90614.MLX90614(i2c_bus)
            except Exception as e:
                print("Warning: MLX90614 init failed:", e)
                mlx = None

    # store to globals
    globals().update(locals())

def cleanup_hardware():
    global sensor, buzzer, oled
    try:
        if sensor:
            sensor.close()
    except Exception:
        pass
    try:
        if buzzer:
            buzzer.close()
    except Exception:
        pass
    try:
        if oled:
            oled.clear()
    except Exception:
        pass

# call init at import
init_hardware()

# handle termination to cleanup GPIO
def handle_exit(sig, frame):
    print("Shutting down, cleaning up hardware...")
    cleanup_hardware()
    os._exit(0)

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

# ---------- UTILS ----------
def beep_pattern(n=1, on=0.08, off=0.08):
    """Short synchronous beep pattern using buzzer (if available)."""
    if buzzer:
        try:
            for _ in range(n):
                buzzer.on()
                time.sleep(on)
                buzzer.off()
                time.sleep(off)
        except Exception as e:
            print("Buzzer error:", e)

def oled_message(line1, line2=""):
    """Write two lines to OLED (simple)."""
    if not oled or not font:
        return
    try:
        with Image.new("1", oled.size) as image:
            draw = ImageDraw.Draw(image)
            draw.text((2, 4), str(line1), font=font, fill=255)
            draw.text((2, 20), str(line2), font=font, fill=255)
            oled.display(image)
    except Exception as e:
        print("OLED write error:", e)

def read_distance_once():
    """Return distance in cm or None if sensor not available or no echo."""
    if sensor is None:
        return None
    try:
        # DistanceSensor returns value 0..1*max_distance
        d = sensor.distance * 100.0
        # Some sensors return 0 if no echo; treat <0.5 cm as invalid
        if d <= 0.5 or d > 200:
            return None
        return round(d, 2)
    except Exception as e:
        print("Distance read error:", e)
        return None

def read_color_safe():
    """Return RGB tuple (0..255) and lux; safe if sensor missing."""
    if color_sensor is None:
        return (0,0,0,0)
    try:
        r,g,b = color_sensor.color_rgb_bytes
        lux = color_sensor.lux or 0.0
        return (int(r), int(g), int(b), float(lux))
    except Exception as e:
        print("Color read error:", e)
        return (0,0,0,0)

def read_temps_safe():
    """Return (object_temp_C, ambient_temp_C)"""
    if mlx is None:
        return (None, None)
    try:
        return (round(mlx.object_temperature,2), round(mlx.ambient_temperature,2))
    except Exception as e:
        print("Temp read error:", e)
        return (None, None)

def speed_of_sound(ambient_c):
    """Speed of sound in air as function of temperature (m/s).
       v ≈ 331.4 + 0.6 * T (°C)
    """
    if ambient_c is None:
        return None
    return round(331.4 + 0.6 * ambient_c, 2)

# ---------- CLASSIFICATION LOGIC ----------
def classify_shape_from_stats(mean_v, std_v):
    """Return human-friendly shape classification."""
    if std_v < SHAPE_FLAT_STD:
        return "Flat Surface"
    elif std_v < SHAPE_CURVED_STD:
        return "Slightly Curved Surface"
    else:
        return "Irregular Surface"

def classify_absorbing_from_stats(mean_v, std_v, missing_ratio):
    """
    Heuristic:
      - If many missing echoes (missing_ratio high) or std dev large -> likely absorbing/transparent/irregular
      - If std small and missing_ratio small -> reflective/normal surface
    """
    if missing_ratio > 0.4 or std_v > MATERIAL_ABSORB_STD:
        return "Likely Absorbing/Transparent Material"
    elif std_v > 1.0:
        return "Possibly Absorbing / Irregular"
    else:
        return "Reflective / Good for Ultrasonic"

# ---------- FLASK ROUTES ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/read_current")
def api_read_current():
    """Return single-shot current readings (distance, color, temps, speed)"""
    with hw_lock:
        d = read_distance_once()
        r,g,b,lux = read_color_safe()
        obj_t, amb_t = read_temps_safe()
    soc = speed_of_sound(amb_t)
    # neat clean text outputs
    distance_text = f"{d} cm" if d is not None else "No echo / out of range"
    color_text = f"R={r} G={g} B={b}"
    temp_text = f"Obj: {obj_t} °C, Amb: {amb_t} °C" if obj_t is not None else "Temp N/A"
    return jsonify({
        "distance_val": d,
        "distance_text": distance_text,
        "color_text": color_text,
        "temp_text": temp_text,
        "r": r, "g": g, "b": b, "lux": lux,
        "obj_temp": obj_t, "amb_temp": amb_t,
        "speed_of_sound_m_s": soc
    })

@app.route("/api/measure_distance")
def api_measure_distance():
    """Triggered when user presses 'Measure Distance' button"""
    beep_pattern(1)
    oled_message("Measuring", "Distance...")
    with hw_lock:
        d = read_distance_once()
        r,g,b,lux = read_color_safe()
        obj_t, amb_t = read_temps_safe()
    soc = speed_of_sound(amb_t)
    distance_text = f"{d} cm" if d is not None else "No echo / out of range"
    # display on OLED and return JSON
    oled_message("Distance:", distance_text)
    beep_pattern(1)
    return jsonify({
        "distance_val": d,
        "distance_text": distance_text,
        "color_text": f"R={r} G={g} B={b}",
        "temp_text": f"Obj:{obj_t} Amb:{amb_t}" if obj_t is not None else "Temp N/A",
        "speed_of_sound_m_s": soc
    })

@app.route("/api/measure_shape")
def api_measure_shape():
    """Take 15 readings quickly and classify shape; return readings + stats"""
    beep_pattern(1)
    oled_message("Measuring", "Shape (15)...")
    readings = []
    missing = 0
    with hw_lock:
        for i in range(15):
            d = read_distance_once()
            if d is None:
                missing += 1
                readings.append(None)
            else:
                readings.append(d)
            time.sleep(0.25)
    # filter valid readings for stats
    valid = [x for x in readings if x is not None]
    if len(valid) == 0:
        result = {
            "readings": readings,
            "average": None,
            "std": None,
            "shape": "No reliable echoes",
            "missing_fraction": 1.0
        }
    else:
        mean_v = round(statistics.mean(valid), 3)
        # use population stdev to reflect spread; if only one reading, stdev=0
        std_v = round(statistics.pstdev(valid) if len(valid)>1 else 0.0, 3)
        missing_frac = round(missing / 15.0, 3)
        shape = classify_shape_from_stats(mean_v, std_v)
        result = {
            "readings": readings,
            "average": mean_v,
            "std": std_v,
            "shape": shape,
            "missing_fraction": missing_frac
        }
    # OLED + beep
    oled_message("Shape:", result.get("shape"))
    beep_pattern(2)
    return jsonify(result)

@app.route("/api/measure_material")
def api_measure_material():
    """Take 20 readings and decide if material is ultrasonic-absorbing/transparent."""
    beep_pattern(1)
    oled_message("Material Test", "Measuring (20)...")
    readings = []
    missing = 0
    with hw_lock:
        for i in range(20):
            d = read_distance_once()
            if d is None:
                missing += 1
                readings.append(None)
            else:
                readings.append(d)
            time.sleep(0.2)
    valid = [x for x in readings if x is not None]
    if len(valid) == 0:
        verdict = "No reliable echoes - likely highly absorbing/transparent"
        avg = None; std_v = None; miss_frac = 1.0
    else:
        avg = round(statistics.mean(valid), 3)
        std_v = round(statistics.pstdev(valid) if len(valid)>1 else 0.0, 3)
        miss_frac = round(missing / 20.0, 3)
        verdict = classify_absorbing_from_stats(avg, std_v, miss_frac)
    oled_message("Material Test", verdict)
    beep_pattern(2)
    return jsonify({
        "readings": readings,
        "average": avg,
        "std": std_v,
        "missing_fraction": miss_frac,
        "verdict": verdict
    })

# ---------- Run ----------
if __name__ == "__main__":
    # If app restarted, try to re-init hardware if any is None
    init_hardware()
    app.run(host="0.0.0.0", port=5000, debug=False)
