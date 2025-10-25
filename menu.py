#!/usr/bin/env python3
"""
Smart Surface Menu (Raspberry Pi 5)

- Menu with 3 options:
  1) Distance
  2) Shape (15 readings -> mean/stddev -> classify)
  3) Material (15 readings -> mean/stddev -> classify Absorbing/Reflective)

- Waits for physical button press to start each test.
- Buzzer: 1 beep at start, 2 beeps at finish.
- Shows color, temps, speed-of-sound on OLED during menu and results on OLED after test.
- Uses: lgpio, adafruit_ssd1306, adafruit_mlx90614, adafruit_tcs34725
"""

import time
import sys
import math
import statistics
import lgpio
import board
import busio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
import adafruit_mlx90614
import adafruit_tcs34725
import signal

# -----------------------
# Pins / constants
# -----------------------
CHIP = 0
TRIG = 23    # output
ECHO = 24    # input
BUZZER = 18  # output
BUTTON = 17  # input, physical button to start test (active LOW)

READINGS_COUNT = 15  # per your request for both shape and material

# -----------------------
# Helper: safe lgpio setup
# -----------------------
def open_chip():
    try:
        return lgpio.gpiochip_open(CHIP)
    except Exception as e:
        print("ERROR: cannot open gpiochip:", e)
        sys.exit(1)

def safe_claim_output(handle, pin, initial=0):
    try:
        lgpio.gpio_claim_output(handle, pin, initial)
        print(f"✅ Output pin {pin} ready")
    except lgpio.error as e:
        print(f"⚠️ pin {pin} busy or claim failed: {e}. Trying to re-open chip and reclaim...")
        try:
            lgpio.gpiochip_close(handle)
            time.sleep(0.2)
            handle = open_chip()
            lgpio.gpio_claim_output(handle, pin, initial)
            print(f"✅ Reclaimed output pin {pin}")
        except Exception as e2:
            print(f"❌ Could not reclaim output pin {pin}: {e2}")
    return handle

def safe_claim_input(handle, pin):
    try:
        lgpio.gpio_claim_input(handle, pin)
        print(f"✅ Input pin {pin} ready")
    except lgpio.error as e:
        print(f"⚠️ pin {pin} busy or claim failed: {e} (continuing)")

# -----------------------
# Initialize GPIO and sensors
# -----------------------
h = open_chip()
h = safe_claim_output(h, TRIG)
safe_claim_input(h, ECHO)
h = safe_claim_output(h, BUZZER)
safe_claim_input(h, BUTTON)

# -----------------------
# OLED init (adafruit_ssd1306, I2C)
# -----------------------
i2c = busio.I2C(board.SCL, board.SDA)
try:
    disp = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)
    disp.fill(0)
    disp.show()
    oled_width = disp.width
    oled_height = disp.height
    font = ImageFont.load_default()
    def oled_show(line1="", line2="", line3=""):
        image = Image.new("1", (oled_width, oled_height))
        draw = ImageDraw.Draw(image)
        draw.text((0, 6), str(line1), font=font, fill=255)
        draw.text((0, 26), str(line2), font=font, fill=255)
        draw.text((0, 46), str(line3), font=font, fill=255)
        disp.image(image)
        disp.show()
    print("✅ OLED initialized")
except Exception as e:
    disp = None
    def oled_show(a="", b="", c=""):
        print("OLED:", a, b, c)
    print("⚠️ OLED init failed:", e)

# -----------------------
# MLX90614 and TCS34725 init
# -----------------------
try:
    mlx = adafruit_mlx90614.MLX90614(i2c)
    print("✅ MLX90614 detected")
except Exception as e:
    mlx = None
    print("⚠️ MLX90614 init failed:", e)

try:
    tcs = adafruit_tcs34725.TCS34725(i2c)
    tcs.integration_time = 100
    tcs.gain = 4
    print("✅ TCS34725 detected")
except Exception as e:
    tcs = None
    print("⚠️ TCS34725 init failed:", e)

# -----------------------
# Utility functions
# -----------------------
def read_temps():
    if mlx:
        try:
            ambient = mlx.ambient_temperature
            obj = mlx.object_temperature
            return round(ambient, 2), round(obj, 2)
        except Exception as e:
            print("MLX read error:", e)
    # fallback simulated values
    ambient = round(25 + (time.time() % 5) - 2, 2)
    obj = round(ambient + 0.5, 2)
    return ambient, obj

