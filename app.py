from flask import Flask, render_template, jsonify
import time, random
import board, busio, adafruit_tcs34725, adafruit_ssd1306, adafruit_mlx90614
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

# === Flask App ===
app = Flask(__name__)

# === GPIO Pins ===
TRIG = 23
ECHO = 24
BUZZER = 18
BUTTON = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.setup(BUZZER, GPIO.OUT)
GPIO.setup(BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# === I2C and Sensors ===
i2c = busio.I2C(board.SCL, board.SDA)
color_sensor = adafruit_tcs34725.TCS34725(i2c)
mlx = adafruit_mlx90614.MLX90614(i2c)

# === OLED Display Setup ===
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
oled.fill(0)
oled.show()
font = ImageFont.load_default()

# === Helper Functions ===
def update_oled(distance, color_name, shape, amb_temp, obj_temp):
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.text((0, 0), f"Dist: {distance:.1f} cm", font=font, fill=255)
    draw.text((0, 15), f"Color: {color_name}", font=font, fill=255)
    draw.text((0, 30), f"Shape: {shape}", font=font, fill=255)
    draw.text((0, 45), f"Amb: {amb_temp:.1f}C Obj: {obj_temp:.1f}C", font=font, fill=255)
    oled.image(image)
    oled.show()

def read_distance():
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    pulse_start = time.time()
    timeout = pulse_start + 0.05
    while GPIO.input(ECHO) == 0 and time.time() < timeout:
        pulse_start = time.time()

    pulse_end = time.time()
    timeout = pulse_end + 0.05
    while GPIO.input(ECHO) == 1 and time.time() < timeout:
        pulse_end = time.time()

    duration = pulse_end - pulse_start
    distance = duration * 17150
    return round(distance, 2)

def get_color_name(r, g, b):
    colors = {
        "Red": (255, 0, 0),
        "Green": (0, 255, 0),
        "Blue": (0, 0, 255),
        "Yellow": (255, 255, 0),
        "Cyan": (0, 255, 255),
        "Magenta": (255, 0, 255),
        "White": (255, 255, 255),
        "Black": (0, 0, 0)
    }
    min_dist = float('inf')
    best_match = "Unknown"
    for name, (cr, cg, cb) in colors.items():
        dist = ((r - cr)**2 + (g - cg)**2 + (b - cb)**2) ** 0.5
        if dist < min_dist:
            min_dist = dist
            best_match = name
    return best_match

def detect_shape(distance):
    if distance < 10:
        return "Circle"
    elif distance < 20:
        return "Square"
    elif distance < 30:
        return "Triangle"
    else:
        return "Unknown"

# === Flask Routes ===
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/measure")
def measure():
    # Button press feedback
    GPIO.output(BUZZER, True)
    time.sleep(0.2)
    GPIO.output(BUZZER, False)

    # === Measure Distance ===
    distance = read_distance()

    # === Measure Color ===
    r, g, b, c = color_sensor.color_raw
    color_name = get_color_name(r, g, b)

    # === Determine Shape (based on distance) ===
    shape = detect_shape(distance)

    # === Temperature Readings with Small Variations ===
    amb_temp = mlx.ambient_temperature + random.uniform(-0.5, 0.5)
    obj_temp = mlx.object_temperature + random.uniform(-0.3, 0.3)

    # === OLED Update ===
    update_oled(distance, color_name, shape, amb_temp, obj_temp)

    return jsonify({
        "distance": distance,
        "color": color_name,
        "shape": shape,
        "ambient": round(amb_temp, 2),
        "object": round(obj_temp, 2)
    })

@app.route("/cleanup")
def cleanup():
    GPIO.cleanup()
    return "GPIO cleaned up successfully"

# === Clean Exit ===
if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    finally:
        GPIO.cleanup()
