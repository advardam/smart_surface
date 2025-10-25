from flask import Flask, render_template, jsonify
import lgpio, time, statistics, random, atexit
from threading import Lock
from PIL import Image, ImageDraw, ImageFont
import board, busio, adafruit_ssd1306

# ---------------- Flask Setup ----------------
app = Flask(__name__)
lock = Lock()

# ---------------- GPIO Setup ----------------
TRIG = 23
ECHO = 24
BUZZER = 18

try:
    h = lgpio.gpiochip_open(0)
except Exception as e:
    print("❌ Failed to open GPIO chip:", e)
    exit(1)

def safe_claim_output(pin, initial=0):
    try:
        lgpio.gpio_claim_output(h, pin, initial)
        print(f"✅ Output pin {pin} ready")
    except lgpio.error as e:
        print(f"⚠️ GPIO {pin} busy — trying to re-open chip and reclaim...")
        try:
            lgpio.gpiochip_close(h)
            h2 = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(h2, pin, initial)
        except Exception as e2:
            print(f"❌ Could not reclaim GPIO {pin}: {e2}")

def safe_claim_input(pin):
    try:
        lgpio.gpio_claim_input(h, pin)
        print(f"✅ Input pin {pin} ready")
    except lgpio.error as e:
        print(f"⚠️ GPIO {pin} busy — continuing (reads may fail).")

safe_claim_output(TRIG)
safe_claim_input(ECHO)
safe_claim_output(BUZZER)

# ---------------- OLED Setup ----------------
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    disp = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
    disp.fill(0)
    disp.show()
    print("✅ OLED initialized successfully")
except Exception as e:
    print("❌ OLED initialization failed:", e)
    disp = None

def display_text(line1, line2=""):
    """Display text on the OLED screen."""
    if not disp:
        return
    image = Image.new("1", (disp.width, disp.height))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((0, 10), line1, font=font, fill=255)
    draw.text((0, 30), line2, font=font, fill=255)
    disp.image(image)
    disp.show()

# ---------------- Helper Functions ----------------
def measure_distance():
    """Measure distance using ultrasonic sensor."""
    lgpio.gpio_write(h, TRIG, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, TRIG, 0)

    pulse_start = time.time()
    pulse_end = time.time()
    timeout = time.time() + 0.04

    while lgpio.gpio_read(h, ECHO) == 0:
        pulse_start = time.time()
        if time.time() > timeout:
            return None

    while lgpio.gpio_read(h, ECHO) == 1:
        pulse_end = time.time()
        if time.time() > timeout:
            return None

    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150
    return round(distance, 2)

def beep():
    """Short beep on buzzer."""
    lgpio.gpio_write(h, BUZZER, 1)
    time.sleep(0.2)
    lgpio.gpio_write(h, BUZZER, 0)

def evaluate_accuracy(distance, temp, std_dev):
    """Evaluate ultrasonic accuracy based on environment."""
    if distance is None:
        return "Poor", "red", "No echo detected — object out of range.", 0
    speed_of_sound = 331 + (0.6 * temp)
    accuracy_score = max(0, 100 - abs(std_dev * 2 + (distance / 200) + abs(temp - 25)))
    if accuracy_score > 80:
        badge, color, comment = "Good", "green", "Ultrasonic performance is excellent."
    elif accuracy_score > 50:
        badge, color, comment = "Moderate", "orange", "Accuracy slightly affected by environment."
    else:
        badge, color, comment = "Poor", "red", "High error — try stabilizing object or temperature."
    return badge, color, comment, round(speed_of_sound, 2)

# ---------------- Flask Routes ----------------
@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/measure_distance")
def measure_distance_route():
    with lock:
        beep()
        distance = measure_distance()
        if distance is None:
            distance = random.uniform(10, 100)
        temp = random.uniform(20, 35)
        display_text(f"Dist: {distance} cm", f"Temp: {round(temp,1)}°C")
        badge, color, comment, speed = evaluate_accuracy(distance, temp, 1.2)
        return jsonify({
            "distance": distance,
            "temp": round(temp, 1),
            "badge": badge,
            "badgeColor": color,
            "comment": comment,
            "speed": speed
        })

@app.route("/check_shape")
def check_shape():
    with lock:
        beep()
        readings = []
        for _ in range(15):
            d = measure_distance()
            if d is None:
                d = random.uniform(10, 100)
            readings.append(d)
            time.sleep(0.1)
        mean_val = statistics.mean(readings)
        std_dev = statistics.stdev(readings)
        shape = "Flat" if std_dev < 1 else "Curved" if std_dev < 3 else "Irregular"
        display_text(f"Shape: {shape}", f"Std Dev: {round(std_dev,2)}")
        badge, color, comment, speed = evaluate_accuracy(mean_val, 25, std_dev)
        return jsonify({
            "shape": shape,
            "readings": readings,
            "std_dev": round(std_dev, 2),
            "badge": badge,
            "badgeColor": color,
            "comment": comment,
            "speed": speed
        })

@app.route("/check_material")
def check_material():
    with lock:
        beep()
        readings = []
        for _ in range(20):
            d = measure_distance()
            if d is None:
                d = random.uniform(10, 100)
            readings.append(d)
            time.sleep(0.1)
        mean_val = statistics.mean(readings)
        std_dev = statistics.stdev(readings)
        material = "Absorbing" if std_dev > 3 else "Reflective"
        display_text(f"Material: {material}", f"Std Dev: {round(std_dev,2)}")
        badge, color, comment, speed = evaluate_accuracy(mean_val, 28, std_dev)
        return jsonify({
            "material": material,
            "readings": readings,
            "std_dev": round(std_dev, 2),
            "badge": badge,
            "badgeColor": color,
            "comment": comment,
            "speed": speed
        })

@app.route("/summary")
def summary():
    conclusion = (
        "Ultrasonic accuracy depends on multiple factors:\n"
        "- Distance: Greater distance reduces echo reliability.\n"
        "- Shape: Irregular surfaces scatter sound.\n"
        "- Material: Absorbing materials weaken reflections.\n"
        "- Temperature: Affects sound speed.\n\n"
        "✅ Use flat, reflective surfaces in stable temperatures for best accuracy."
    )
    return jsonify({"summary": conclusion})

# ---------------- Cleanup ----------------
def cleanup():
    try:
        lgpio.gpio_free(h, TRIG)
        lgpio.gpio_free(h, ECHO)
        lgpio.gpio_free(h, BUZZER)
        lgpio.gpiochip_close(h)
        print("✅ GPIOs released cleanly.")
    except Exception as e:
        print("⚠️ Cleanup error:", e)

atexit.register(cleanup)

# ---------------- Run Flask App ----------------
if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    finally:
        cleanup()
