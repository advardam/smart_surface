#!/usr/bin/env python3
import lgpio
import time
import board
import busio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
import adafruit_mlx90614
import adafruit_tcs34725
import signal
import sys

# ====================================
# SMART SURFACE DIAGNOSTIC SCRIPT
# Raspberry Pi 5
# ====================================

# GPIO PIN DEFINITIONS
TRIG = 23
ECHO = 24
BUZZER = 18
BUTTON = 17

# Initialize GPIO chip
CHIP = 0
h = lgpio.gpiochip_open(CHIP)
lgpio.gpio_claim_output(h, TRIG)
lgpio.gpio_claim_input(h, ECHO)
lgpio.gpio_claim_output(h, BUZZER)
lgpio.gpio_claim_input(h, BUTTON)

print("\n=== SMART SURFACE PROJECT INITIALIZATION ===")

# ====================================
# OLED SETUP
# ====================================
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    disp = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)
    disp.fill(0)
    disp.show()

    width = disp.width
    height = disp.height
    image = Image.new("1", (width, height))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    def oled_message(msg1, msg2=""):
        draw.rectangle((0, 0, width, height), outline=0, fill=0)
        draw.text((0, 15), msg1, font=font, fill=255)
        if msg2:
            draw.text((0, 35), msg2, font=font, fill=255)
        disp.image(image)
        disp.show()

    oled_message("SMART SURFACE", "Initializing...")
    print("✅ OLED initialized successfully")

except Exception as e:
    print(f"❌ OLED init failed: {e}")
    disp = None
    oled_message = lambda a, b="": print(f"OLED: {a} {b}")

# ====================================
# MLX90614 SENSOR SETUP
# ====================================
try:
    mlx = adafruit_mlx90614.MLX90614(i2c)
    obj_temp = mlx.object_temperature
    amb_temp = mlx.ambient_temperature
    print(f"✅ MLX90614 OK - Object: {obj_temp:.2f}°C, Ambient: {amb_temp:.2f}°C")
except Exception as e:
    mlx = None
    print(f"❌ MLX90614 not detected: {e}")

# ====================================
# TCS34725 COLOR SENSOR SETUP
# ====================================
try:
    tcs = adafruit_tcs34725.TCS34725(i2c)
    tcs.integration_time = 100
    tcs.gain = 4
    color = tcs.color_rgb_bytes
    print(f"✅ TCS34725 OK - RGB: {color}")
except Exception as e:
    tcs = None
    print(f"❌ TCS34725 not detected: {e}")

# ====================================
# BUZZER TEST
# ====================================
print("🔔 Testing buzzer...")
lgpio.gpio_write(h, BUZZER, 1)
time.sleep(0.2)
lgpio.gpio_write(h, BUZZER, 0)
print("✅ Buzzer OK")

# ====================================
# ULTRASONIC FUNCTION
# ====================================
def get_distance():
    lgpio.gpio_write(h, TRIG, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, TRIG, 0)

    start_time = time.time()
    while lgpio.gpio_read(h, ECHO) == 0:
        start_time = time.time()

    stop_time = time.time()
    while lgpio.gpio_read(h, ECHO) == 1:
        stop_time = time.time()

    elapsed = stop_time - start_time
    distance = (elapsed * 34300) / 2
    return round(distance, 2)

# ====================================
# BUTTON HANDLER
# ====================================
def run_diagnostics():
    oled_message("Running Tests...", "")
    print("\n=== STARTING DIAGNOSTIC TESTS ===")

    # --- Ultrasonic ---
    try:
        readings = [get_distance() for _ in range(5)]
        avg_dist = sum(readings) / len(readings)
        print(f"📏 Ultrasonic Avg: {avg_dist:.2f} cm")
    except Exception as e:
        avg_dist = None
        print(f"❌ Ultrasonic error: {e}")

    # --- MLX90614 ---
    if mlx:
        obj_temp = mlx.object_temperature
        amb_temp = mlx.ambient_temperature
        print(f"🌡️ IR Temp: Obj {obj_temp:.2f}°C | Amb {amb_temp:.2f}°C")
    else:
        print("⚠️ MLX90614 not detected")

    # --- TCS34725 ---
    if tcs:
        r, g, b = tcs.color_rgb_bytes
        print(f"🎨 Color RGB: {r}, {g}, {b}")
    else:
        print("⚠️ TCS34725 not detected")

    oled_message("Diagnostics Done", "Check Console")
    lgpio.gpio_write(h, BUZZER, 1)
    time.sleep(0.3)
    lgpio.gpio_write(h, BUZZER, 0)

    print("✅ TEST COMPLETE\n")

# ====================================
# CLEANUP HANDLER
# ====================================
def cleanup(sig=None, frame=None):
    print("\n🧹 Cleaning up GPIO...")
    lgpio.gpio_write(h, BUZZER, 0)
    lgpio.gpiochip_close(h)
    if disp:
        disp.fill(0)
        disp.show()
    print("✅ Exit complete.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)

# ====================================
# MAIN LOOP
# ====================================
oled_message("SMART SURFACE", "Press Button to Test")

print("\n=== SYSTEM READY ===")
print("👉 Press button on GPIO17 to start diagnostics")

while True:
    if lgpio.gpio_read(h, BUTTON) == 0:  # Active LOW button
        run_diagnostics()
        oled_message("Press Button", "for next test")
        time.sleep(1.5)
    time.sleep(0.1)
