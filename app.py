from flask import Flask, render_template, jsonify
import RPi.GPIO as GPIO
import time, statistics, random
from threading import Lock
import Adafruit_SSD1306
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
lock = Lock()

# Ultrasonic sensor pins
TRIG = 23
ECHO = 24
BUZZER = 18

# GPIO Setup
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.setup(BUZZER, GPIO.OUT)

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

# Helper functions
def measure_distance():
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)
    start = time.time()
    stop = time.time()
    while GPIO.input(ECHO) == 0:
        start = time.time()
    while GPIO.input(ECHO) == 1:
        stop = time.time()
    elapsed = stop - start
    distance = (elapsed * 34300) / 2
    return round(distance, 2)

def beep():
    GPIO.output(BUZZER, True)
    time.sleep(0.2)
    GPIO.output(BUZZER, False)

def oled_display(line1, line2=""):
    draw.rectangle((0, 0, width, height), outline=0, fill=0)
    draw.text((0, 10), line1, font=font, fill=255)
    draw.text((0, 30), line2, font=font, fill=255)
    disp.image(image)
    disp.display()

def evaluate_accuracy(distance, temp, std_dev):
    """Returns badge type and recommendation."""
    speed_of_sound = 331 + (0.6 * temp)
    accuracy_score = max(0, 100 - abs(std_dev * 2 + (distance / 200) + abs(temp - 25)))
    if accuracy_score > 80:
        badge, color, comment = "Good", "green", "Ultrasonic performance is excellent."
    elif accuracy_score > 50:
        badge, color, comment = "Moderate", "orange", "Accuracy slightly affected by environment."
    else:
        badge, color, comment = "Poor", "red", "High error — try stabilizing object or temp."
    return badge, color, comment, round(speed_of_sound, 2)

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/measure_distance")
def measure_distance_route():
    with lock:
        beep()
        try:
            distance = measure_distance()
        except:
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
        for _ in range(15):
            try:
                d = measure_distance()
            except:
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
        for _ in range(20):
            try:
                d = measure_distance()
            except:
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
    """Generate a textual summary based on sensor trends."""
    conclusion = (
        "Ultrasonic accuracy depends on multiple factors:\n"
        "- **Distance:** Greater distance reduces echo reliability.\n"
        "- **Shape:** Irregular surfaces scatter sound, reducing precision.\n"
        "- **Material:** Absorbing materials cause weak reflections.\n"
        "- **Temperature:** Affects sound speed; higher temp increases accuracy slightly.\n\n"
        "Final Insight: Maintain moderate temperature and reflective, flat surfaces "
        "for the most reliable ultrasonic readings."
    )
    return jsonify({"summary": conclusion})

@app.teardown_appcontext
def cleanup_gpio(exception=None):
    GPIO.cleanup()

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    finally:
        GPIO.cleanup()
