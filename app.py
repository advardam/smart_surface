import time
import statistics
import lgpio
import Adafruit_SSD1306
from flask import Flask, render_template, jsonify
from PIL import Image, ImageDraw, ImageFont
import atexit

# -----------------------------
# GPIO SETUP
# -----------------------------
CHIP = 0
TRIG = 23
ECHO = 24
BUZZER = 18

def safe_gpio_claim_output(handle, pin):
    try:
        lgpio.gpio_claim_output(handle, pin)
        print(f"✅ Output pin {pin} ready")
    except lgpio.error as e:
        print(f"⚠️ GPIO {pin} busy — trying to re-open chip and reclaim...")
        try:
            lgpio.gpiochip_close(handle)
            time.sleep(0.2)
            handle = lgpio.gpiochip_open(CHIP)
            lgpio.gpio_claim_output(handle, pin)
            print(f"✅ GPIO {pin} reclaimed successfully")
        except Exception as e2:
            print(f"❌ Could not reclaim GPIO {pin}: {e2}")
    return handle

def safe_gpio_claim_input(handle, pin):
    try:
        lgpio.gpio_claim_input(handle, pin)
        print(f"✅ Input pin {pin} ready")
    except lgpio.error as e:
        print(f"⚠️ GPIO {pin} busy — continuing (reads may fail).")

h = lgpio.gpiochip_open(CHIP)
h = safe_gpio_claim_output(h, TRIG)
safe_gpio_claim_input(h, ECHO)
h = safe_gpio_claim_output(h, BUZZER)

# -----------------------------
# OLED SETUP
# -----------------------------
try:
    disp = Adafruit_SSD1306.SSD1306_128_64(rst=None)
    disp.begin()
    disp.clear()
    disp.display()
    print("✅ OLED initialized successfully")
except Exception as e:
    print(f"❌ OLED initialization failed: {e}")

# -----------------------------
# OLED DISPLAY FUNCTION
# -----------------------------
def display_message(line1="", line2="", line3=""):
    try:
        width = disp.width
        height = disp.height
        image = Image.new("1", (width, height))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        draw.text((0, 0), line1, font=font, fill=255)
        draw.text((0, 16), line2, font=font, fill=255)
        draw.text((0, 32), line3, font=font, fill=255)

        disp.image(image)
        disp.display()
    except Exception as e:
        print(f"⚠️ OLED display error: {e}")

# -----------------------------
# FLASK DASHBOARD SETUP
# -----------------------------
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/measure_distance')
def measure_distance():
    # Example placeholder: actual ultrasonic logic can be added here
    lgpio.gpio_write(h, BUZZER, 1)
    time.sleep(0.1)
    lgpio.gpio_write(h, BUZZER, 0)

    distance = 25.3  # Replace with actual measured value
    display_message("Distance:", f"{distance:.2f} cm", "Measured")
    print(f"📏 Distance measured: {distance:.2f} cm")

    return jsonify({'distance': distance})

# Add routes for shape detection, material detection later

# -----------------------------
# CLEANUP HANDLER
# -----------------------------
def cleanup():
    try:
        lgpio.gpiochip_close(h)
        print("🧹 GPIOs released successfully.")
    except Exception as e:
        print(f"⚠️ GPIO cleanup error: {e}")

atexit.register(cleanup)

# -----------------------------
# RUN SERVER
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
