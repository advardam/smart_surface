from flask import Flask, render_template, jsonify
import time, random
import board, busio, adafruit_tcs34725, adafruit_mlx90614, adafruit_ssd1306
from gpiozero import DistanceSensor, Button, Buzzer, Device
from gpiozero.pins.lgpio import LGPIOFactory
from PIL import Image, ImageDraw, ImageFont

# --- Use LGPIO for Raspberry Pi 5 ---
Device.pin_factory = LGPIOFactory()

app = Flask(__name__)

# === GPIO & SENSOR SETUP ===
sensor = DistanceSensor(echo=24, trigger=23, max_distance=2)
buzzer = Buzzer(18)
button = Button(17)

# === I2C & SENSORS ===
i2c = busio.I2C(board.SCL, board.SDA)
color_sensor = adafruit_tcs34725.TCS34725(i2c)
mlx = adafruit_mlx90614.MLX90614(i2c)

# === OLED DISPLAY ===
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
oled.fill(0)
oled.show()
font = ImageFont.load_default()

# === OLED UPDATE FUNCTION ===
def update_oled(distance, color_name, shape, amb_temp, obj_temp):
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.text((0, 0), f"Dist: {distance:.1f} cm", font=font, fill=255)
    draw.text((0, 15), f"Color: {color_name}", font=font, fill=255)
    draw.text((0, 30), f"Shape: {shape}", font=font, fill=255)
    draw.text((0, 45), f"Amb: {amb_temp:.1f}C Obj: {obj_temp:.1f}C", font=font, fill=255)
    oled.image(image)
    oled.show()

# === LOGIC HELPERS ===
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
    min_dist = 9999
    best_match = "Unknown"
    for name, (cr, cg, cb) in colors.items():
        dist = ((r - cr)**2 + (g - cg)**2 + (b - cb)**2)**0.5
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

# === ROUTES ===
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/measure")
def measure():
    buzzer.on()
    time.sleep(0.2)
    buzzer.off()

    distance = round(sensor.distance * 100, 2)
    r, g, b, c = color_sensor.color_raw
    color_name = get_color_name(r, g, b)
    shape = detect_shape(distance)

    amb_temp = mlx.ambient_temperature + random.uniform(-0.5, 0.5)
    obj_temp = mlx.object_temperature + random.uniform(-0.3, 0.3)

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
    sensor.close()
    buzzer.close()
    button.close()
    oled.fill(0)
    oled.show()
    return "GPIO cleaned up successfully"

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    finally:
        sensor.close()
        buzzer.close()
        button.close()
        oled.fill(0)
        oled.show()
