from machine import I2C, Pin
import math
import time

i2c = I2C(0, sda=Pin(21), scl=Pin(22), freq=400000)
MPU_ADDR = 0x68

# Wake up MPU6050
i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
time.sleep_ms(100)

def read_word(reg):
    data = i2c.readfrom_mem(MPU_ADDR, reg, 2)
    val = (data[0] << 8) | data[1]
    if val > 32768:
        val -= 65536
    return val

print("MPU6050 Ready!")

while True:
    acX = read_word(0x3B)
    acY = read_word(0x3D)
    acZ = read_word(0x3F)

    # Roll angle — same formula as Arduino
    roll = math.atan2(acY, acZ) * 180 / math.pi

    # Force — same formula as Arduino (all 3 axes)
    force = math.sqrt(acX*acX + acY*acY + acZ*acZ) / 100

    # Send in exact same format: "ROLL:FORCE"
    print(f"{roll:.2f}:{int(force)}")

    time.sleep_ms(15)  # 60Hz — same as Arduino