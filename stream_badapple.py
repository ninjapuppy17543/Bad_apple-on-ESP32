import cv2
import glob
import serial
import time

SERIAL_PORT = "COM4"   # <-- CHANGE THIS to your real COM port (e.g. "COM5")
BAUD = 921600

FRAME_W = 128   # must match ESP
FRAME_H = 96
BYTES_PER_FRAME = (FRAME_W * FRAME_H) // 8

TARGET_FPS = 15
FRAME_INTERVAL = 1.0 / TARGET_FPS

def to_1bit(frame):
    # frame: grayscale 96x128
    _, bw = cv2.threshold(frame, 128, 255, cv2.THRESH_BINARY)
    out = bytearray(BYTES_PER_FRAME)
    for y in range(FRAME_H):
        for x in range(FRAME_W):
            byte_i = (y * (FRAME_W // 8)) + (x // 8)
            if bw[y, x] > 0:
                out[byte_i] |= (1 << (7 - (x % 8)))
    return out

def main():
    ser = serial.Serial(SERIAL_PORT, BAUD)
    time.sleep(1)

    frames = sorted(glob.glob("frames/*.png"))
    total_frames = len(frames)
    print("Loaded", total_frames, "frames")

    start_time = time.perf_counter()

    for i, fpath in enumerate(frames):
        img = cv2.imread(fpath, cv2.IMREAD_GRAYSCALE)
        # Just in case: force resize to 128x96
        img = cv2.resize(img, (FRAME_W, FRAME_H))

        payload = to_1bit(img)

        # When should this frame ideally appear?
        target_t = start_time + i * FRAME_INTERVAL

        # Send frame
        ser.write(payload)

        # Wait for ACK from ESP32
        ser.read(1)
        time.sleep(0.002)   # 2 milliseconds helps prevent tearing


        # Enforce FPS timing
        now = time.perf_counter()
        sleep_time = target_t - now
        if sleep_time > 0:
            time.sleep(sleep_time)

        if i % 50 == 0:
            print(f"Sent frame {i}/{total_frames}")

    print("Done streaming.")
    ser.close()

if __name__ == "__main__":
    main()
