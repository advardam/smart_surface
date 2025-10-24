#!/usr/bin/env python3
"""
smart_surface_project/app.py

Robust Flask + sensors app for Raspberry Pi 5.
Safe initialization, GPIO cleanup, retries for ultrasonic reads,
buzzer & OLED feedback, and JSON endpoints for dashboard.
"""

import os
import time
import statistics
import threading
import atexit
import signal
from flask import Flask, render_template, jsonify
from threading import Lock

# GPIO and hardware libs
from gpiozero import Buzzer
from gpiozero import DistanceSensor as GZDistanceSensor
# we use RPi.GPIO for a cleanup fallback
try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None

# luma / PIL for OLED
try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    ssd1306 = None

# Adafruit sensors (optional)
try:
    import board, busio, adafruit_tcs34725, adafruit_mlx90614
except Exception:
    board = busio = adafruit_tcs34725 = adafruit_mlx90614 = None

# ---------- CONFIG ----------
TRIG_PIN = 23
ECHO_PIN = 24
BUZZER_PIN = 18
OLED_ADDR = 0x3C
I2C_PORT = 1

# thresholds & parameters
SHAPE_READINGS = 15
MATERIAL_READINGS = 20
DISTANCE_RETRIES = 4
DISTANCE_RETRY_DELAY = 0.12  # seconds between retry reads
READ_DELAY_SHAPE = 0.25
READ_DELAY_MATERIAL = 0.2

# ---------- GLOBALS ----------
app = Flask(__name__, static_folder="static", template_folder="templates")
hw_lock = Lock()

# hardware objects (initialized in init_hardware)
distance_sensor = None
buzzer = None
oled = None
oled_font = None
i2c_bus = None
color_sensor = None
mlx = None

# ---------- UTILS: init/cleanup ----------

def init_hardware(retries=2):
    """Try to initialize all hardware safely. If pins are busy try cleanup and retry."""
    global distance_sensor, buzzer, oled, oled_font, i2c_bus, color_sensor, mlx

    # attempt 1
    for attempt in range(retries):
        try:
            # DistanceSensor using gpiozero (may raise if pin busy)
            distance_sensor = GZDistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=2)
        except Exception as e:
            print(f"[init] DistanceSensor init failed (attempt {attempt+1}): {e}")
            distance_sensor = None
            # try cleanup and pause before retry
            _try_gpio_cleanup()
            time.sleep(0.5)
        else:
            break

    # buzzer
    try:
        buzzer = Buzzer(BUZZER_PIN)
    except Exception as e:
        print("[init] Buzzer init failed:", e)
        buzzer = None

    # OLED init (luma)
    if ssd1306:
        try:
            serial = i2c(port=I2C_PORT, address=OLED_ADDR)
            oled = ssd1306(serial)
            oled_font = ImageFont.load_default()
        except Exception as e:
            print("[init] OLED init failed:", e)
            oled = None
            oled_font = None

    # I2C sensors (TCS34725, MLX90614)
    if board and busio:
        try:
            i2c_bus = busio.I2C(board.SCL, board.SDA)
        except Exception as e:
            print("[init] I2C bus init failed:", e)
            i2c_bus = None
        else:
            if adafruit_tcs34725:
                try:
                    color_sensor = adafruit_tcs34725.TCS34725(i2c_bus)
                    color_sensor.integration_time = 50
                    color_sensor.gain = 4
                except Exception as e:
                    print("[init] TCS34725 init failed:", e)
                    color_sensor = None
            if adafruit_mlx90614:
                try:
                    mlx = adafruit_mlx90614.MLX90614(i2c_bus)
                except Exception as e:
                    print("[init] MLX90614 init failed:", e)
                    mlx = None
    else:
        i2c_bus = None
        color_sensor = None
        mlx = None

    print("[init] Hardware init completed. distance_sensor:", bool(distance_sensor),
          "oled:", bool(oled), "color_sensor:", bool(color_sensor), "mlx:", bool(mlx))


def _try_gpio_cleanup():
    """Attempt to free GPIO resources using different cleanup methods."""
    try:
        if GPIO:
            GPIO.cleanup()
            print("[cleanup] RPi.GPIO cleanup called")
    except Exception as e:
        print("[cleanup] RPi.GPIO cleanup failed:", e)
    # gpiozero handles its own cleanup when objects closed; we rely on that elsewhere

