import serial
import time
import numpy as np
import sounddevice as sd
import sys
import threading

# --- CONFIGURATION ---
# UPDATE THIS PORT to match your Arduino (e.g., COM3 or /dev/cu.usbmodem...)
SERIAL_PORT = 'COM3' 
BAUD_RATE = 115200
SAMPLE_RATE = 44100
MIN_STRUM_FORCE = 140 

# --- AUDIO ENGINE ---
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
                    mixed_audio += sound[idx : idx + frames]
                    self.active_sounds[i][1] += frames
                else:
                    mixed_audio[:remaining] += sound[idx:]
                    self.active_sounds.pop(i)
        
        # Limiter/Distortion
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

# --- VIRTUAL STRINGS (Open E Tuning) ---
VIRTUAL_STRINGS = [
    {"angle": -40, "note": "Low E", "sound": generate_string_sound(82.41)},
    {"angle": -25, "note": "A",     "sound": generate_string_sound(110.00)},
    {"angle": -10, "note": "D",     "sound": generate_string_sound(146.83)},
    {"angle": 5,   "note": "G",     "sound": generate_string_sound(196.00)},
    {"angle": 20,  "note": "B",     "sound": generate_string_sound(246.94)},
    {"angle": 35,  "note": "High E","sound": generate_string_sound(329.63)},
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
    
    prev_roll = -999
    
    try:
        while True:
            if ser.in_waiting:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if ":" in line:
                        r_str, f_str = line.split(":")
                        current_roll = float(r_str) - offset
                        force = int(f_str)

                        if force > MIN_STRUM_FORCE:
                            for s in VIRTUAL_STRINGS:
                                ang = s["angle"]
                                if prev_roll != -999:
                                    # Check for crossing the virtual string line
                                    down = (prev_roll > ang >= current_roll)
                                    up = (prev_roll < ang <= current_roll)
                                    if down or up:
                                        engine.add_sound(s["sound"])
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
