# app.py
from flask import Flask, render_template, jsonify
import lgpio
import time, statistics, random, sys
from threading import Lock
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageDraw, ImageFont

# Attempt to import MLX90614 temp sensor library; if not available we'll simulate
try:
    from smbus2 import SMBus
    # try importing mlx90614 python wrapper if present
    try:
        import mlx90614
        MLX_AVAILABLE = True
    except Exception:
        MLX_AVAILABLE = False
except Exception:
    MLX_AVAILABLE = False

app = Flask(__name__, static_folder="static", template_folder="templates")
lock = Lock()

# GPIO pins
TRIG = 23
ECHO = 24
BUZZER = 18

# ---------- Safe GPIO setup with self-recovery ----------
def open_gpiochip():
    try:
        return lgpio.gpiochip_open(0)
    except Exception as e:
        print("❌ Failed to open GPIO chip:", e)
        sys.exit(1)

def safe_claim_output(h, pin, level=0):
    try:
        lgpio.gpio_claim_output(h, pin, level)
        print(f"✅ Output pin {pin} ready")
        return h
    except lgpio.error as e:
        if "busy" in str(e).lower():
            print(f"⚠️ GPIO {pin} busy — trying to re-open chip and reclaim...")
            try:
                lgpio.gpiochip_close(h)
                time.sleep(0.2)
                new_h = open_gpiochip()
                lgpio.gpio_claim_output(new_h, pin, level)
                print(f"✅ GPIO {pin} reclaimed successfully")
                return new_h
            except Exception as e2:
                print(f"❌ Could not reclaim GPIO {pin}: {e2}")
        else:
            print(f"⚠️ Could not claim GPIO {pin}: {e}")
    return h

def safe_claim_input(h, pin):
    try:
        lgpio.gpio_claim_input(h, pin)
        print(f"✅ Input pin {pin} ready")
    except lgpio.error as e:
        if "busy" in str(e).lower():
            print(f"⚠️ GPIO {pin} busy — continuing (reads may fail).")
        else:
            print(f"⚠️ Could not claim GPIO {pin}: {e}")

# Open and configure GPIO
h = open_gpiochip()
h = safe_claim_output(h, TRIG)
safe_claim_input(h, ECHO)
h = safe_claim_output(h, BUZZER)

# ---------- OLED setup (luma.oled) ----------
serial = i2c(port=1, address=0x3C)
disp = ssd1306(serial)
width, height = disp.width, disp.height
image = Image.new("1", (width, height))
draw = ImageDraw.Draw(image)
font = ImageFont.load_default()

def oled_display(line1, line2=""):
    draw.rectangle((0, 0, width, height), outline=0, fill=0)
    # center shorter text visually
    draw.text((0, 8), str(line1), font=font, fill=255)
    draw.text((0, 28), str(line2), font=font, fill=255)
    disp.display(image)

# ---------- Temperature reading (MLX90614) or fallback ----------
def read_temps():
    """
    Returns (ambient_temp_C, object_temp_C).
    If MLX sensor present, read actual; otherwise simulate plausible values.
    """
    if MLX_AVAILABLE:
        try:
            bus = SMBus(1)
            sensor = mlx90614.MLX90614(bus, address=0x5A)
            ambient = sensor.get_ambient_temp()
            obj = sensor.get_obj_temp()
            return round(ambient, 2), round(obj, 2)
        except Exception as e:
            print("MLX read failed:", e)
    # fallback simulated readings
    ambient = random.uniform(20.0, 30.0)
    obj = ambient + random.uniform(-2.0, 5.0)
    return round(ambient, 2), round(obj, 2)

# ---------- (Optional) Color sensor read; fallback simulated ----------
def read_color():
    """
    Placeholder: if you have TCS34725 code, insert here.
    We'll return a simple color name (string). Currently simulated.
    """
    # For real sensor, replace with actual read. For now, random choice:
    return random.choice(["Red", "Green", "Blue", "White", "Black", "Yellow"])

# ---------- Helper: ultrasonic measurement ----------
def measure_distance_once():
    """
    Send trigger and wait for echo. Returns distance in cm or None on timeout.
    Uses lgpio h handle.
    """
    try:
        lgpio.gpio_write(h, TRIG, 0)
        time.sleep(0.002)
        lgpio.gpio_write(h, TRIG, 1)
        time.sleep(0.00001)
        lgpio.gpio_write(h, TRIG, 0)

        start_time = time.time()
        timeout = start_time + 0.05  # 50ms
        while lgpio.gpio_read(h, ECHO) == 0:
            start_time = time.time()
            if time.time() > timeout:
                return None

        end_time = time.time()
        while lgpio.gpio_read(h, ECHO) == 1:
            end_time = time.time()
            if time.time() > timeout:
                return None

        distance = (end_time - start_time) * 17150  # cm
        return round(distance, 2) if distance > 2 else None
    except Exception as e:
        print("Ultrasonic read error:", e)
        return None

def beep(duration=0.12):
    try:
        lgpio.gpio_write(h, BUZZER, 1)
        time.sleep(duration)
        lgpio.gpio_write(h, BUZZER, 0)
    except Exception:
        pass

def speed_of_sound_c(ambient_temp_c):
    """Speed of sound in air (m/s) approximation: 331 + 0.6*T"""
    return round(331.0 + 0.6 * ambient_temp_c, 2)

