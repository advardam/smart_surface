import time, statistics, lgpio, board, busio
from adafruit_mlx90614 import MLX90614
import adafruit_tcs34725
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont

# -----------------------------
# GPIO Configuration
# -----------------------------
CHIP = 0
TRIG = 23
ECHO = 24
BUZZER = 18
BUTTON = 17

print("\n=== SMART SURFACE PROJECT INITIALIZATION ===")

# Open GPIO chip
h = lgpio.gpiochip_open(CHIP)
lgpio.gpio_claim_output(h, TRIG)
lgpio.gpio_claim_input(h, ECHO)
lgpio.gpio_claim_output(h, BUZZER)
lgpio.gpio_claim_input(h, BUTTON, lgpio.SET_PULL_UP)

# -----------------------------
# I2C + Sensor Setup
# -----------------------------
i2c = busio.I2C(board.SCL, board.SDA)

# MLX90614 (IR Temp)
mlx = MLX90614(i2c)

# TCS34725 (Color)
tcs = adafruit_tcs34725.TCS34725(i2c)

# OLED
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
oled.fill(0)
oled.show()
font = ImageFont.load_default()
image = Image.new("1", (128, 64))
draw = ImageDraw.Draw(image)

print("✅ OLED initialized successfully")


# -----------------------------
# Helper Functions
# -----------------------------
def beep(times=1):
    for _ in range(times):
        lgpio.gpio_write(h, BUZZER, 1)
        time.sleep(0.2)
        lgpio.gpio_write(h, BUZZER, 0)
        time.sleep(0.1)


def oled_display(line1, line2="", line3=""):
    draw.rectangle((0, 0, 128, 64), outline=0, fill=0)
    draw.text((0, 5), line1, font=font, fill=255)
    draw.text((0, 25), line2, font=font, fill=255)
    draw.text((0, 45), line3, font=font, fill=255)
    oled.image(image)
    oled.show()


def measure_distance():
    lgpio.gpio_write(h, TRIG, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, TRIG, 0)

    pulse_start = time.time()
    timeout = time.time() + 0.04
    while lgpio.gpio_read(h, ECHO) == 0:
        pulse_start = time.time()
        if time.time() > timeout:
            return None

    pulse_end = time.time()
    while lgpio.gpio_read(h, ECHO) == 1:
        pulse_end = time.time()
        if time.time() > timeout:
            return None

    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150
    return round(distance, 2)


def wait_for_button():
    oled_display("Waiting for button", "Press to start test")
    print("➡️ Waiting for button press...")
    while lgpio.gpio_read(h, BUTTON) == 1:
        time.sleep(0.05)
    time.sleep(0.3)
    print("✅ Button pressed!")


def speed_of_sound(temp):
    return 331 + (0.6 * temp)


# -----------------------------
# Sensor Status Display
# -----------------------------
def show_menu():
    obj_temp = mlx.object_temperature
    amb_temp = mlx.ambient_temperature
    rgb = tcs.color_rgb_bytes
    speed = speed_of_sound(amb_temp)
    oled_display(
        "Select Option:",
        f"Obj:{obj_temp:.1f}C Amb:{amb_temp:.1f}C",
        f"Speed:{speed:.1f}m/s RGB:{rgb}"
    )
    print("\n=== MAIN MENU ===")
    print(f"1. Check Distance")
    print(f"2. Check Shape (15 readings)")
    print(f"3. Check Material (15 readings)")
    print(f"Obj Temp: {obj_temp:.1f}°C | Amb Temp: {amb_temp:.1f}°C | Speed: {speed:.2f} m/s")
    print(f"Color RGB: {rgb}")


# -----------------------------
# Test Logic
# -----------------------------
def test_distance():
    wait_for_button()
    beep(1)
    dist = measure_distance()
    oled_display("Measuring...", "")
    if dist:
        oled_display(f"Distance: {dist} cm")
        print(f"📏 Distance: {dist} cm")
    else:
        oled_display("Distance: N/A")
    beep(2)


def test_shape():
    wait_for_button()
    beep(1)
    readings = []
    for _ in range(15):
        d = measure_distance()
        if d: readings.append(d)
        time.sleep(0.1)
    if readings:
        mean_val = statistics.mean(readings)
        std_dev = statistics.stdev(readings)
        shape = "Flat" if std_dev < 1 else "Curved" if std_dev < 3 else "Irregular"
        oled_display(f"Shape: {shape}", f"SD:{std_dev:.2f}")
        print(f"📊 Shape: {shape}, SD:{std_dev:.2f}")
    beep(2)


def test_material():
    wait_for_button()
    beep(1)
    readings = []
    for _ in range(15):
        d = measure_distance()
        if d: readings.append(d)
        time.sleep(0.1)
    if readings:
        mean_val = statistics.mean(readings)
        std_dev = statistics.stdev(readings)
        material = "Absorbing" if std_dev > 3 else "Reflective"
        oled_display(f"Material: {material}", f"SD:{std_dev:.2f}")
        print(f"🧱 Material: {material}, SD:{std_dev:.2f}")
    beep(2)


# -----------------------------
# Main Loop
# -----------------------------
while True:
    show_menu()
    choice = input("\nEnter choice (1-3): ").strip()
    if choice == "1":
        test_distance()
    elif choice == "2":
        test_shape()
    elif choice == "3":
        test_material()
    else:
        print("❌ Invalid option.")
    time.sleep(1)
