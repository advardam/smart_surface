import time
import board
import busio
import lgpio
import adafruit_tcs34725
import adafruit_mlx90614
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
import atexit

# -----------------------------
# GPIO CONFIGURATION
# -----------------------------
CHIP = 0
TRIG = 23
ECHO = 24
BUZZER = 18
BUTTON = 17

print("\n=== SMART SURFACE PROJECT INITIALIZATION ===")

# Open GPIO chip
h = lgpio.gpiochip_open(CHIP)

def safe_gpio_claim_output(handle, pin):
    try:
        lgpio.gpio_claim_output(handle, pin)
        print(f"✅ Output pin {pin} ready")
    except Exception as e:
        print(f"⚠️ GPIO {pin} busy — continuing...")
    return handle

def safe_gpio_claim_input(handle, pin):
    try:
        lgpio.gpio_claim_input(handle, pin, lgpio.SET_PULL_UP)
        print(f"✅ Input pin {pin} ready (with pull-up)")
    except Exception as e:
        print(f"⚠️ GPIO {pin} busy — continuing...")

# Setup pins
h = safe_gpio_claim_output(h, TRIG)
safe_gpio_claim_input(h, ECHO)
h = safe_gpio_claim_output(h, BUZZER)
safe_gpio_claim_input(h, BUTTON)

# -----------------------------
# OLED SETUP
# -----------------------------
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
    oled.fill(0)
    oled.show()
    print("✅ OLED initialized successfully")
except Exception as e:
    print(f"❌ OLED init failed: {e}")

# -----------------------------
# SENSOR SETUP (MLX90614 + TCS34725)
# -----------------------------
try:
    mlx = adafruit_mlx90614.MLX90614(i2c)
    obj_temp = mlx.object_temperature
    amb_temp = mlx.ambient_temperature
    print(f"✅ MLX90614 OK - Obj: {obj_temp:.2f}°C | Amb: {amb_temp:.2f}°C")
except Exception as e:
    print(f"❌ MLX90614 error: {e}")

try:
    color = adafruit_tcs34725.TCS34725(i2c)
    rgb = color.color_rgb_bytes
    print(f"✅ TCS34725 OK - RGB: {rgb}")
except Exception as e:
    print(f"❌ TCS34725 error: {e}")

# -----------------------------
# BUZZER TEST
# -----------------------------
print("🔔 Testing buzzer...")
lgpio.gpio_write(h, BUZZER, 1)
time.sleep(0.2)
lgpio.gpio_write(h, BUZZER, 0)
print("✅ Buzzer OK")

# -----------------------------
# OLED DISPLAY HELPER
# -----------------------------
def oled_display(lines):
    oled.fill(0)
    image = Image.new("1", (128, 64))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    y = 0
    for line in lines:
        draw.text((0, y), line, font=font, fill=255)
        y += 10
    oled.image(image)
    oled.show()

# -----------------------------
# WAIT FOR BUTTON PRESS
# -----------------------------
def wait_for_button(test_name):
    oled_display([test_name, "", "Press button to start"])
    print(f"➡️ Waiting for button press to start: {test_name}")
    while lgpio.gpio_read(h, BUTTON) == 1:
        time.sleep(0.05)
    print("✅ Button pressed — starting test...")
    lgpio.gpio_write(h, BUZZER, 1)
    time.sleep(0.2)
    lgpio.gpio_write(h, BUZZER, 0)
    time.sleep(0.3)

# -----------------------------
# MAIN MENU
# -----------------------------
while True:
    try:
        obj_temp = mlx.object_temperature
        amb_temp = mlx.ambient_temperature
        rgb = color.color_rgb_bytes

        speed_sound = 331 + (0.6 * amb_temp)
        oled_display([
            "SMART SURFACE MENU",
            "",
            "1. Distance Test",
            "2. Shape Detection",
            "3. Material Type",
            "",
            f"T={obj_temp:.1f}/{amb_temp:.1f}C",
            f"RGB={rgb}",
            f"Speed={speed_sound:.1f} m/s"
        ])

        print("\nSelect an option:")
        print("1 - Distance")
        print("2 - Shape")
        print("3 - Material")
        choice = input("Enter choice (1/2/3): ")

        if choice == "1":
            wait_for_button("Distance Test")
            oled_display(["Distance Test Running..."])
            # Add your distance logic here
            time.sleep(2)
            lgpio.gpio_write(h, BUZZER, 1)
            time.sleep(0.2)
            lgpio.gpio_write(h, BUZZER, 0)
            time.sleep(0.2)
            lgpio.gpio_write(h, BUZZER, 1)
            time.sleep(0.2)
            lgpio.gpio_write(h, BUZZER, 0)
            oled_display(["✅ Distance Test Done"])

        elif choice == "2":
            wait_for_button("Shape Detection Test")
            oled_display(["Shape Test Running..."])
            # Add shape detection logic here
            time.sleep(2)
            lgpio.gpio_write(h, BUZZER, 1)
            time.sleep(0.2)
            lgpio.gpio_write(h, BUZZER, 0)
            time.sleep(0.2)
            lgpio.gpio_write(h, BUZZER, 1)
            time.sleep(0.2)
            lgpio.gpio_write(h, BUZZER, 0)
            oled_display(["✅ Shape Test Done"])

        elif choice == "3":
            wait_for_button("Material Type Test")
            oled_display(["Material Test Running..."])
            # Add material test logic here
            time.sleep(2)
            lgpio.gpio_write(h, BUZZER, 1)
            time.sleep(0.2)
            lgpio.gpio_write(h, BUZZER, 0)
            time.sleep(0.2)
            lgpio.gpio_write(h, BUZZER, 1)
            time.sleep(0.2)
            lgpio.gpio_write(h, BUZZER, 0)
            oled_display(["✅ Material Test Done"])

        else:
            print("Invalid choice!")

    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f"⚠️ Error: {e}")

# -----------------------------
# CLEANUP
# -----------------------------
def cleanup():
    try:
        lgpio.gpiochip_close(h)
        print("\n🧹 GPIO released cleanly.")
    except Exception as e:
        print(f"⚠️ Cleanup issue: {e}")

atexit.register(cleanup)
