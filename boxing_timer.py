#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import json, os, time, subprocess, wave, struct

STATE_FILE = "boxing_timer_state.json"

# ---------------------- SOUND ----------------------

def generate_wav(path, freq, dur, vol):
    if os.path.exists(path): return
    rate = 44100
    samples = int(dur * rate)
    amp = int(vol * 32767)
    period = rate // freq
    half = period // 2
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        for i in range(samples):
            w.writeframes(struct.pack("<h", amp if (i % period) < half else -amp))

def ensure_wav():
    generate_wav("bell.wav", 880, 0.35, 0.8)
    generate_wav("n30.wav", 660, 0.25, 0.6)
    generate_wav("n10.wav", 1000, 0.15, 0.7)

def play(path):
    for cmd in [["aplay", path], ["paplay", path]]:
        try: subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); return
        except: pass

# ---------------------- TAB ----------------------

class BoxingTab:
    def __init__(self, nb, app, cfg=None):
        self.app = app
        self.nb = nb
        self.frame = ttk.Frame(nb)
        nb.add(self.frame, text=(cfg["name"] if cfg else "Session"))

        self.running = False
        self.mode = "idle"
        self.current_round = 0
        self.remaining = 0
        self.last_tick = None

        self.name = tk.StringVar(value=(cfg["name"] if cfg else "Session"))
        self.rounds = tk.IntVar(value=(cfg["rounds"] if cfg else 3))
        self.rlen = tk.IntVar(value=(cfg["round_len"] if cfg else 180))
        self.rest = tk.IntVar(value=(cfg["rest_len"] if cfg else 60))
        self.prep = tk.IntVar(value=(cfg["prep_len"] if cfg else 10))
        self.n30 = tk.BooleanVar(value=(cfg["notify_30s"] if cfg else True))
        self.n10 = tk.BooleanVar(value=(cfg["notify_10s"] if cfg else True))

        self.build_ui()

        if cfg and "runtime" in cfg:
            rt = cfg["runtime"]
            self.mode = rt["mode"]
            self.current_round = rt["current_round"]
            self.remaining = rt["remaining"]
            self.running = rt["running"]
            if self.running:
                self.last_tick = time.time()
                self.app.root.after(100, self.tick)
            self.update_display()

    # ---------------- UI ----------------


    def build_ui(self):
        f = self.frame
        f.columnconfigure(0, weight=1)

        # ENLARGED CLOCK REGION — BIGGER THAN BEFORE
        f.rowconfigure(0, weight=0)   # top controls
        f.rowconfigure(1, weight=8)   # HUGE clock region
        f.rowconfigure(2, weight=1)   # settings
        f.rowconfigure(3, weight=1)   # notifications

        top = ttk.Frame(f); top.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Name:", font=self.app.base_font).grid(row=0, column=0)
        e = ttk.Entry(top, textvariable=self.name, font=self.app.base_font)
        e.grid(row=0, column=1, sticky="ew"); e.bind("<KeyRelease>", lambda *_: self.rename())

        for i, (txt, cmd) in enumerate([("Start", self.start), ("Stop", self.stop),
                                        ("Reset", self.reset), ("Pause", self.pause)]):
            ttk.Button(top, text=txt, command=cmd).grid(row=0, column=i+2, padx=5)

        # MASSIVE CLOCK REGION
        self.clock = tk.Label(
            f,
            text="00:00",
            font=self.app.clock_font,
            bg="#ccc",
            fg="black",
            relief="sunken",
            padx=40, pady=40   # << HUGE padding
        )
        self.clock.grid(row=1, column=0, sticky="nsew", pady=20)
        self.clock.bind("<Button-1>", lambda *_: self.toggle())
        self.clock.bind("<Button-3>", lambda *_: self.reset())

        cfg = ttk.Frame(f); cfg.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        for i, (txt, var, lo, hi) in enumerate([
            ("Rounds:", self.rounds, 1, 999),
            ("Round (s):", self.rlen, 10, 3600),
            ("Rest (s):", self.rest, 5, 3600),
            ("Prep (s):", self.prep, 0, 3600)
        ]):
            ttk.Label(cfg, text=txt, font=self.app.base_font).grid(row=i, column=0)
            tk.Spinbox(cfg, textvariable=var, from_=lo, to=hi,
                       font=self.app.base_font, width=4).grid(row=i, column=1, sticky="w")

        nf = ttk.Frame(f); nf.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        ttk.Checkbutton(nf, text="Notify 30s", variable=self.n30,
                        command=self.app.save).pack(anchor="w")
        ttk.Checkbutton(nf, text="Notify 10s", variable=self.n10,
                        command=self.app.save).pack(anchor="w")

        for v in [self.rounds, self.rlen, self.rest, self.prep, self.n30, self.n10]:
            v.trace_add("write", lambda *_: self.app.save())

        f.bind("<Configure>", self.scale)





    # ---------------- Logic ----------------

    def scale(self, e):
        h = max(e.height, 200)
        self.app.base_font.configure(size=max(14, h // 25))
        self.app.clock_font.configure(size=max(64, h // 4))

    def rename(self):
        idx = self.nb.index(self.frame)
        self.nb.tab(idx, text=self.name.get())
        self.app.save()

    def toggle(self):
        if not self.running and self.mode != "paused": self.start()
        elif self.mode == "paused": self.unpause()
        else: self.pause()

    def start(self):
        self.app.stop_others(self)
        if self.running: return
        self.running = True
        self.current_round = 1
        self.mode = "prep" if self.prep.get() > 0 else "fight"
        self.remaining = self.prep.get() if self.mode == "prep" else self.rlen.get()
        if self.mode == "fight": play("bell.wav")
        self.last_tick = time.time()
        self.update_display()
        self.app.save()
        self.app.root.after(100, self.tick)

    def stop(self):
        self.running = False
        self.mode = "idle"
        self.update_display()
        self.app.save()

    def reset(self):
        self.running = False
        self.mode = "idle"
        self.current_round = 0
        self.remaining = 0
        self.update_display()
        self.app.save()

    def pause(self):
        if not self.running: return
        self.running = False
        self.mode = "paused"
        self.update_display()
        self.app.save()

    def unpause(self):
        if self.mode != "paused": return
        self.running = True
        self.mode = "fight"
        self.last_tick = time.time()
        self.update_display()
        self.app.save()
        self.app.root.after(100, self.tick)

    def tick(self):
        if not self.running: return
        now = time.time()
        if now - self.last_tick >= 1:
            self.last_tick = now
            self.remaining -= 1
            if self.remaining <= 0: self.phase_end()
            else: self.notify()
        self.update_display()
        self.app.root.after(100, self.tick)

    def phase_end(self):
        play("bell.wav")
        if self.mode == "prep":
            self.mode = "fight"; self.remaining = self.rlen.get(); play("bell.wav")
        elif self.mode == "fight":
            if self.current_round >= self.rounds.get():
                self.running = False
                self.mode = "idle"
                self.remaining = 0
            else:
                self.mode = "rest"; self.remaining = self.rest.get(); play("bell.wav")
        elif self.mode == "rest":
            self.current_round += 1
            self.mode = "fight"; self.remaining = self.rlen.get(); play("bell.wav")
        self.app.save()

    def notify(self):
        if self.mode != "fight": return
        if self.n30.get() and self.remaining == 30: play("n30.wav")
        if self.n10.get() and self.remaining == 10: play("n10.wav")

    def update_display(self):
        m, s = divmod(self.remaining, 60)
        self.clock.config(text=f"{m:02d}:{s:02d}")
        colors = {"fight": "#66cc66", "rest": "#ff6666",
                  "prep": "#ffff99", "paused": "#9999ff", "idle": "#ccc"}
        self.clock.config(bg=colors.get(self.mode, "#ccc"))

    def serialize(self):
        return {
            "name": self.name.get(),
            "rounds": self.rounds.get(),
            "round_len": self.rlen.get(),
            "rest_len": self.rest.get(),
            "prep_len": self.prep.get(),
            "notify_30s": self.n30.get(),
            "notify_10s": self.n10.get(),
            "runtime": {
                "mode": self.mode,
                "current_round": self.current_round,
                "remaining": self.remaining,
                "running": self.running
            }
        }

# ---------------------- APP ----------------------

class BoxingTimerApp:
    def __init__(self, root):
        self.root = root
        root.title("Boxing Timer")
        ensure_wav()

        self.base_font = tkfont.Font(family="Helvetica", size=14)
        self.clock_font = tkfont.Font(family="Helvetica", size=64, weight="bold")

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True)

        self.tabs = []

        bottom = ttk.Frame(root); bottom.pack(fill="x", padx=10, pady=5)
        ttk.Button(bottom, text="Add Tab", command=self.add_tab).pack(side="left")
        ttk.Button(bottom, text="Close Tab", command=self.close_tab).pack(side="left", padx=5)
        ttk.Button(bottom, text="Save", command=self.save).pack(side="right")

        self.window_size = None
        self.load()

        if not self.tabs: self.add_tab()

        if self.window_size:
            w, h = self.window_size; root.geometry(f"{w}x{h}")
        else:
            root.geometry("700x500")

        root.bind("<Configure>", self.resize)
        root.protocol("WM_DELETE_WINDOW", self.close)

        root.update_idletasks()
        for t in self.tabs:
            e = tk.Event(); e.height = root.winfo_height(); t.scale(e)

    def add_tab(self, cfg=None):
        t = BoxingTab(self.nb, self, cfg)
        self.tabs.append(t)
        self.save()

    def close_tab(self):
        try: idx = self.nb.index("current")
        except: return
        self.nb.forget(self.tabs[idx].frame)
        del self.tabs[idx]
        self.save()
        if not self.tabs: self.add_tab()

    def stop_others(self, active):
        for t in self.tabs:
            if t is not active: t.stop()

    def save(self):
        if self.root.winfo_width() > 1:
            self.window_size = (self.root.winfo_width(), self.root.winfo_height())
        data = {"tabs": [t.serialize() for t in self.tabs],
                "window_size": self.window_size}
        with open(STATE_FILE, "w") as f: json.dump(data, f, indent=2)

    def load(self):
        if not os.path.exists(STATE_FILE): return
        try:
            with open(STATE_FILE) as f: data = json.load(f)
        except: return
        self.window_size = data.get("window_size")
        for cfg in data.get("tabs", []): self.add_tab(cfg)

    def resize(self, e):
        if e.widget == self.root and e.width > 1:
            self.window_size = (e.width, e.height)

    def close(self):
        self.save()
        self.root.destroy()

# ---------------------- MAIN ----------------------

def main():
    root = tk.Tk()
    BoxingTimerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
