import time
import lgpio
import board
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
import adafruit_tcs34725
import adafruit_mlx90614
import statistics

# -----------------------------
# GPIO + I2C Setup
# -----------------------------
CHIP = 0
TRIG = 23
ECHO = 24
BUZZER = 18
BUTTON = 17

h = lgpio.gpiochip_open(CHIP)
lgpio.gpio_claim_output(h, TRIG)
lgpio.gpio_claim_input(h, ECHO)
lgpio.gpio_claim_output(h, BUZZER)
lgpio.gpio_claim_input(h, BUTTON)

i2c = board.I2C()
disp = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
mlx = adafruit_mlx90614.MLX90614(i2c)
tcs = adafruit_tcs34725.TCS34725(i2c)

font = ImageFont.load_default()

def beep(n=1):
    for _ in range(n):
        lgpio.gpio_write(h, BUZZER, 1)
        time.sleep(0.15)
        lgpio.gpio_write(h, BUZZER, 0)
        time.sleep(0.15)

def measure_distance():
    lgpio.gpio_write(h, TRIG, 0)
    time.sleep(0.05)
    lgpio.gpio_write(h, TRIG, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, TRIG, 0)

    start = time.time()
    while lgpio.gpio_read(h, ECHO) == 0:
        start = time.time()
    while lgpio.gpio_read(h, ECHO) == 1:
        stop = time.time()

    duration = stop - start
    temp = mlx.ambient_temperature
    speed = 331 + 0.6 * temp
    distance = (duration * speed * 100) / 2
    return round(distance, 2), speed

def display_menu():
    obj_temp = mlx.object_temperature
    amb_temp = mlx.ambient_temperature
    color = tcs.color_rgb_bytes
    speed = 331 + 0.6 * amb_temp

    disp.fill(0)
    image = Image.new("1", (disp.width, disp.height))
    draw = ImageDraw.Draw(image)
    draw.text((0, 0), "SMART SURFACE MENU", font=font, fill=255)
    draw.text((0, 12), "1.Distance", font=font, fill=255)
    draw.text((0, 22), "2.Shape (15 readings)", font=font, fill=255)
    draw.text((0, 32), "3.Material (15 readings)", font=font, fill=255)
    draw.text((0, 44), f"Tobj:{obj_temp:.1f}C Tamb:{amb_temp:.1f}C", font=font, fill=255)
    draw.text((0, 54), f"RGB:{color} v={speed:.1f}m/s", font=font, fill=255)
    disp.image(image)
    disp.show()

def wait_for_button():
    print("➡️ Press button to start...")
    while lgpio.gpio_read(h, BUTTON) == 1:
        time.sleep(0.05)

# -----------------------------
# Main Loop
# -----------------------------
while True:
    display_menu()
    print("\n=== SMART SURFACE MENU ===")
    print("1. Measure Distance")
    print("2. Detect Shape (15 readings)")
    print("3. Detect Material (15 readings)")
    choice = input("Select option (1-3): ")

    wait_for_button()
    beep(1)

    if choice == "1":
        dist, speed = measure_distance()
        print(f"📏 Distance: {dist} cm | Speed: {speed:.2f} m/s")
        image = Image.new("1", (disp.width, disp.height))
        draw = ImageDraw.Draw(image)
        draw.text((0, 0), "Distance Measured", font=font, fill=255)
        draw.text((0, 20), f"{dist} cm", font=font, fill=255)
        disp.image(image)
        disp.show()

    elif choice == "2":
        readings = []
        for i in range(15):
            d, _ = measure_distance()
            readings.append(d)
            print(f"Reading {i+1}: {d} cm")
            time.sleep(0.2)
        mean_val = statistics.mean(readings)
        stdev_val = statistics.stdev(readings)
        shape = "Flat Surface" if stdev_val < 0.5 else "Curved Surface"
        print(f"Shape: {shape} | SD={stdev_val:.2f}")
        image = Image.new("1", (disp.width, disp.height))
        draw = ImageDraw.Draw(image)
        draw.text((0, 0), "Shape Detection", font=font, fill=255)
        draw.text((0, 20), f"{shape}", font=font, fill=255)
        disp.image(image)
        disp.show()

    elif choice == "3":
        readings = []
        for i in range(15):
            d, _ = measure_distance()
            readings.append(d)
            print(f"Reading {i+1}: {d} cm")
            time.sleep(0.2)
        stdev_val = statistics.stdev(readings)
        material = "Absorbing" if stdev_val > 1.0 else "Reflective"
        print(f"Material: {material} | SD={stdev_val:.2f}")
        image = Image.new("1", (disp.width, disp.height))
        draw = ImageDraw.Draw(image)
        draw.text((0, 0), "Material Type", font=font, fill=255)
        draw.text((0, 20), f"{material}", font=font, fill=255)
        disp.image(image)
        disp.show()

    else:
        print("❌ Invalid choice, try again.")

    beep(2)
    time.sleep(2)