def cleanup_all():
    """Close and cleanup hardware objects."""
    global distance_sensor, buzzer, oled, color_sensor, mlx
    print("[cleanup] Running cleanup_all()")
    try:
        if distance_sensor:
            try:
                distance_sensor.close()
            except Exception:
                pass
            distance_sensor = None
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
    # final attempt to cleanup system GPIO
    _try_gpio_cleanup()
    print("[cleanup] Done.")


# ensure cleanup at normal exit
atexit.register(cleanup_all)
signal.signal(signal.SIGINT, lambda s,f: (cleanup_all(), os._exit(0)))
signal.signal(signal.SIGTERM, lambda s,f: (cleanup_all(), os._exit(0)))

# initialize hardware on start
init_hardware()

# ---------- SMALL HELPERS ----------

def beep(n=1, on=0.08, off=0.06):
    """Blocking beep pattern for immediate feedback."""
    if not buzzer:
        return
    try:
        for _ in range(n):
            buzzer.on()
            time.sleep(on)
            buzzer.off()
            time.sleep(off)
    except Exception as e:
        print("beep error:", e)

def oled_write(line1, line2=""):
    """Simple two-line write to OLED if available."""
    if not oled or not oled_font:
        return
    try:
        with Image.new("1", oled.size) as image:
            draw = ImageDraw.Draw(image)
            draw.text((2, 2), str(line1), font=oled_font, fill=255)
            draw.text((2, 18), str(line2), font=oled_font, fill=255)
            oled.display(image)
    except Exception as e:
        print("oled_write error:", e)

def safe_color_read():
    """Return r,g,b,lux or zeros if sensor missing."""
    if not color_sensor:
        return (0,0,0,0.0)
    try:
        r,g,b = color_sensor.color_rgb_bytes
        lux = color_sensor.lux or 0.0
        return (int(r), int(g), int(b), float(lux))
    except Exception as e:
        print("color read error:", e)
        return (0,0,0,0.0)

def safe_temp_read():
    """Return (obj, amb) or (None,None)"""
    if not mlx:
        return (None, None)
    try:
        return (round(mlx.object_temperature,2), round(mlx.ambient_temperature,2))
    except Exception as e:
        print("mlx read error:", e)
        return (None, None)

def speed_of_sound(ambient_c):
    """Approximate speed of sound in air (m/s). v ≈ 331.4 + 0.6*T"""
    if ambient_c is None:
        return None
    return round(331.4 + 0.6 * ambient_c, 2)

# ---------- DISTANCE READ with retries ----------

def read_distance_once(max_retries=DISTANCE_RETRIES, retry_delay=DISTANCE_RETRY_DELAY):
    """Attempt to read ultrasonic distance (cm) with retries.
       Returns float cm or None if no valid echo.
    """
    global distance_sensor
    if distance_sensor is None:
        # Try to re-init distance sensor once
        try:
            distance_sensor = GZDistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=2)
        except Exception as e:
            print("read_distance_once: sensor not available and reinit failed:", e)
            return None

    for attempt in range(max_retries):
        try:
            d = distance_sensor.distance * 100.0  # cm
            # Some platforms return 0.0 or tiny values when no echo -> treat <0.5 as invalid
            if d is None:
                valid = False
            else:
                valid = (d >= 0.5 and d <= 400.0)
            if valid:
                return round(d, 2)
        except Exception as e:
            # hardware/driver error -> try a short wait and retry
            print("read_distance_once exception:", e)
        time.sleep(retry_delay)
    # if all retries failed
    return None

# ---------- CLASSIFIERS ----------

def classify_shape_from_stats(valid_readings):
    """Given valid readings list, return (mean, std, label)"""
    if not valid_readings:
        return (None, None, "No reliable echoes")
    mean_v = round(statistics.mean(valid_readings), 3)
    std_v = round(statistics.pstdev(valid_readings) if len(valid_readings) > 1 else 0.0, 3)
    if std_v < 0.3:
        label = "Flat Surface"
    elif std_v < 1.0:
        label = "Slightly Curved"
    else:
        label = "Irregular Surface"
    return (mean_v, std_v, label)