def read_color_name():
    if tcs:
        try:
            r, g, b = tcs.color_rgb_bytes
            # quick name from dominant channel
            if r > g and r > b:
                name = "Red"
            elif g > r and g > b:
                name = "Green"
            elif b > r and b > g:
                name = "Blue"
            else:
                name = "Unknown"
            return (r, g, b), name
        except Exception as e:
            print("TCS read error:", e)
    # fallback simulated
    return (0,0,0), "Unknown"

def speed_of_sound_m_s(ambient_c):
    return 331.0 + 0.6 * ambient_c

# Ultrasonic single measurement using ambient temp for speed calculation
def measure_distance_once(ambient_temp_c=None, timeout_s=0.05):
    # Send trigger pulse
    try:
        lgpio.gpio_write(h, TRIG, 0)
        time.sleep(0.0002)
        lgpio.gpio_write(h, TRIG, 1)
        time.sleep(0.00001)
        lgpio.gpio_write(h, TRIG, 0)
    except Exception as e:
        print("Trigger write error:", e)
        return None

    start = time.time()
    timeout = start + timeout_s
    # wait for echo high
    while lgpio.gpio_read(h, ECHO) == 0:
        start = time.time()
        if time.time() > timeout:
            return None
    # wait for echo low
    end = time.time()
    while lgpio.gpio_read(h, ECHO) == 1:
        end = time.time()
        if time.time() > timeout:
            return None

    elapsed = end - start  # seconds
    ambient = ambient_temp_c if ambient_temp_c is not None else read_temps()[0]
    speed = speed_of_sound_m_s(ambient)  # m/s
    # distance in cm: elapsed * speed (m/s) * 100cm/m / 2
    distance_cm = (elapsed * speed * 100.0) / 2.0
    return round(distance_cm, 2)

def beep(times=1, on_time=0.12, off_time=0.08):
    for i in range(times):
        try:
            lgpio.gpio_write(h, BUZZER, 1)
            time.sleep(on_time)
            lgpio.gpio_write(h, BUZZER, 0)
        except Exception as e:
            print("Buzzer error:", e)
        if i < times-1:
            time.sleep(off_time)

# -----------------------
# Button wait helper
# -----------------------
def wait_for_button_press(poll_interval=0.05):
    # Informative loop: show status on OLED
    oled_show("Waiting for button", "Press to START", "")
    print("Waiting for physical button press (GPIO17).")
    while True:
        try:
            val = lgpio.gpio_read(h, BUTTON)
        except Exception as e:
            print("Button read error:", e)
            val = 1
        # Assumes active LOW (button connects pin to GND when pressed)
        if val == 0:
            # debounce
            time.sleep(0.05)
            if lgpio.gpio_read(h, BUTTON) == 0:
                time.sleep(0.05)
                return
        time.sleep(poll_interval)

# -----------------------
# Classification helpers
# -----------------------
def classify_shape(std_dev):
    if std_dev < 1.0:
        return "Flat"
    elif std_dev < 3.0:
        return "Curved"
    else:
        return "Irregular"

def classify_material(std_dev):
    # heuristic: larger variation => absorbing
    return "Absorbing" if std_dev > 3.0 else "Reflective"

# -----------------------
# Actions for menu options
# -----------------------
def option_distance():
    ambient, obj = read_temps()
    (r,g,b), cname = read_color_name()
    speed = speed_of_sound_m_s(ambient)
    oled_show("Option: Distance", f"Color: {cname}", f"Amb:{ambient}C Speed:{round(speed,2)}")
    print(f"\nSelected: Distance\nColor: {cname} | Ambient: {ambient} C | Object: {obj} C | Speed: {round(speed,2)} m/s")
    print("Press physical button to start the distance measurement.")
    wait_for_button_press()
    # start beep once
    beep(times=1)
    # single reading (you can take average of a few if desired)
    readings = []
    for _ in range(3):
        d = measure_distance_once(ambient)
        if d is None:
            d = 0.0
        readings.append(d)
        time.sleep(0.08)
    mean_d = round(statistics.mean(readings), 2)
    oled_show("Distance Result", f"{mean_d} cm", f"Color:{cname}")
    print(f"Distance readings: {readings}\nMean distance: {mean_d} cm")
    # finish beep twice
    beep(times=2)
    return {"readings": readings, "mean": mean_d, "color": cname, "ambient": ambient, "object_temp": obj, "speed_m_s": round(speed,2)}

