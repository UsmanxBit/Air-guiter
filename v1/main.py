from machine import I2C, Pin
from machine import WDT
import math
import time

i2c = I2C(0, sda=Pin(21), scl=Pin(22), freq=400000)
MPU_ADDR = 0x68

# Wake up MPU6050
i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
time.sleep_ms(100)

# --- STARTUP CHECK ---
devices = i2c.scan()
if MPU_ADDR not in devices:
    print("ERROR: MPU6050 not found! Check wiring.")
    raise SystemExit
print("MPU6050 Ready!")

# --- WATCHDOG: auto-restart if ESP32 freezes (8 second timeout) ---
wdt = WDT(timeout=8000)

def read_all_axes():
    # Read all 6 bytes in ONE burst — faster than 3 separate calls
    data = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
    def to_signed(hi, lo):
        val = (hi << 8) | lo
        if val > 32768:
            val -= 65536
        return val
    acX = to_signed(data[0], data[1])
    acY = to_signed(data[2], data[3])
    acZ = to_signed(data[4], data[5])
    return acX, acY, acZ

while True:
    wdt.feed()  # Reset watchdog timer — proves ESP32 is alive

    acX, acY, acZ = read_all_axes()

    # Roll angle
    roll = math.atan2(acY, acZ) * 180 / math.pi

    # Force — all 3 axes
    force = math.sqrt(acX*acX + acY*acY + acZ*acZ) / 100

    print(f"{roll:.2f}:{int(force)}")

    time.sleep_ms(15)  # 60Hz
