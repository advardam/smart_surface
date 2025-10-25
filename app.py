import time
import statistics
import lgpio
from flask import Flask, render_template, jsonify
from threading import Thread
import Adafruit_SSD1306
from PIL import Image, ImageDraw, ImageFont
import board
import busio
import adafruit_tcs34725
import adafruit_mlx90614
import atexit

# -------------------------------
# GPIO SETUP (Raspberry Pi 5 + lgpio)
# -------------------------------
TRIG = 23
ECHO = 24
BUZZER = 18

h = lgpio.gpiochip_open(0)

def setup_gpio():
    try:
        lgpio.gpio_claim_output(h, TRIG)
        print("✅ Output pin 23 ready")
    except:
        print("⚠️ GPIO 23 busy — continuing...")

    try:
        lgpio.gpio_claim_input(h, ECHO)
        print("✅ Input pin 24 ready")
    except:
        print("⚠️ GPIO 24 busy — continuing...")

    try:
        lgpio.gpio_claim_output(h, BUZZER)
        print("✅ Output pin 18 ready")
    except:
        print("⚠️ GPIO 18 busy — continuing...")

setup_gpio()

# -------------------------------
# OLED DISPLAY SETUP
# -------------------------------
disp = Adafruit_SSD1306.SSD1306_128_64(rst=None)
disp.begin()
disp.clear()
disp.display()

def display_text(text):
    image = Image.new('1', (disp.width, disp.height))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((0, 0), text, font=font, fill=255)
    disp.image(image)
    disp.display()

# -------------------------------
# SENSOR SETUP
# -------------------------------
i2c = busio.I2C(board.SCL, board.SDA)
color_sensor = adafruit_tcs34725.TCS34725(i2c)
temp_sensor = adafruit_mlx90614.MLX90614(i2c)

# -------------------------------
# HELPER FUNCTIONS
# -------------------------------
def beep(duration=0.2):
    lgpio.gpio_write(h, BUZZER, 1)
    time.sleep(duration)
    lgpio.gpio_write(h, BUZZER, 0)

def measure_distance():
    lgpio.gpio_write(h, TRIG, 0)
    time.sleep(0.05)
    lgpio.gpio_write(h, TRIG, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, TRIG, 0)

    start = time.time()
    timeout = start + 0.04
    while lgpio.gpio_read(h, ECHO) == 0 and time.time() < timeout:
        start = time.time()
    while lgpio.gpio_read(h, ECHO) == 1 and time.time() < timeout:
        stop = time.time()

    elapsed = stop - start
    temp_c = temp_sensor.ambient_temperature
    speed = 331.3 + (0.606 * temp_c)
    distance = (elapsed * speed) / 2
    return round(distance, 2), round(speed, 2)

def detect_color():
    r, g, b, c = color_sensor.color_raw
    color_name = "Unknown"
    if r > g and r > b:
        color_name = "Red"
    elif g > r and g > b:
        color_name = "Green"
    elif b > r and b > g:
        color_name = "Blue"
    return color_name

def measure_shape():
    readings = []
    for _ in range(15):
        dist, _ = measure_distance()
        readings.append(dist)
        time.sleep(0.1)
    mean = statistics.mean(readings)
    stdev = statistics.stdev(readings)
    shape = "Flat" if stdev < 0.5 else "Curved"
    return readings, mean, stdev, shape

def detect_material():
    readings = []
    for _ in range(20):
        dist, _ = measure_distance()
        readings.append(dist)
        time.sleep(0.1)
    mean = statistics.mean(readings)
    stdev = statistics.stdev(readings)
    material = "Absorbing" if stdev > 1 else "Reflective"
    return readings, mean, stdev, material

# -------------------------------
# FLASK DASHBOARD
# -------------------------------
app = Flask(__name__)
data = {
    "distance": None,
    "color": None,
    "temp_obj": None,
    "temp_amb": None,
    "speed": None,
    "shape": None,
    "material": None,
    "readings": [],
}

@app.route('/')
def index():
    return render_template('index.html', data=data)

@app.route('/measure/distance')
def measure_distance_route():
    beep()
    dist, speed = measure_distance()
    temp_amb = temp_sensor.ambient_temperature
    temp_obj = temp_sensor.object_temperature
    color = detect_color()

    data.update({
        "distance": dist,
        "speed": speed,
        "temp_obj": round(temp_obj, 2),
        "temp_amb": round(temp_amb, 2),
        "color": color,
    })
    display_text(f"Dist: {dist}cm\nColor: {color}\nTemp: {temp_obj}°C")
    return jsonify(data)

@app.route('/measure/shape')
def measure_shape_route():
    beep()
    readings, mean, stdev, shape = measure_shape()
    data.update({"shape": shape, "readings": readings})
    display_text(f"Shape: {shape}\nMean: {mean:.2f}\nSD: {stdev:.2f}")
    return jsonify(data)

@app.route('/measure/material')
def measure_material_route():
    beep()
    readings, mean, stdev, material = detect_material()
    data.update({"material": material, "readings": readings})
    display_text(f"Material: {material}\nMean: {mean:.2f}\nSD: {stdev:.2f}")
    return jsonify(data)

# -------------------------------
# CLEANUP HANDLER
# -------------------------------
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

# -------------------------------
# RUN SERVER
# -------------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