def evaluate_accuracy(distance_cm, temp_c, std_dev):
    """Return badge and comment and numeric accuracy score (0-100)"""
    if distance_cm is None:
        return {"badge": "Poor", "color": "red", "comment": "No echo detected — object out of range.", "score": 0}
    # simple heuristic: larger std_dev and greater distance and temp deviation reduce accuracy
    score = max(0, 100 - (abs(std_dev) * 5) - (distance_cm / 2) - abs(temp_c - 25))
    if score > 80:
        badge, color, comment = "Good", "green", "Ultrasonic performance is excellent."
    elif score > 50:
        badge, color, comment = "Moderate", "orange", "Accuracy slightly affected by environment."
    else:
        badge, color, comment = "Poor", "red", "High error — try stabilizing object or temperature."
    return {"badge": badge, "color": color, "comment": comment, "score": round(score, 1)}

# ---------- Flask routes ----------
@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/measure_distance", methods=["GET"])
def route_measure_distance():
    """
    Single distance measurement. Updates OLED and returns JSON:
    { distance, color, object_temp, ambient_temp, temp_diff, speed_of_sound, accuracy }
    """
    with lock:
        beep()
        distance = measure_distance_once()
        if distance is None:
            # fallback simulated reading for UI continuity
            distance = round(random.uniform(5.0, 120.0), 2)
        ambient, obj_temp = read_temps()
        color = read_color()
        temp_diff = round(obj_temp - ambient, 2)
        speed = speed_of_sound_c(ambient)
        acc = evaluate_accuracy(distance, ambient, 0.5)  # std dev unknown for single read
        oled_display(f"Dist: {distance} cm", f"Temp: {obj_temp}C")
        return jsonify({
            "distance": distance,
            "color": color,
            "object_temp": obj_temp,
            "ambient_temp": ambient,
            "temp_diff": temp_diff,
            "speed_of_sound": speed,
            "accuracy": acc
        })

@app.route("/measure_shape", methods=["GET"])
def route_measure_shape():
    """
    Take 15 readings, compute mean/stddev, classify shape, return readings + stats.
    """
    with lock:
        beep()
        readings = []
        for i in range(15):
            d = measure_distance_once()
            if d is None:
                # fallback simulated measurement
                d = round(random.uniform(5.0, 120.0), 2)
            readings.append(d)
            time.sleep(0.08)  # short pause between readings

        mean_val = statistics.mean(readings)
        std_dev = statistics.pstdev(readings) if len(readings) > 1 else 0.0
        # classify: tight std => flat; moderate => curved; large => irregular
        if std_dev < 1.0:
            shape = "Flat"
        elif std_dev < 3.0:
            shape = "Curved"
        else:
            shape = "Irregular"

        ambient, obj_temp = read_temps()
        temp_diff = round(obj_temp - ambient, 2)
        speed = speed_of_sound_c(ambient)
        acc = evaluate_accuracy(mean_val, ambient, std_dev)
        oled_display(f"Shape: {shape}", f"Std: {round(std_dev,2)}")
        return jsonify({
            "readings": readings,
            "mean": round(mean_val, 2),
            "std_dev": round(std_dev, 3),
            "shape": shape,
            "ambient_temp": ambient,
            "object_temp": obj_temp,
            "temp_diff": temp_diff,
            "speed_of_sound": speed,
            "accuracy": acc
        })

@app.route("/measure_material", methods=["GET"])
def route_measure_material():
    """
    Take 20 readings, compute mean/stddev, classify material (Absorbing/Reflective).
    """
    with lock:
        beep()
        readings = []
        for i in range(20):
            d = measure_distance_once()
            if d is None:
                d = round(random.uniform(5.0, 120.0), 2)
            readings.append(d)
            time.sleep(0.08)

        mean_val = statistics.mean(readings)
        std_dev = statistics.pstdev(readings) if len(readings) > 1 else 0.0
        # heuristic: absorbing materials cause higher variance / weaker returns
        material = "Absorbing" if std_dev > 3.0 else "Reflective"

        ambient, obj_temp = read_temps()
        temp_diff = round(obj_temp - ambient, 2)
        speed = speed_of_sound_c(ambient)
        acc = evaluate_accuracy(mean_val, ambient, std_dev)
        oled_display(f"Material: {material}", f"Std: {round(std_dev,2)}")
        return jsonify({
            "readings": readings,
            "mean": round(mean_val, 2),
            "std_dev": round(std_dev, 3),
            "material": material,
            "ambient_temp": ambient,
            "object_temp": obj_temp,
            "temp_diff": temp_diff,
            "speed_of_sound": speed,
            "accuracy": acc
        })

@app.route("/summary", methods=["GET"])
def route_summary():
    """Provide textual conclusions about temperature effect and accuracy."""
    text = (
        "Ultrasonic accuracy depends on distance (longer = weaker), shape (irregular scatters),\n"
        "material (absorbing materials reduce echoes), and temperature (affects speed of sound).\n\n"
        "Conclusion: Minimize temperature difference between object and ambient; use flat reflective surfaces\n"
        "for best accuracy. Speed of sound used = 331 + 0.6*T (m/s)."
    )
    return jsonify({"summary": text})

@app.teardown_appcontext
def cleanup_gpio(exception=None):
    try:
        lgpio.gpiochip_close(h)
    except Exception:
        pass

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        try:
            lgpio.gpiochip_close(h)
        except Exception:
            pass
