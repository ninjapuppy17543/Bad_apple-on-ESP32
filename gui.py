# gui.py
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw, ImageFont
from player import BadApplePlayer
import time

SERIAL_PORT = "COM4"   # <-- change this to your actual ESP32 COM port

# Virtual TFT (simulated screen) resolution
VIRTUAL_W, VIRTUAL_H = 320, 240  # pretend TFT resolution


def format_time(seconds: float) -> str:
    seconds = int(seconds)
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


def main():
    # --- Create player engine ---
    player = BadApplePlayer(
        serial_port=SERIAL_PORT,
        baud=921600,
        frames_glob="frames/*.png",
        frame_w=128,
        frame_h=96,
        base_fps=15.0,
    )

    root = tk.Tk()
    root.title("Bad Apple ESP32 Controller")
    root.geometry("650x650")

    # ---------- Info ----------
    info_label = ttk.Label(root, text=f"Frames loaded: {player.total_frames}")
    info_label.pack(pady=5)

    # ================================================================
    # TOP: FULL VIDEO PREVIEW
    # ================================================================
    preview_frame = ttk.Frame(root)
    preview_frame.pack(pady=5)

    ttk.Label(preview_frame, text="Full Video Preview:").pack()

    preview_canvas = tk.Label(preview_frame)
    preview_canvas.pack()
    preview_canvas.img_ref = None  # keep ref to avoid GC

    # Skip indicator (for +5s, -10s, etc.)
    skip_indicator = {"text": None, "timestamp": 0.0}

    def show_skip_indicator(seconds: float):
        if seconds > 0:
            text = f"+{int(seconds)}s"
        else:
            text = f"{int(seconds)}s"
        skip_indicator["text"] = text
        skip_indicator["timestamp"] = time.time()

    # ================================================================
    # MIDDLE: CONTROLS (play/pause, speed, seek)
    # ================================================================
    btn_frame = ttk.Frame(root)
    btn_frame.pack(pady=5)

    ttk.Button(btn_frame, text="Play",   command=player.play).grid(row=0, column=0, padx=5)
    ttk.Button(btn_frame, text="Pause",  command=player.pause).grid(row=0, column=1, padx=5)
    ttk.Button(btn_frame, text="Rewind", command=player.rewind).grid(row=0, column=2, padx=5)

    # ---------- YouTube-style Speed Dropdown ----------
    ttk.Label(root, text="Playback Speed").pack()

    yt_speeds = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
    yt_speed_labels = [f"{s}x" if s != 1.0 else "Normal (1x)" for s in yt_speeds]

    speed_var = tk.StringVar(value="Normal (1x)")

    def apply_speed_label(label: str):
        if label.startswith("Normal"):
            value = 1.0
        else:
            try:
                value = float(label.replace("x", ""))
            except ValueError:
                value = 1.0
        player.set_speed(value)

    def on_speed_select(event=None):
        apply_speed_label(speed_var.get())

    speed_combo = ttk.Combobox(
        root, state="readonly", values=yt_speed_labels, textvariable=speed_var
    )
    speed_combo.pack(fill="x", padx=20, pady=5)
    speed_combo.bind("<<ComboboxSelected>>", on_speed_select)

    # ---------- Seek Bar ----------
    ttk.Label(root, text="Seek").pack()

    seek_var = tk.IntVar(value=0)
    is_seeking = {"value": False}

    def on_seek_change(val):
        # real-time seeking while dragging
        if is_seeking["value"]:
            try:
                idx = int(float(val))
            except ValueError:
                idx = 0
            player.seek(idx)

    seek_scale = ttk.Scale(
        root,
        from_=0,
        to=player.total_frames - 1,
        orient="horizontal",
        variable=seek_var,
        command=on_seek_change,
    )
    seek_scale.pack(fill="x", padx=20, pady=5)

    def on_seek_press(event):
        is_seeking["value"] = True

    def on_seek_release(event):
        is_seeking["value"] = False
        idx = seek_var.get()
        player.seek(idx)

    seek_scale.bind("<ButtonPress-1>", on_seek_press)
    seek_scale.bind("<ButtonRelease-1>", on_seek_release)

    # ---------- Relative Seeking (immediate, YouTube-style) ----------
    SEEK_SMALL = 5    # seconds
    SEEK_BIG = 10     # seconds

    def seek_relative(seconds: float):
        # convert seconds -> frames relative to current position
        delta_frames = int(seconds * player.base_fps)
        idx = player.get_current_frame()
        player.seek(idx + delta_frames)
        show_skip_indicator(seconds)

    # ---------- Keyboard Shortcuts ----------
    def on_space(event=None):
        player.toggle_play()

    def on_left(event=None):
        seek_relative(-SEEK_SMALL)

    def on_right(event=None):
        seek_relative(+SEEK_SMALL)

    def on_down(event=None):
        seek_relative(-SEEK_BIG)

    def on_up(event=None):
        seek_relative(+SEEK_BIG)

    def on_J(event=None):
        seek_relative(-SEEK_BIG)

    def on_L(event=None):
        seek_relative(+SEEK_BIG)

    # Speed step (like YouTube's < and >, we use , and .)
    def step_speed(delta: int):
        current_label = speed_var.get()
        try:
            idx = yt_speed_labels.index(current_label)
        except ValueError:
            idx = yt_speed_labels.index("Normal (1x)")
        new_idx = max(0, min(len(yt_speed_labels) - 1, idx + delta))
        new_label = yt_speed_labels[new_idx]
        speed_var.set(new_label)
        apply_speed_label(new_label)

    def on_speed_up(event=None):
        step_speed(+1)

    def on_speed_down(event=None):
        step_speed(-1)

    root.bind("<space>", on_space)
    root.bind("<Left>", on_left)
    root.bind("<Right>", on_right)
    root.bind("<Down>", on_down)
    root.bind("<Up>", on_up)
    root.bind("j", on_J)
    root.bind("J", on_J)
    root.bind("l", on_L)
    root.bind("L", on_L)
    root.bind("<period>", on_speed_up)   # .
    root.bind("<comma>", on_speed_down)  # ,

    # ---------- Status Label ----------
    status_label = ttk.Label(root, text="")
    status_label.pack(pady=5)

    # ================================================================
    # BOTTOM: VIRTUAL TFT SCREEN (MOVE + SCALE)
    # ================================================================
    virtual_frame = ttk.Frame(root)
    virtual_frame.pack(pady=10)

    ttk.Label(virtual_frame, text="Virtual TFT (simulating hardware screen):").pack()

    virtual_label = tk.Label(virtual_frame)
    virtual_label.pack()
    virtual_label.img_ref = None  # keep ref

    # Viewport within the virtual TFT where the video is drawn
    viewport = {
        "x": 80,   # initial position
        "y": 60,
        "w": 160,  # initial size
        "h": 120,
    }

    drag_state = {
        "mode": None,   # None / "move" / "resize"
        "start_x": 0,
        "start_y": 0,
        "start_vx": 0,
        "start_vy": 0,
        "start_vw": 0,
        "start_vh": 0,
    }

    RESIZE_HANDLE_SIZE = 12  # pixel size of the "corner" region for resizing

    def in_viewport(x, y):
        vx, vy, vw, vh = viewport["x"], viewport["y"], viewport["w"], viewport["h"]
        return (vx <= x <= vx + vw) and (vy <= y <= vy + vh)

    def in_resize_corner(x, y):
        vx, vy, vw, vh = viewport["x"], viewport["y"], viewport["w"], viewport["h"]
        # bottom-right corner zone
        return (vx + vw - RESIZE_HANDLE_SIZE <= x <= vx + vw and
                vy + vh - RESIZE_HANDLE_SIZE <= y <= vy + vh)

    def on_virtual_mouse_down(event):
        x, y = event.x, event.y
        if in_viewport(x, y):
            drag_state["start_x"] = x
            drag_state["start_y"] = y
            drag_state["start_vx"] = viewport["x"]
            drag_state["start_vy"] = viewport["y"]
            drag_state["start_vw"] = viewport["w"]
            drag_state["start_vh"] = viewport["h"]

            if in_resize_corner(x, y):
                drag_state["mode"] = "resize"
            else:
                drag_state["mode"] = "move"
        else:
            drag_state["mode"] = None

    def on_virtual_mouse_move(event):
        if drag_state["mode"] is None:
            return

        x, y = event.x, event.y

        if drag_state["mode"] == "move":
            dx = x - drag_state["start_x"]
            dy = y - drag_state["start_y"]
            new_x = drag_state["start_vx"] + dx
            new_y = drag_state["start_vy"] + dy

            # clamp to virtual TFT bounds
            new_x = max(0, min(new_x, VIRTUAL_W - viewport["w"]))
            new_y = max(0, min(new_y, VIRTUAL_H - viewport["h"]))

            viewport["x"] = new_x
            viewport["y"] = new_y

        elif drag_state["mode"] == "resize":
            dx = x - drag_state["start_x"]
            dy = y - drag_state["start_y"]
            new_w = drag_state["start_vw"] + dx
            new_h = drag_state["start_vh"] + dy

            # minimum size
            min_w, min_h = 32, 24
            new_w = max(min_w, new_w)
            new_h = max(min_h, new_h)

            # clamp to virtual TFT bounds
            if viewport["x"] + new_w > VIRTUAL_W:
                new_w = VIRTUAL_W - viewport["x"]
            if viewport["y"] + new_h > VIRTUAL_H:
                new_h = VIRTUAL_H - viewport["y"]

            viewport["w"] = new_w
            viewport["h"] = new_h

    def on_virtual_mouse_up(event):
        drag_state["mode"] = None

    virtual_label.bind("<ButtonPress-1>", on_virtual_mouse_down)
    virtual_label.bind("<B1-Motion>", on_virtual_mouse_move)
    virtual_label.bind("<ButtonRelease-1>", on_virtual_mouse_up)

    # ================================================================
    # UI UPDATE LOOP
    # ================================================================
    def update_ui():
        idx = player.get_current_frame()
        playing = player.is_playing()

        # Time display
        cur_t = idx / player.base_fps
        tot_t = player.total_frames / player.base_fps
        status_label.config(
            text=f"Frame {idx}/{player.total_frames - 1}  |  {format_time(cur_t)} / {format_time(tot_t)}  |  {'Playing' if playing else 'Paused'}"
        )

        # Sync seek bar if user isn't dragging
        if not is_seeking["value"]:
            seek_var.set(idx)

        # ----------------- FULL PREVIEW (top) -----------------
        try:
            frame_img = player.get_preview_frame(idx)  # numpy (H x W)
            pil_img = Image.fromarray(frame_img)

            # Scale preview x3 for visibility
            scale = 3
            pil_img = pil_img.resize(
                (player.frame_w * scale, player.frame_h * scale),
                Image.NEAREST
            )

            # Draw skip indicator if recent (<0.5s)
            dt = time.time() - skip_indicator["timestamp"]
            if skip_indicator["text"] and dt < 0.5:
                draw = ImageDraw.Draw(pil_img)
                text = skip_indicator["text"]
                W, H = pil_img.size
                font = ImageFont.load_default()
                # Pillow 10+: use textbbox instead of textsize
                bbox = draw.textbbox((0, 0), text, font=font)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                draw.text(
                    ((W - w) // 2, (H - h) // 2),
                    text,
                    fill=255,
                    font=font
                )

            tk_img = ImageTk.PhotoImage(pil_img)
            preview_canvas.configure(image=tk_img)
            preview_canvas.img_ref = tk_img
        except Exception:
            pass  # avoid crashing UI for any preview issue

        # ----------------- VIRTUAL TFT (bottom) -----------------
        try:
            frame_img = player.get_preview_frame(idx)  # same frame
            # base "screen" image
            tft_img = Image.new("L", (VIRTUAL_W, VIRTUAL_H), 0)  # black background

            # scale video frame to viewport size
            vw, vh = int(viewport["w"]), int(viewport["h"])
            if vw > 0 and vh > 0:
                vid_pil = Image.fromarray(frame_img)
                vid_scaled = vid_pil.resize((vw, vh), Image.NEAREST)
                tft_img.paste(vid_scaled, (int(viewport["x"]), int(viewport["y"])))

            # draw viewport border + resize handle
            draw = ImageDraw.Draw(tft_img)
            vx, vy, vw, vh = viewport["x"], viewport["y"], viewport["w"], viewport["h"]
            # rectangle border
            draw.rectangle(
                [vx, vy, vx + vw - 1, vy + vh - 1],
                outline=255,
                width=1
            )
            # resize handle (small filled square in bottom-right corner)
            handle_x0 = vx + vw - RESIZE_HANDLE_SIZE
            handle_y0 = vy + vh - RESIZE_HANDLE_SIZE
            draw.rectangle(
                [handle_x0, handle_y0, handle_x0 + RESIZE_HANDLE_SIZE - 1, handle_y0 + RESIZE_HANDLE_SIZE - 1],
                fill=255
            )

            # convert to RGB for Tk
            tft_img_rgb = tft_img.convert("RGB")
            tk_tft = ImageTk.PhotoImage(tft_img_rgb)
            virtual_label.configure(image=tk_tft)
            virtual_label.img_ref = tk_tft

        except Exception:
            pass

        root.after(100, update_ui)

    # ---------- Quit Handler ----------
    def on_quit():
        player.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_quit)
    update_ui()
    root.mainloop()


if __name__ == "__main__":
    main()
