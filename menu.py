import time
import board
import busio
import lgpio
import adafruit_ssd1306
from adafruit_tcs34725 import TCS34725
from mlx90614 import MLX90614
from PIL import Image, ImageDraw, ImageFont
import statistics

# -----------------------------
# GPIO CONFIGURATION
# -----------------------------
CHIP = 0
TRIG = 23
ECHO = 24
BUZZER = 18
BUTTON = 17

print("\n=== SMART SURFACE PROJECT INITIALIZATION ===")

# Initialize GPIO
h = lgpio.gpiochip_open(CHIP)
lgpio.gpio_claim_output(h, TRIG)
lgpio.gpio_claim_input(h, ECHO)
lgpio.gpio_claim_output(h, BUZZER)
lgpio.gpio_claim_input(h, BUTTON)

# -----------------------------
# I2C SETUP
# -----------------------------
i2c = busio.I2C(board.SCL, board.SDA)

# OLED
disp = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
disp.fill(0)
disp.show()
font = ImageFont.load_default()

# Color Sensor
color = TCS34725(i2c)

# Temperature Sensor
mlx = MLX90614(i2c)

# -----------------------------
# UTILITY FUNCTIONS
# -----------------------------
def show_oled(lines):
    image = Image.new("1", (disp.width, disp.height))
    draw = ImageDraw.Draw(image)
    y = 0
    for line in lines:
        draw.text((0, y), line, font=font, fill=255)
        y += 12
    disp.image(image)
    disp.show()

def buzzer_beep(n=1):
    for _ in range(n):
        lgpio.gpio_write(h, BUZZER, 1)
        time.sleep(0.2)
        lgpio.gpio_write(h, BUZZER, 0)
        time.sleep(0.2)

def ultrasonic_distance():
    lgpio.gpio_write(h, TRIG, 0)
    time.sleep(0.05)
    lgpio.gpio_write(h, TRIG, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, TRIG, 0)

    start_time = time.time()
    timeout = start_time + 0.04

    while lgpio.gpio_read(h, ECHO) == 0 and time.time() < timeout:
        pulse_start = time.time()
    while lgpio.gpio_read(h, ECHO) == 1 and time.time() < timeout:
        pulse_end = time.time()

    duration = pulse_end - pulse_start
    ambient_temp = mlx.get_amb_temp()
    speed_of_sound = 331.4 + (0.6 * ambient_temp)
    distance = (duration * speed_of_sound) / 2 * 100
    return distance, speed_of_sound

# -----------------------------
# TEST FUNCTIONS
# -----------------------------
def test_distance():
    buzzer_beep(1)
    readings = []
    for _ in range(5):
        d, _ = ultrasonic_distance()
        readings.append(d)
        time.sleep(0.2)
    avg = sum(readings) / len(readings)
    show_oled([f"Distance Test", f"Avg: {avg:.2f} cm"])
    buzzer_beep(2)

def test_shape():
    buzzer_beep(1)
    readings = []
    for _ in range(15):
        d, _ = ultrasonic_distance()
        readings.append(d)
        time.sleep(0.2)
    mean = statistics.mean(readings)
    std = statistics.stdev(readings)
    shape = "Flat" if std < 0.5 else "Irregular"
    show_oled([f"Shape Test", f"Mean: {mean:.2f}", f"Std: {std:.2f}", f"Shape: {shape}"])
    buzzer_beep(2)

def test_material():
    buzzer_beep(1)
    readings = []
    for _ in range(15):
        d, _ = ultrasonic_distance()
        readings.append(d)
        time.sleep(0.2)
    std = statistics.stdev(readings)
    material = "Absorbing" if std > 1 else "Reflective"
    show_oled([f"Material Test", f"Std Dev: {std:.2f}", f"Type: {material}"])
    buzzer_beep(2)

# -----------------------------
# MAIN MENU
# -----------------------------
while True:
    obj_temp = mlx.get_obj_temp()
    amb_temp = mlx.get_amb_temp()
    r, g, b = color.color_rgb_bytes
    _, speed = ultrasonic_distance()

    show_oled([
        "Select an Option:",
        "1. Distance",
        "2. Shape",
        "3. Material",
        f"Temp: {amb_temp:.1f}C | {obj_temp:.1f}C",
        f"RGB: {r},{g},{b}",
        f"Sound: {speed:.1f} m/s"
    ])

    choice = input("\nEnter choice (1-3): ")

    # Wait for button press
    show_oled(["Waiting for", "button press..."])
    while lgpio.gpio_read(h, BUTTON) == 1:
        time.sleep(0.1)

    # Run selected test
    if choice == "1":
        test_distance()
    elif choice == "2":
        test_shape()
    elif choice == "3":
        test_material()
    else:
        show_oled(["Invalid Choice"])
        time.sleep(1)
