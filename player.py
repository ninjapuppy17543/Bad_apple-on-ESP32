# player.py
import glob
import time
import threading
import cv2
import serial
import numpy as np


class BadApplePlayer:
    def __init__(
        self,
        serial_port: str,
        baud: int = 921600,
        frames_glob: str = "frames/*.png",
        frame_w: int = 128,
        frame_h: int = 96,
        base_fps: float = 15.0,
        loop_fps: float = 120.0,   # high-frequency loop for responsiveness
    ):
        # Video & transmission settings
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.bytes_per_frame = (frame_w * frame_h) // 8

        self.serial_port = serial_port
        self.baud = baud
        self.base_fps = base_fps
        self.loop_fps = loop_fps  # how often the loop runs

        # State (protected by lock)
        self._lock = threading.Lock()
        self._playing = False
        self._stop_flag = False

        # Timeline state (in seconds of video)
        self._video_time_sec = 0.0        # current logical video time
        self._speed_multiplier = 1.0      # 1.0 = normal speed

        # Open serial
        self.ser = serial.Serial(self.serial_port, self.baud)
        time.sleep(1.0)  # give ESP32 time to reset

        # Load frames (preview + packed)
        self.frames, self.preview_frames = self._load_all_frames(frames_glob)
        self.total_frames = len(self.frames)
        print(f"[Player] Loaded {self.total_frames} frames")

        # Background playback thread
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Load & pack all frames
    # ------------------------------------------------------------------

    def _load_all_frames(self, pattern: str):
        paths = sorted(glob.glob(pattern))
        if not paths:
            raise SystemExit(f"No frames found with pattern: {pattern}")

        packed_frames = []
        preview_frames = []

        for i, path in enumerate(paths):
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            img = cv2.resize(img, (self.frame_w, self.frame_h))

            # Store preview (uint8 image)
            preview_frames.append(img.copy())

            # Store packed 1-bit frame for ESP32
            packed_frames.append(self._pack_img(img))

            if i % 200 == 0:
                print(f"[Player] Packed {i}/{len(paths)} frames")

        return packed_frames, preview_frames

    def _pack_img(self, img: np.ndarray) -> bytes:
        # Threshold to 1-bit
        _, bw = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY)
        out = bytearray(self.bytes_per_frame)

        for y in range(self.frame_h):
            row_offset = y * (self.frame_w // 8)
            for x in range(self.frame_w):
                byte_i = row_offset + (x >> 3)
                if bw[y, x] > 0:
                    out[byte_i] |= (1 << (7 - (x & 7)))

        return bytes(out)

    # ------------------------------------------------------------------
    # Main playback loop (timeline-driven)
    # ------------------------------------------------------------------

    def _loop(self):
        loop_interval = 1.0 / self.loop_fps
        last_real_time = time.perf_counter()
        last_sent_frame = -1

        while True:
            # Check stop
            with self._lock:
                if self._stop_flag:
                    break
                playing = self._playing
                speed = self._speed_multiplier
                video_time = self._video_time_sec

            now = time.perf_counter()
            dt = now - last_real_time
            last_real_time = now

            # Clamp dt in case of long pauses (debugger, etc.)
            if dt > 0.25:
                dt = 0.25

            # Update video timeline if playing
            if playing:
                video_time += dt * speed
                # Loop video time if we reach the end
                total_video_time = self.total_frames / self.base_fps
                if total_video_time > 0:
                    # Wrap around
                    while video_time >= total_video_time:
                        video_time -= total_video_time
                    while video_time < 0:
                        video_time += total_video_time

                with self._lock:
                    self._video_time_sec = video_time
            else:
                # Not playing -> video_time remains constant
                pass

            # Compute which frame we *should* be on
            frame_idx = int(video_time * self.base_fps)
            if self.total_frames > 0:
                # Just in case int rounding goes off by one
                frame_idx = max(0, min(frame_idx, self.total_frames - 1))
            else:
                frame_idx = 0

            # Only send frame when it changes
            if frame_idx != last_sent_frame:
                self._send_frame(frame_idx)
                last_sent_frame = frame_idx

            time.sleep(loop_interval)

        self.ser.close()
        print("[Player] Stopped and serial closed.")

    # ------------------------------------------------------------------
    # Send one frame to ESP32
    # ------------------------------------------------------------------

    def _send_frame(self, frame_index: int):
        if self.total_frames == 0:
            return

        frame_index = max(0, min(frame_index, self.total_frames - 1))
        payload = self.frames[frame_index]
        self.ser.write(payload)

        try:
            self.ser.read(1)  # wait for ACK (0xAA) from ESP32
        except Exception:
            # In case of serial glitch, don't crash the loop
            pass

    # ------------------------------------------------------------------
    # Public API used by the GUI
    # ------------------------------------------------------------------

    def play(self):
        with self._lock:
            self._playing = True

    def pause(self):
        with self._lock:
            self._playing = False

    def toggle_play(self):
        with self._lock:
            self._playing = not self._playing

    def rewind(self):
        self.seek(0)

    def seek(self, frame_index: int):
        """Set the video time so the logical frame is frame_index."""
        if self.total_frames == 0:
            return

        frame_index = max(0, min(frame_index, self.total_frames - 1))
        new_time = frame_index / self.base_fps

        with self._lock:
            self._video_time_sec = new_time
        # Next loop iteration will see a different frame index and send it

    def set_speed(self, multiplier: float):
        with self._lock:
            self._speed_multiplier = max(0.1, float(multiplier))

    def get_current_frame(self) -> int:
        """Return the current logical frame index."""
        with self._lock:
            video_time = self._video_time_sec

        if self.total_frames == 0:
            return 0

        idx = int(video_time * self.base_fps)
        idx = max(0, min(idx, self.total_frames - 1))
        return idx

    def get_preview_frame(self, frame_index: int):
        """Return grayscale numpy image (H x W) of given frame."""
        if self.total_frames == 0:
            # Fallback blank image
            return np.zeros((self.frame_h, self.frame_w), dtype=np.uint8)

        frame_index = max(0, min(frame_index, self.total_frames - 1))
        return self.preview_frames[frame_index]

    def is_playing(self):
        with self._lock:
            return self._playing

    def stop(self):
        with self._lock:
            self._stop_flag = True
        self._thread.join(timeout=2.0)
