from flask import Flask, render_template, jsonify
from gpiozero import DistanceSensor, Button, Buzzer
import board, busio, adafruit_tcs34725, adafruit_mlx90614, adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
import statistics, time

app = Flask(__name__)

# Initialize sensors and components
sensor = DistanceSensor(echo=24, trigger=23, max_distance=2)
button = Button(17)
buzzer = Buzzer(18)

i2c = busio.I2C(board.SCL, board.SDA)
color_sensor = adafruit_tcs34725.TCS34725(i2c)
temp_sensor = adafruit_mlx90614.MLX90614(i2c)
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)

data_log = {"distance": [], "shape": [], "material": []}
summary_data = {"accuracy": "", "recommendation": "", "badge": ""}

# --- OLED Helper Functions ---
def oled_display(lines):
    oled.fill(0)
    oled.show()
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    y = 0
    for line in lines:
        draw.text((0, y), line, font=font, fill=255)
        y += 12
    oled.image(image)
    oled.show()

# --- Hardware Utility Functions ---
def beep():
    buzzer.on()
    time.sleep(0.15)
    buzzer.off()

def read_distance(n=1, delay=0.1):
    readings = []
    for _ in range(n):
        dist = round(sensor.distance * 100, 2)
        readings.append(dist)
        time.sleep(delay)
    return readings

def read_color_temp():
    r, g, b = color_sensor.color_rgb_bytes
    color_temp = color_sensor.color_temperature
    lux = color_sensor.lux
    return r, g, b, color_temp, lux

def read_temperature():
    amb = round(temp_sensor.ambient_temperature, 2)
    obj = round(temp_sensor.object_temperature, 2)
    return amb, obj

def ultrasonic_speed(temp_c):
    return round(331.4 + (0.6 * temp_c), 2)

# --- Analysis Functions ---
def analyze_shape():
    beep()
    readings = read_distance(15, 0.2)
    mean = statistics.mean(readings)
    stdev = statistics.stdev(readings)
    if stdev < 0.3:
        shape = "Flat Surface"
    elif stdev < 1.0:
        shape = "Curved Surface"
    else:
        shape = "Irregular Shape"
    data_log["shape"] = readings
    oled_display(["Shape Test", f"Result: {shape}", f"SD: {round(stdev,2)}"])
    return shape, mean, stdev

def analyze_material():
    beep()
    readings = read_distance(20, 0.2)
    mean = statistics.mean(readings)
    stdev = statistics.stdev(readings)
    if stdev < 0.2:
        mat = "Reflective Material"
    elif stdev < 1.0:
        mat = "Moderate Absorber"
    else:
        mat = "Ultrasonic Absorber"
    data_log["material"] = readings
    oled_display(["Material Test", f"Result: {mat}", f"SD: {round(stdev,2)}"])
    return mat, mean, stdev

def analyze_accuracy():
    amb, obj = read_temperature()
    diff = abs(obj - amb)
    speed = ultrasonic_speed(amb)
    if diff < 1.5:
        badge, acc, rec = ("success", "Good", "Stable environment, minimal effect on accuracy.")
    elif diff < 3.0:
        badge, acc, rec = ("warning", "Moderate", "Slight temperature difference; may affect readings.")
    else:
        badge, acc, rec = ("danger", "Poor", "High temp variation — ultrasonic accuracy reduced.")
    summary_data.update({
        "accuracy": acc,
        "recommendation": rec,
        "badge": badge,
        "speed": speed,
        "temp_diff": diff
    })
    oled_display([
        f"Accuracy: {acc}",
        f"ΔT: {round(diff,2)}°C",
        f"Speed: {speed} m/s"
    ])

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/measure_distance')
def measure_distance():
    beep()
    dist = read_distance()[0]
    r, g, b, color_temp, lux = read_color_temp()
    amb, obj = read_temperature()
    analyze_accuracy()
    data_log["distance"].append(dist)
    oled_display([f"Distance: {dist}cm", f"ObjT:{obj}°C", f"AmbT:{amb}°C"])
    return jsonify({
        "distance": dist,
        "color": f"R:{r} G:{g} B:{b}",
        "color_temp": color_temp,
        "lux": lux,
        "amb_temp": amb,
        "obj_temp": obj,
        "summary": summary_data
    })

@app.route('/check_shape')
def check_shape():
    shape, mean, stdev = analyze_shape()
    analyze_accuracy()
    return jsonify({"shape": shape, "readings": data_log["shape"], "summary": summary_data})

@app.route('/check_material')
def check_material():
    mat, mean, stdev = analyze_material()
    analyze_accuracy()
    return jsonify({"material": mat, "readings": data_log["material"], "summary": summary_data})

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    finally:
        sensor.close()
        buzzer.close()
        oled.fill(0)
        oled.show()