def option_shape():
    ambient, obj = read_temps()
    (r,g,b), cname = read_color_name()
    speed = speed_of_sound_m_s(ambient)
    oled_show("Option: Shape", f"Color:{cname}", f"Amb:{ambient}C Speed:{round(speed,2)}")
    print(f"\nSelected: Shape\nColor: {cname} | Ambient: {ambient} C | Object: {obj} C | Speed: {round(speed,2)} m/s")
    print(f"Press physical button to start the shape test ({READINGS_COUNT} readings).")
    wait_for_button_press()
    beep(times=1)  # start
    readings = []
    for i in range(READINGS_COUNT):
        d = measure_distance_once(ambient)
        if d is None:
            d = 0.0
        readings.append(d)
        print(f"[{i+1}/{READINGS_COUNT}] {d} cm")
        # update OLED with a live summary every few readings
        if i % 5 == 0:
            oled_show(f"Shape test {i+1}/{READINGS_COUNT}", f"Last:{d} cm", f"Color:{cname}")
        time.sleep(0.08)
    mean_val = round(statistics.mean(readings), 2)
    std_dev = round(statistics.stdev(readings), 3) if len(readings) > 1 else 0.0
    shape = classify_shape(std_dev)
    oled_show(f"Shape: {shape}", f"Mean:{mean_val} cm", f"Std:{std_dev}")
    print(f"All readings: {readings}")
    print(f"Mean: {mean_val} cm | StdDev: {std_dev} -> Shape: {shape}")
    beep(times=2)  # finished
    return {"readings": readings, "mean": mean_val, "std_dev": std_dev, "shape": shape, "color": cname, "ambient": ambient, "object_temp": obj, "speed_m_s": round(speed,2)}

def option_material():
    ambient, obj = read_temps()
    (r,g,b), cname = read_color_name()
    speed = speed_of_sound_m_s(ambient)
    oled_show("Option: Material", f"Color:{cname}", f"Amb:{ambient}C Speed:{round(speed,2)}")
    print(f"\nSelected: Material\nColor: {cname} | Ambient: {ambient} C | Object: {obj} C | Speed: {round(speed,2)} m/s")
    print(f"Press physical button to start the material test ({READINGS_COUNT} readings).")
    wait_for_button_press()
    beep(times=1)
    readings = []
    for i in range(READINGS_COUNT):
        d = measure_distance_once(ambient)
        if d is None:
            d = 0.0
        readings.append(d)
        print(f"[{i+1}/{READINGS_COUNT}] {d} cm")
        if i % 5 == 0:
            oled_show(f"Material test {i+1}/{READINGS_COUNT}", f"Last:{d} cm", f"Color:{cname}")
        time.sleep(0.08)
    mean_val = round(statistics.mean(readings), 2)
    std_dev = round(statistics.stdev(readings), 3) if len(readings) > 1 else 0.0
    material = classify_material(std_dev)
    oled_show(f"Material: {material}", f"Mean:{mean_val} cm", f"Std:{std_dev}")
    print(f"All readings: {readings}")
    print(f"Mean: {mean_val} cm | StdDev: {std_dev} -> Material: {material}")
    beep(times=2)
    return {"readings": readings, "mean": mean_val, "std_dev": std_dev, "material": material, "color": cname, "ambient": ambient, "object_temp": obj, "speed_m_s": round(speed,2)}

# -----------------------
# Menu loop
# -----------------------
def menu_loop():
    while True:
        ambient, obj = read_temps()
        (r,g,b), cname = read_color_name()
        speed = speed_of_sound_m_s(ambient)
        oled_show("SMART SURFACE MENU", f"Color:{cname} Temp:{round(obj,2)}C", f"Speed:{round(speed,2)} m/s")
        print("\n==== SMART SURFACE MENU ====")
        print("1) Check Distance")
        print("2) Check Shape (15 readings)")
        print("3) Check Material (15 readings)")
        print("q) Quit")
        choice = input("Select option [1/2/3/q]: ").strip().lower()
        if choice == "1":
            res = option_distance()
            print("Result:", res)
        elif choice == "2":
            res = option_shape()
            print("Result:", res)
        elif choice == "3":
            res = option_material()
            print("Result:", res)
        elif choice == "q":
            print("Quitting...")
            break
        else:
            print("Invalid selection")
        time.sleep(0.3)

# -----------------------
# Cleanup
# -----------------------
def cleanup(sig=None, frame=None):
    print("\nCleaning up...")
    try:
        lgpio.gpio_write(h, BUZZER, 0)
    except Exception:
        pass
    try:
        lgpio.gpiochip_close(h)
    except Exception:
        pass
    if disp:
        disp.fill(0)
        disp.show()
    print("Done. Exiting.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)

# -----------------------
# Start
# -----------------------
if __name__ == "__main__":
    try:
        menu_loop()
    finally:
        cleanup()
