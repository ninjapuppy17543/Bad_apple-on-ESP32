import cv2
import numpy as np
import glob

FRAME_W = 128
FRAME_H = 96

frames = sorted(glob.glob("frames/*.png"))

img = cv2.imread(frames[0], cv2.IMREAD_GRAYSCALE)
print("Image shape:", img.shape)  # should be (96, 128)

img = cv2.resize(img, (FRAME_W, FRAME_H))

# convert to 1-bit
_, bw = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY)

BYTES_PER_FRAME = (FRAME_W * FRAME_H) // 8
print("Expected bytes:", BYTES_PER_FRAME)

# pack to bytes
out = bytearray(BYTES_PER_FRAME)

for y in range(FRAME_H):
    for x in range(FRAME_W):
        byte_i = (y * (FRAME_W // 8)) + (x // 8)
        if bw[y, x] > 0:
            out[byte_i] |= (1 << (7 - (x % 8)))

print("Actual bytes:", len(out))
print("First 32 bytes:", list(out[:32]))
print("Bytes per row:", FRAME_W // 8)
