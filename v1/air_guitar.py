import serial
import time
import numpy as np
import sounddevice as sd
import sys
import threading
import math

# --- CONFIGURATION ---
SERIAL_PORT     = 'COM3'
BAUD_RATE       = 115200
SAMPLE_RATE     = 44100
MIN_STRUM_FORCE = 140    # Base force threshold

# --- UPGRADE 1: Per-string cooldown ---
STRING_COOLDOWN = 0.15   # Each string needs 150ms before it can replay

# --- UPGRADE 2: Velocity threshold ---
MIN_VELOCITY    = 3.0    # Degrees per frame — ignore slow drifts

# --- UPGRADE 3: Force spike detection ---
MIN_FORCE_SPIKE = 30     # Force must JUMP by this much (sudden snap)

# --- UPGRADE 4: Low pass filter ---
ALPHA           = 0.3    # 0=max smooth/laggy, 1=raw/responsive. 0.3 is balanced

# --- AUDIO ENGINE (same as original) ---
class GuitarEngine:
    def __init__(self):
        self.active_sounds = []
        self.lock = threading.Lock()

    def add_sound(self, sound_array):
        with self.lock:
            self.active_sounds.append([sound_array, 0])

    def callback(self, outdata, frames, time, status):
        if status: print(status, file=sys.stderr)
        mixed_audio = np.zeros(frames)
        with self.lock:
            for i in range(len(self.active_sounds) - 1, -1, -1):
                sound, idx = self.active_sounds[i]
                remaining = len(sound) - idx
                if remaining > frames:
                    mixed_audio += sound[idx:idx + frames]
                    self.active_sounds[i][1] += frames
                else:
                    mixed_audio[:remaining] += sound[idx:]
                    self.active_sounds.pop(i)

        # Limiter/Distortion (same as original)
        mixed_audio = np.tanh(mixed_audio) * 0.5
        outdata[:] = mixed_audio.reshape(-1, 1)

def generate_string_sound(freq, duration=3.0, decay=0.992):
    n_samples = int(duration * SAMPLE_RATE)
    N = int(SAMPLE_RATE / freq)
    buf = np.random.randn(N)
    samples = np.zeros(n_samples)
    for i in range(n_samples):
        samples[i] = buf[i % N]
        buf[i % N] = 0.5 * (buf[i % N] + buf[(i + 1) % N]) * decay
    return samples.astype(np.float32)

# --- VIRTUAL STRINGS (same angles as original) ---
VIRTUAL_STRINGS = [
    {"angle": -40, "note": "Low E", "sound": generate_string_sound(82.41),  "last_played": 0},
    {"angle": -25, "note": "A",     "sound": generate_string_sound(110.00), "last_played": 0},
    {"angle": -10, "note": "D",     "sound": generate_string_sound(146.83), "last_played": 0},
    {"angle":   5, "note": "G",     "sound": generate_string_sound(196.00), "last_played": 0},
    {"angle":  20, "note": "B",     "sound": generate_string_sound(246.94), "last_played": 0},
    {"angle":  35, "note": "High E","sound": generate_string_sound(329.63), "last_played": 0},
]

def calibrate_sensor(ser):
    print("\n   HOLD HAND NEUTRAL... Calibrating in 3 seconds...")
    time.sleep(3)
    readings = []
    start = time.time()
    while time.time() - start < 1.5:
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if ":" in line:
                    r, _ = line.split(":")
                    readings.append(float(r))
            except: pass
    if not readings: return 0.0
    offset = sum(readings) / len(readings)
    print(f"   Done! Zero point: {offset:.1f}\n")
    return offset

def main():
    engine = GuitarEngine()
    stream = sd.OutputStream(channels=1, samplerate=SAMPLE_RATE, callback=engine.callback)
    stream.start()

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.01)
        time.sleep(2)
    except:
        print("Check Serial Port!")
        return

    offset = calibrate_sensor(ser)
    print("🎸 READY! Sweep wrist to play.")

    prev_roll   = -999
    smoothed_roll = -999  # UPGRADE 4: low pass filtered roll
    prev_force  = 0       # UPGRADE 3: for spike detection

    try:
        while True:
            if ser.in_waiting:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if ":" in line:
                        r_str, f_str = line.split(":")
                        raw_roll = float(r_str) - offset
                        force    = int(f_str)

                        # UPGRADE 4: Low pass filter on roll
                        if smoothed_roll == -999:
                            smoothed_roll = raw_roll  # first reading — init
                        smoothed_roll = (ALPHA * raw_roll) + ((1 - ALPHA) * smoothed_roll)
                        current_roll  = smoothed_roll

                        # UPGRADE 2: Velocity — how fast is wrist moving
                        if prev_roll != -999:
                            velocity = abs(current_roll - prev_roll)
                        else:
                            velocity = 0

                        # UPGRADE 3: Force spike — sudden jump in force
                        force_spike = force - prev_force
                        prev_force  = force

                        # Only process if force AND spike AND velocity all pass
                        if (force > MIN_STRUM_FORCE and
                            force_spike > MIN_FORCE_SPIKE and
                            velocity > MIN_VELOCITY):

                            now = time.time()
                            for s in VIRTUAL_STRINGS:
                                ang = s["angle"]
                                if prev_roll != -999:
                                    down = (prev_roll > ang >= current_roll)
                                    up   = (prev_roll < ang <= current_roll)
                                    if down or up:
                                        # UPGRADE 1: Per-string cooldown check
                                        if now - s["last_played"] > STRING_COOLDOWN:
                                            engine.add_sound(s["sound"])
                                            s["last_played"] = now
                                            print(f"🎵 {s['note']}")

                        prev_roll = current_roll

                except: pass
            else:
                time.sleep(0.001)

    except KeyboardInterrupt:
        stream.stop()
        ser.close()

if __name__ == "__main__":
    main()
