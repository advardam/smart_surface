import lgpio
import Adafruit_SSD1306
import time
from PIL import Image, ImageDraw, ImageFont
import atexit

# -----------------------------
# GPIO CONFIGURATION
# -----------------------------
CHIP = 0
TRIG = 23
ECHO = 24
BUZZER = 18

print("\n=== SMART SURFACE PROJECT INITIALIZATION ===")

# Open GPIO chip
h = lgpio.gpiochip_open(CHIP)

# Safe GPIO claim functions
def safe_gpio_claim_output(handle, pin):
    try:
        lgpio.gpio_claim_output(handle, pin)
        print(f"✅ Output pin {pin} ready")
    except lgpio.error as e:
        print(f"⚠️ GPIO {pin} busy — trying to recover...")
        try:
            lgpio.gpiochip_close(handle)
            time.sleep(0.2)
            handle = lgpio.gpiochip_open(CHIP)
            lgpio.gpio_claim_output(handle, pin)
            print(f"✅ Reclaimed GPIO {pin}")
        except Exception as e2:
            print(f"❌ Could not reclaim GPIO {pin}: {e2}")
    return handle

def safe_gpio_claim_input(handle, pin):
    try:
        lgpio.gpio_claim_input(handle, pin)
        print(f"✅ Input pin {pin} ready")
    except lgpio.error:
        print(f"⚠️ GPIO {pin} busy or already in use")

# Initialize pins
h = safe_gpio_claim_output(h, TRIG)
safe_gpio_claim_input(h, ECHO)
h = safe_gpio_claim_output(h, BUZZER)

# -----------------------------
# OLED DISPLAY SETUP
# -----------------------------
try:
    disp = Adafruit_SSD1306.SSD1306_128_64(rst=None)
    disp.begin()
    disp.clear()
    disp.display()

    width = disp.width
    height = disp.height
    image = Image.new('1', (width, height))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((0, 0), "Smart Surface Project", font=font, fill=255)
    draw.text((0, 20), "Initializing...", font=font, fill=255)
    disp.image(image)
    disp.display()
    print("✅ OLED initialized successfully")

except Exception as e:
    print(f"❌ OLED init failed: {e}")

# -----------------------------
# BUZZER TEST
# -----------------------------
print("🔔 Testing buzzer...")
lgpio.gpio_write(h, BUZZER, 1)
time.sleep(0.2)
lgpio.gpio_write(h, BUZZER, 0)
print("✅ Buzzer OK")

# -----------------------------
# CLEANUP HANDLER
# -----------------------------
def cleanup():
    try:
        lgpio.gpiochip_close(h)
        print("\n🧹 GPIO released cleanly.")
    except Exception as e:
        print(f"⚠️ Cleanup issue: {e}")

atexit.register(cleanup)

print("\n✅ Stage 1 complete. Hardware initialized.")
