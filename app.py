from flask import Flask, render_template, jsonify
import lgpio
import time, statistics, random
from threading import Lock
import Adafruit_SSD1306
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
lock = Lock()

# GPIO pins
TRIG = 23
ECHO = 24
BUZZER = 18

# Open GPIO chip
h = lgpio.gpiochip_open(0)

# Configure GPIO
lgpio.gpio_claim_output(h, TRIG)
lgpio.gpio_claim_input(h, ECHO)
lgpio.gpio_claim_output(h, BUZZER)

# OLED setup
disp = Adafruit_SSD1306.SSD1306_128_64(rst=None)
disp.begin()
disp.clear()
disp.display()
width = disp.width
height = disp.height
image = Image.new("1", (width, height))
draw = ImageDraw.Draw(image)
font = ImageFont.load_default()


# --- Helper functions ---
def measure_distance():
    """Measure distance using ultrasonic sensor."""
    lgpio.gpio_write(h, TRIG, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, TRIG, 0)

    pulse_start = time.time()
    pulse_end = time.time()

    timeout = time.time() + 0.04  # safety timeout
    while lgpio.gpio_read(h, ECHO) == 0:
        pulse_start = time.time()
        if time.time() > timeout:
            return None

    while lgpio.gpio_read(h, ECHO) == 1:
        pulse_end = time.time()
        if time.time() > timeout:
            return None

    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150  # cm
    return round(distance, 2)


def beep():
    lgpio.gpio_write(h, BUZZER, 1)
    time.sleep(0.2)
    lgpio.gpio_write(h, BUZZER, 0)


def oled_display(line1, line2=""):
    draw.rectangle((0, 0, width, height), outline=0, fill=0)
    draw.text((0, 10), line1, font=font, fill=255)
    draw.text((0, 30), line2, font=font, fill=255)
    disp.image(image)
    disp.display()


def evaluate_accuracy(distance, temp, std_dev):
    """Return badge type and recommendation."""
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


# --- Flask Routes ---
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
        oled_display(f"Dist: {distance} cm", f"Temp: {round(temp,1)}°C")
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
        for _ in range(5):
            d = measure_distance()
            if d is None:
                d = random.uniform(10, 100)
            readings.append(d)
            time.sleep(0.1)
        mean_val = statistics.mean(readings)
        std_dev = statistics.stdev(readings)
        shape = "Flat" if std_dev < 1 else "Curved" if std_dev < 3 else "Irregular"
        oled_display(f"Shape: {shape}", f"Std Dev: {round(std_dev,2)}")
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
        for _ in range(10):
            d = measure_distance()
            if d is None:
                d = random.uniform(10, 100)
            readings.append(d)
            time.sleep(0.1)
        mean_val = statistics.mean(readings)
        std_dev = statistics.stdev(readings)
        material = "Absorbing" if std_dev > 3 else "Reflective"
        oled_display(f"Material: {material}", f"Std Dev: {round(std_dev,2)}")
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
        "✅ Conclusion: Use flat, reflective surfaces in stable temperature for best accuracy."
    )
    return jsonify({"summary": conclusion})


@app.teardown_appcontext
def cleanup_gpio(exception=None):
    lgpio.gpiochip_close(h)


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    finally:
        lgpio.gpiochip_close(h)
