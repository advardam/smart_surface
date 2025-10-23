import time
import atexit
import RPi.GPIO as GPIO
from gpiozero import DistanceSensor, Button, Buzzer
from adafruit_tcs34725 import TCS34725
import board, busio, adafruit_mlx90614
from flask import Flask, render_template, jsonify
import Adafruit_SSD1306

# 🧹--- GPIO Cleanup Before Initialization ---
GPIO.setwarnings(False)
GPIO.cleanup()

# 🧹--- Register Cleanup on Exit ---
def safe_cleanup():
    try:
        GPIO.cleanup()
        print("🧹 GPIO cleaned successfully on exit.")
    except Exception as e:
        print("⚠️ GPIO cleanup error:", e)
atexit.register(safe_cleanup)

# --- Setup I2C and Sensors ---
i2c = busio.I2C(board.SCL, board.SDA)

# Color Sensor
color_sensor = TCS34725(i2c)

# Temperature Sensor (MLX90614)
mlx = adafruit_mlx90614.MLX90614(i2c)

# OLED Display
disp = Adafruit_SSD1306.SSD1306_128_64(rst=None)
disp.begin()
disp.clear()
disp.display()

# Ultrasonic Sensor + Button + Buzzer
sensor = DistanceSensor(echo=24, trigger=23, max_distance=2)
button = Button(17)
buzzer = Buzzer(27)

# Flask App
app = Flask(__name__)

# --- Helper Functions ---
def get_color_name(r, g, b):
    colors = {
        "Red": (255, 0, 0),
        "Green": (0, 255, 0),
        "Blue": (0, 0, 255),
        "Yellow": (255, 255, 0),
        "Cyan": (0, 255, 255),
        "Magenta": (255, 0, 255),
        "White": (255, 255, 255),
        "Black": (0, 0, 0),
    }
    closest_color = min(colors.keys(), key=lambda c: (r - colors[c][0])**2 + (g - colors[c][1])**2 + (b - colors[c][2])**2)
    return closest_color

def read_all_sensors():
    # Distance
    distance = round(sensor.distance * 100, 2)
    
    # Color
    r, g, b, c = color_sensor.color_rgb_bytes
    color_name = get_color_name(r, g, b)
    
    # Temperature
    ambient_temp = round(mlx.ambient_temperature, 2)
    object_temp = round(mlx.object_temperature, 2)

    # Show on OLED
    disp.clear()
    disp.display()
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('1', (disp.width, disp.height))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    
    draw.text((0, 0), f"Dist: {distance} cm", font=font, fill=255)
    draw.text((0, 16), f"Color: {color_name}", font=font, fill=255)
    draw.text((0, 32), f"Amb: {ambient_temp}°C", font=font, fill=255)
    draw.text((0, 48), f"Obj: {object_temp}°C", font=font, fill=255)
    disp.image(image)
    disp.display()

    return {
        "distance": distance,
        "color": color_name,
        "ambient_temp": ambient_temp,
        "object_temp": object_temp
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/check', methods=['GET'])
def check_readings():
    buzzer.on()
    time.sleep(0.2)
    buzzer.off()
    data = read_all_sensors()
    return jsonify(data)

if __name__ == "__main__":
    print("🚀 Smart Surface Flask server running...")
    app.run(host='0.0.0.0', port=5000, debug=True)