def classify_material_from_stats(valid_readings, missing_fraction):
    """Heuristic detection for absorbing/transparent materials"""
    if not valid_readings:
        return ("No echoes - likely highly absorbing/transparent", None, None)
    mean_v = round(statistics.mean(valid_readings), 3)
    std_v = round(statistics.pstdev(valid_readings) if len(valid_readings) > 1 else 0.0, 3)
    if missing_fraction > 0.4 or std_v > 1.5:
        verdict = "Likely Absorbing / Transparent"
    elif std_v > 1.0:
        verdict = "Possibly Absorbing / Irregular"
    else:
        verdict = "Reflective / Good for Ultrasonic"
    return (verdict, mean_v, std_v)

# ---------- FLASK ROUTES ----------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/read_current")
def api_read_current():
    """Return current single-shot readings"""
    with hw_lock:
        d = read_distance_once()
        r,g,b,lux = safe_color_read()
        obj_temp, amb_temp = safe_temp_read()
    distance_text = f"{d} cm" if d is not None else "No echo / out of range"
    color_text = f"R={r} G={g} B={b}"
    temp_text = f"Obj: {obj_temp} °C, Amb: {amb_temp} °C" if obj_temp is not None else "Temp N/A"
    sos = speed_of_sound(amb_temp)
    return jsonify({
        "distance_val": d,
        "distance_text": distance_text,
        "color_text": color_text,
        "temp_text": temp_text,
        "r": r, "g": g, "b": b, "lux": lux,
        "obj_temp": obj_temp, "amb_temp": amb_temp,
        "speed_of_sound_m_s": sos
    })

@app.route("/api/measure_distance")
def api_measure_distance():
    """Single-shot distance measurement triggered by UI"""
    # beep + OLED feedback
    with hw_lock:
        beep(1)
        oled_write("Measuring", "Distance...")
        d = read_distance_once()
        r,g,b,lux = safe_color_read()
        obj_temp, amb_temp = safe_temp_read()
    beep(1)
    distance_text = f"{d} cm" if d is not None else "No echo / out of range"
    oled_write("Distance:", distance_text)
    sos = speed_of_sound(amb_temp)
    return jsonify({
        "distance_val": d,
        "distance_text": distance_text,
        "color_text": f"R={r} G={g} B={b}",
        "temp_text": f"Obj:{obj_temp} Amb:{amb_temp}" if obj_temp is not None else "Temp N/A",
        "speed_of_sound_m_s": sos
    })

@app.route("/api/measure_shape")
def api_measure_shape():
    """Take SHAPE_READINGS readings and classify"""
    with hw_lock:
        beep(1)
        oled_write("Measuring", f"Shape ({SHAPE_READINGS})")
        readings = []
        missing = 0
        for i in range(SHAPE_READINGS):
            d = read_distance_once()
            if d is None:
                readings.append(None)
                missing += 1
            else:
                readings.append(d)
            time.sleep(READ_DELAY_SHAPE)
    # compute stats on valid readings
    valid = [x for x in readings if x is not None]
    mean_v, std_v, label = classify_shape_from_stats(valid)
    missing_frac = round(missing / float(SHAPE_READINGS), 3)
    oled_write("Shape:", label)
    beep(2)
    return jsonify({
        "readings": readings,
        "valid_count": len(valid),
        "missing_fraction": missing_frac,
        "average": mean_v,
        "std": std_v,
        "shape": label
    })

@app.route("/api/measure_material")
def api_measure_material():
    """Take MATERIAL_READINGS readings and classify absorbing properties"""
    with hw_lock:
        beep(1)
        oled_write("Measuring", f"Material ({MATERIAL_READINGS})")
        readings = []
        missing = 0
        for i in range(MATERIAL_READINGS):
            d = read_distance_once()
            if d is None:
                readings.append(None)
                missing += 1
            else:
                readings.append(d)
            time.sleep(READ_DELAY_MATERIAL)
    valid = [x for x in readings if x is not None]
    miss_frac = round(missing / float(MATERIAL_READINGS), 3)
    verdict, mean_v, std_v = classify_material_from_stats(valid, miss_frac)
    oled_write("Material:", verdict)
    beep(2)
    return jsonify({
        "readings": readings,
        "valid_count": len(valid),
        "missing_fraction": miss_frac,
        "average": mean_v,
        "std": std_v,
        "verdict": verdict
    })

# ---------- STARTUP ----------
if __name__ == "__main__":
    # If pins were busy on start, a manual reboot sometimes required.
    print("Starting Flask app. If DistanceSensor still reports 'busy' try rebooting the Pi.")
    app.run(host="0.0.0.0", port=5000)
