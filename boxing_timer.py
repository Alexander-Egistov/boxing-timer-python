#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import json
import os
import time
import subprocess
import wave
import struct
import simpleaudio as sa

STATE_FILE = "boxing_timer_state.json"

# -------------------------------------------------------------------
# WAV GENERATION (placeholder tones)
# -------------------------------------------------------------------

def generate_wav(filename, freq=440, duration=0.25, volume=0.5):
    if os.path.exists(filename):
        return

    framerate = 44100
    n_samples = int(duration * framerate)
    amplitude = int(volume * 32767)

    with wave.open(filename, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)

        period = framerate // freq
        half_period = period // 2

        for i in range(n_samples):
            sample = amplitude if (i % period) < half_period else -amplitude
            w.writeframes(struct.pack("<h", int(sample)))


def ensure_wav_files():
    generate_wav("bell.wav", freq=880, duration=0.35, volume=0.8)
    generate_wav("notification_30s.wav", freq=660, duration=0.25, volume=0.6)
    generate_wav("notification_10s.wav", freq=1000, duration=0.15, volume=0.7)


def play_wav(path):
    for cmd in [["aplay", path], ["paplay", path]]:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            continue


# -------------------------------------------------------------------
# TAB CLASS
# -------------------------------------------------------------------

class BoxingTab:
    def __init__(self, parent_notebook, app, config=None):
        self.app = app
        self.notebook = parent_notebook

        self.frame = ttk.Frame(self.notebook)
        self.notebook.add(self.frame, text=config["name"] if config else "Session")

        self.running = False
        self.mode = "idle"
        self.previous_mode = "idle"
        self.current_round = 0
        self.remaining = 0
        self.last_tick_time = None

        self.name_var = tk.StringVar(value=(config["name"] if config else "Session"))
        self.rounds_var = tk.IntVar(value=(config["rounds"] if config else 3))
        self.round_len_var = tk.IntVar(value=(config["round_len"] if config else 180))
        self.rest_len_var = tk.IntVar(value=(config["rest_len"] if config else 60))
        self.prep_len_var = tk.IntVar(value=(config["prep_len"] if config else 10))
        self.notify_30s_var = tk.BooleanVar(value=(config["notify_30s"] if config else True))
        self.notify_10s_var = tk.BooleanVar(value=(config["notify_10s"] if config else True))

        self.build_ui()

        if config and "runtime" in config:
            rt = config["runtime"]
            self.mode = rt.get("mode", "idle")
            self.current_round = rt.get("current_round", 0)
            self.remaining = rt.get("remaining", 0)
            self.running = rt.get("running", False)
            if self.running:
                self.last_tick_time = time.time()
                self.app.root.after(100, self.tick)
            self.update_clock_display()

    # -------------------------------------------------------------------

    def build_ui(self):
        self.frame.columnconfigure(0, weight=1)

        top_frame = ttk.Frame(self.frame)
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        top_frame.columnconfigure(1, weight=1)

        ttk.Label(top_frame, text="Name:", font=self.app.base_font).grid(row=0, column=0, sticky="w")
        name_entry = ttk.Entry(top_frame, textvariable=self.name_var, font=self.app.base_font)
        name_entry.grid(row=0, column=1, sticky="ew", padx=5)
        name_entry.bind("<KeyRelease>", lambda e: self.rename_tab())

        ttk.Button(top_frame, text="Start", command=self.start).grid(row=0, column=2, padx=5)
        ttk.Button(top_frame, text="Stop", command=self.stop).grid(row=0, column=3, padx=5)
        ttk.Button(top_frame, text="Reset", command=self.reset).grid(row=0, column=4, padx=5)
        ttk.Button(top_frame, text="Pause", command=self.pause).grid(row=0, column=5, padx=5)

        self.clock_label = tk.Label(
            self.frame,
            text="00:00",
            font=self.app.clock_font,
            bg="#cccccc",
            fg="black",
            relief="sunken"
        )
        self.clock_label.grid(row=1, column=0, sticky="nsew", pady=10)
        self.frame.rowconfigure(1, weight=1)

        self.clock_label.bind("<Button-1>", self.toggle_start_pause)
        self.clock_label.bind("<Button-3>", self.right_click_reset)

        self.frame.bind("<Configure>", self.scale_fonts)

        cfg_frame = ttk.Frame(self.frame)
        cfg_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        cfg_frame.columnconfigure(1, weight=1)

        def spinbox(var, from_, to):
            sb = tk.Spinbox(cfg_frame, textvariable=var, from_=from_, to=to,
                            font=self.app.base_font, width=6)
            return sb

        ttk.Label(cfg_frame, text="Rounds:", font=self.app.base_font).grid(row=0, column=0, sticky="w")
        spinbox(self.rounds_var, 1, 99).grid(row=0, column=1, sticky="w", padx=5)

        ttk.Label(cfg_frame, text="Round length (s):", font=self.app.base_font).grid(row=1, column=0, sticky="w")
        spinbox(self.round_len_var, 10, 3600).grid(row=1, column=1, sticky="w", padx=5)

        ttk.Label(cfg_frame, text="Rest length (s):", font=self.app.base_font).grid(row=2, column=0, sticky="w")
        spinbox(self.rest_len_var, 5, 3600).grid(row=2, column=1, sticky="w", padx=5)

        ttk.Label(cfg_frame, text="Prep length (s):", font=self.app.base_font).grid(row=3, column=0, sticky="w")
        spinbox(self.prep_len_var, 0, 3600).grid(row=3, column=1, sticky="w", padx=5)

        notif_frame = ttk.Frame(self.frame)
        notif_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

        ttk.Checkbutton(
            notif_frame,
            text="Notify 30s before end of round",
            variable=self.notify_30s_var,
            command=self.app.save_state
        ).pack(anchor="w")

        ttk.Checkbutton(
            notif_frame,
            text="Notify 10s before end of round",
            variable=self.notify_10s_var,
            command=self.app.save_state
        ).pack(anchor="w")

        for var in [
            self.rounds_var,
            self.round_len_var,
            self.rest_len_var,
            self.prep_len_var,
            self.notify_30s_var,
            self.notify_10s_var,
        ]:
            var.trace_add("write", lambda *args: self.app.save_state())

    # -------------------------------------------------------------------

    def scale_fonts(self, event):
        now = time.time()
        if hasattr(self, "_last_scale") and now - self._last_scale < 0.1:
            return
        self._last_scale = now

        h = max(event.height, 200)
        base_size = max(14, h // 25)
        clock_size = max(64, h // 3)
        self.app.base_font.configure(size=base_size)
        self.app.clock_font.configure(size=clock_size)

    # -------------------------------------------------------------------

    def toggle_start_pause(self, event):
        if not self.running and self.mode != "paused":
            self.start()
        elif self.mode == "paused":
            self.unpause()
        else:
            self.pause()

    def right_click_reset(self, event):
        self.reset()

    def rename_tab(self):
        idx = self.notebook.index(self.frame)
        self.notebook.tab(idx, text=self.name_var.get())
        self.app.save_state()

    def start(self):
        if self.running:
            return

        rounds = int(self.rounds_var.get())
        round_len = int(self.round_len_var.get())
        rest_len = int(self.rest_len_var.get())
        prep_len = int(self.prep_len_var.get())

        self.running = True
        self.current_round = 1

        if prep_len > 0:
            self.mode = "prep"
            self.remaining = prep_len
        else:
            self.mode = "fight"
            self.remaining = round_len
            self.app.play_bell()

        self.last_tick_time = time.time()
        self.update_clock_display()
        self.app.save_state()
        self.app.root.after(100, self.tick)

    def stop(self):
        self.running = False
        self.previous_mode = self.mode
        self.mode = "idle"
        self.update_clock_display()
        self.app.save_state()

    def reset(self):
        self.running = False
        self.mode = "idle"
        self.current_round = 0
        self.remaining = 0
        self.update_clock_display()
        self.app.save_state()

    def pause(self):
        if not self.running:
            return
        self.running = False
        self.previous_mode = self.mode
        self.mode = "paused"
        self.update_clock_display()
        self.app.save_state()

    def unpause(self):
        if self.mode != "paused":
            return
        self.running = True
        self.mode = self.previous_mode if self.previous_mode not in ("idle", "paused") else "fight"
        self.last_tick_time = time.time()
        self.update_clock_display()
        self.app.save_state()
        self.app.root.after(100, self.tick)

    def tick(self):
        if not self.running:
            return

        now = time.time()
        elapsed = now - self.last_tick_time
        if elapsed >= 1.0:
            self.last_tick_time = now
            self.remaining -= int(elapsed)
            if self.remaining <= 0:
                self.handle_phase_end()
            else:
                self.check_notifications()

        self.update_clock_display()
        self.app.root.after(100, self.tick)

    def handle_phase_end(self):
        rounds = int(self.rounds_var.get())
        round_len = int(self.round_len_var.get())
        rest_len = int(self.rest_len_var.get())

        self.app.play_bell()

        if self.mode == "prep":
            self.mode = "fight"
            self.remaining = round_len
            self.app.play_bell()

        elif self.mode == "fight":
            if self.current_round >= rounds:
                self.running = False
                self.mode = "idle"
                self.remaining = 0
            else:
                self.mode = "rest"
                self.remaining = rest_len
                self.app.play_bell()

        elif self.mode == "rest":
            self.current_round += 1
            self.mode = "fight"
            self.remaining = round_len
            self.app.play_bell()

        self.app.save_state()

    def check_notifications(self):
        if self.mode != "fight":
            return

        remaining = self.remaining

        if self.notify_30s_var.get() and remaining == 30:
            self.app.play_notification_30s()

        if self.notify_10s_var.get() and remaining == 10:
            self.app.play_notification_10s()

    def update_clock_display(self):
        mins = self.remaining // 60
        secs = self.remaining % 60
        self.clock_label.config(text=f"{mins:02d}:{secs:02d}")

        if self.mode == "fight":
            bg = "#66cc66"
        elif self.mode == "rest":
            bg = "#ff6666"
        elif self.mode == "prep":
            bg = "#ffff99"
        elif self.mode == "paused":
            bg = "#9999ff"
        else:
            bg = "#cccccc"

        self.clock_label.config(bg=bg)

    def serialize(self):
        return {
            "name": self.name_var.get(),
            "rounds": int(self.rounds_var.get()),
            "round_len": int(self.round_len_var.get()),
            "rest_len": int(self.rest_len_var.get()),
            "prep_len": int(self.prep_len_var.get()),
            "notify_30s": bool(self.notify_30s_var.get()),
            "notify_10s": bool(self.notify_10s_var.get()),
            "runtime": {
                "mode": self.mode,
                "current_round": self.current_round,
                "remaining": self.remaining,
                "running": self.running,
            },
        }


# -------------------------------------------------------------------
# MAIN APP
# -------------------------------------------------------------------

class BoxingTimerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Boxing Timer")

        ensure_wav_files()

        self.base_font = tkfont.Font(family="Helvetica", size=14)
        self.clock_font = tkfont.Font(family="Helvetica", size=64, weight="bold")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)

        self.tabs = []

        bottom_frame = ttk.Frame(root)
        bottom_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(bottom_frame, text="Add Tab", command=self.add_tab).pack(side="left")
        ttk.Button(bottom_frame, text="Save", command=self.save_state).pack(side="right")

        self.window_size = None
        self.load_state()

        if self.window_size:
            w, h = self.window_size
            self.root.geometry(f"{w}x{h}")
        else:
            self.root.geometry("700x500")

        if not self.tabs:
            self.add_tab()

        self.root.bind("<Configure>", self.on_resize)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # -------------------------------------------------------------
        # ONE-TIME INITIAL RESCALE
        # -------------------------------------------------------------
        self.root.update_idletasks()
        for t in self.tabs:
            e = tk.Event()
            e.height = self.root.winfo_height()
            t.scale_fonts(e)

    # -------------------------------------------------------------------

    def add_tab(self, config=None):
        tab = BoxingTab(self.notebook, self, config=config)
        self.tabs.append(tab)
        self.save_state()

    def play_bell(self):
        play_wav("bell.wav")

    def play_notification_30s(self):
        play_wav("notification_30s.wav")

    def play_notification_10s(self):
        play_wav("notification_10s.wav")

    def save_state(self):
        if self.root.winfo_width() > 1 and self.root.winfo_height() > 1:
            self.window_size = (self.root.winfo_width(), self.root.winfo_height())
        data = {
            "tabs": [t.serialize() for t in self.tabs],
            "window_size": self.window_size,
        }
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("Error saving state:", e)

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            return

        self.window_size = data.get("window_size")
        for cfg in data.get("tabs", []):
            self.add_tab(config=cfg)

    def on_resize(self, event):
        if event.widget == self.root:
            if event.width > 1 and event.height > 1:
                self.window_size = (event.width, event.height)

    def on_close(self):
        self.save_state()
        self.root.destroy()


# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------

def main():
    root = tk.Tk()
    app = BoxingTimerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
