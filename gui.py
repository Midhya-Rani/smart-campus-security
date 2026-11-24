"""Tkinter desktop dashboard for the AI Smart Campus Security System."""
import csv
import time as _time
import tkinter as tk
from collections import Counter
from datetime import datetime, date
from tkinter import ttk, messagebox, filedialog

import cv2
from PIL import Image, ImageTk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from .classifier import EventClassifier
from .database import Database
from .detector import PersonDetector
from .dsa import AlertManager, LinkedList
from .graph import CampusGraph
from .models import SEVERITY_NAMES
from .rules import DEFAULT_RULES, Rule, RuleEngine, parse_time

DETECT_EVERY = 3          # run the AI model on every Nth frame
ALERT_COOLDOWN = 10       # seconds between repeated alerts for the same location
SECURITY_BASE = "Security Office"

# Sky-blue theme: blue background, light cards (fg/muted = text on blue, pfg/pmuted = text on cards)
P = dict(bg="#3a86d8", panel="#f3f7fd", fg="#ffffff", muted="#d6e8ff", pfg="#1b2a41",
         pmuted="#5b6b82", accent="#12408a", accent2="#7dd3fc", header="#0f2f63",
         edge="#a9c4e8", high="#f8c9c9", med="#fde6c4", low="#cdeedb")
SEV_COLORS = {"High": "#e74c3c", "Medium": "#f39c12", "Low": "#27ae60"}


class MapCanvas(tk.Canvas):
    """Draws the campus graph; can highlight a route, explored nodes, alerts."""
    W, H, PAD = 640, 430, 45

    def __init__(self, parent, graph: CampusGraph):
        super().__init__(parent, width=self.W, height=self.H, bg=P["panel"],
                         highlightthickness=1, highlightbackground=P["edge"])
        self.graph = graph

    def _xy(self, name):
        x, y = self.graph.pos[name]
        return (self.PAD + x / 100 * (self.W - 2 * self.PAD),
                self.PAD + y / 100 * (self.H - 2 * self.PAD))

    def draw(self, path=None, explored=(), alert_locations=()):
        self.delete("all")
        path = path or []
        path_edges = {frozenset(e) for e in zip(path, path[1:])}
        for a, b in self.graph.g.edges:
            on_path = frozenset((a, b)) in path_edges
            (x1, y1), (x2, y2) = self._xy(a), self._xy(b)
            self.create_line(x1, y1, x2, y2, width=4 if on_path else 1,
                             fill="#e67e22" if on_path else P["pmuted"])
            self.create_text((x1 + x2) / 2, (y1 + y2) / 2 - 7, fill=P["pmuted"],
                             text=str(self.graph.weight(a, b)), font=("Arial", 7))
        for name in self.graph.g.nodes:
            x, y = self._xy(name)
            if name in alert_locations:
                color, r = "#e74c3c", 11          # alert nodes are bigger
            elif name in path:
                color, r = "#27ae60", 9
            elif name in explored:
                color, r = "#f1c40f", 9
            else:
                color, r = "#3498db", 9
            self.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=P["pfg"])
            self.create_text(x, y + 21, text=name, font=("Arial", 9, "bold"), fill=P["pfg"])


class App(tk.Tk):
    def __init__(self, db_path: str = "campus_security.db"):
        super().__init__()
        self.title("AI Smart Campus Security System")
        self.geometry("1200x780")
        self.minsize(1050, 680)

        # --- core components -------------------------------------------
        self.db = Database(db_path)
        self.graph = CampusGraph()
        if not self.db.get_rules():
            for r in DEFAULT_RULES:
                self.db.save_rule(r)
        self.engine = RuleEngine(self.db.get_rules())
        self.manager = AlertManager()
        self.history = LinkedList()                     # in-memory event history
        for a in self.db.get_events(newest_first=False):
            self.history.append(a)
            if a.status == "pending":
                self.manager.add(a)
        self.classifier = EventClassifier()
        self.classifier.train()
        self.detector = None                            # loaded lazily (model is heavy)

        # --- video state -----------------------------------------------
        self.cap = None
        self._after_id = None
        self.frame_idx = 0
        self.last_dets = []
        self.video_path = ""
        self._last_alert = {}
        self._photo = None
        self.paused = False
        self._last_shown = None
        self._fps = 0.0
        self._t_prev = None

        self._setup_style()
        self._build_ui()
        self._bind_shortcuts()
        self.refresh_all()
        self._tick()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # =====================================================================
    # Style
    # =====================================================================
    def _setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        self.configure(bg=P["bg"])
        self.option_add("*TCombobox*Listbox.background", P["panel"])
        self.option_add("*TCombobox*Listbox.foreground", P["pfg"])
        self.option_add("*TCombobox*Listbox.selectBackground", P["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        s.configure(".", background=P["bg"], foreground=P["fg"], fieldbackground=P["panel"],
                    font=("Segoe UI", 10), bordercolor=P["edge"])
        s.configure("Muted.TLabel", foreground=P["muted"])
        s.configure("TNotebook", borderwidth=0)
        s.configure("TNotebook.Tab", padding=(16, 8), background=P["panel"], foreground=P["pmuted"])
        s.map("TNotebook.Tab", background=[("selected", P["accent"])],
              foreground=[("selected", "#ffffff")])
        s.configure("TButton", padding=(10, 5), background=P["panel"], foreground=P["pfg"])
        s.map("TButton", background=[("active", P["edge"])])
        s.configure("Accent.TButton", background=P["accent"], foreground="#ffffff")
        s.map("Accent.TButton", background=[("active", P["accent"])])
        for w in ("TEntry", "TCombobox", "TSpinbox"):
            s.configure(w, fieldbackground=P["panel"], foreground=P["pfg"])
        s.configure("TCombobox", background=P["panel"], arrowcolor=P["pfg"])
        s.configure("Treeview", background=P["panel"], fieldbackground=P["panel"],
                    foreground=P["pfg"], rowheight=26)
        s.configure("Treeview.Heading", background=P["edge"], foreground=P["pfg"],
                    font=("Segoe UI", 10, "bold"), padding=5)
        s.map("Treeview", background=[("selected", P["accent"])],
              foreground=[("selected", "#ffffff")])
        s.configure("Header.TFrame", background=P["header"])
        s.configure("Header.TLabel", background=P["header"], foreground="#ffffff")
        s.configure("Banner.TLabel", background=P["header"], foreground="#2ecc71",
                    font=("Segoe UI", 10, "bold"))
        s.configure("BannerAlert.TLabel", background="#c0392b", foreground="#ffffff",
                    font=("Segoe UI", 10, "bold"), padding=(10, 3))
        s.configure("Card.TFrame", background=P["panel"], relief="solid", borderwidth=1)
        s.configure("CardTitle.TLabel", background=P["panel"], foreground=P["pmuted"],
                    font=("Segoe UI", 9))
        s.configure("CardValue.TLabel", background=P["panel"], foreground=P["pfg"],
                    font=("Segoe UI", 22, "bold"))

    def _draw_strip(self, _e=None):
        """Horizontal two-colour gradient line under the header."""
        c = self.strip
        c.delete("all")
        w = max(c.winfo_width(), 2)
        c1 = [int(P["accent"][i:i + 2], 16) for i in (1, 3, 5)]
        c2 = [int(P["accent2"][i:i + 2], 16) for i in (1, 3, 5)]
        steps = min(w, 200)
        for i in range(steps):
            t = i / max(steps - 1, 1)
            col = "#%02x%02x%02x" % tuple(int(c1[k] + (c2[k] - c1[k]) * t) for k in range(3))
            c.create_rectangle(i * w / steps, 0, (i + 1) * w / steps + 1, 5, fill=col, outline=col)

    def _make_text(self, parent, **kw):
        return tk.Text(parent, bg=P["panel"], fg=P["pfg"], relief="flat", insertbackground=P["pfg"],
                       highlightthickness=1, highlightbackground=P["edge"],
                       font=("Consolas", 10), **kw)

    # =====================================================================
    # UI construction
    # =====================================================================
    def _build_ui(self):
        self.status_var = tk.StringVar(value="Ready.  (F5 refresh | Ctrl+1..7 tabs)")
        ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w",
                  padding=4).pack(side="bottom", fill="x")

        header = ttk.Frame(self, style="Header.TFrame", padding=(12, 8))
        header.pack(side="top", fill="x")
        ttk.Label(header, text="AI Smart Campus Security", style="Header.TLabel",
                  font=("Segoe UI", 15, "bold")).pack(side="left")
        self.clock_var = tk.StringVar()
        ttk.Label(header, textvariable=self.clock_var, style="Header.TLabel",
                  font=("Consolas", 11)).pack(side="right", padx=12)
        self.banner_var = tk.StringVar(value="System secure")
        self.banner = ttk.Label(header, textvariable=self.banner_var, style="Banner.TLabel")
        self.banner.pack(side="right", padx=12)

        self.strip = tk.Canvas(self, height=5, highlightthickness=0, bd=0)
        self.strip.pack(side="top", fill="x")
        self.strip.bind("<Configure>", self._draw_strip)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs = {}
        for name, builder in [("Dashboard", self._tab_dashboard),
                              ("Video Monitoring", self._tab_video),
                              ("Security Alerts", self._tab_alerts),
                              ("Campus Map", self._tab_map),
                              ("Route Planning", self._tab_route),
                              ("Event History", self._tab_history),
                              ("Security Rules", self._tab_rules)]:
            frame = ttk.Frame(self.nb, padding=10)
            self.nb.add(frame, text=name)
            self.tabs[name] = frame
            builder(frame)
        for tree in (self.alert_tree, self.hist_tree):
            tree.tag_configure("High", background=P["high"], foreground=P["pfg"])
            tree.tag_configure("Medium", background=P["med"], foreground=P["pfg"])
            tree.tag_configure("Low", background=P["low"], foreground=P["pfg"])

    def _bind_shortcuts(self):
        self.bind("<F5>", lambda _e: self.refresh_all())
        for i, name in enumerate(self.tabs, 1):
            self.bind(f"<Control-Key-{i}>", lambda _e, n=name: self.nb.select(self.tabs[n]))

    def _tick(self):
        """Every second: clock + pending-alert banner."""
        self.clock_var.set(datetime.now().strftime("%a %d %b %Y   %H:%M:%S"))
        pending = self.manager.pending_count()
        self.banner_var.set(f"  {pending} pending alert(s)  " if pending else "System secure")
        self.banner.configure(style="BannerAlert.TLabel" if pending else "Banner.TLabel")
        self.after(1000, self._tick)

    def _rebuild_manager(self):
        """Re-sync the in-memory alert queues from the database."""
        self.manager = AlertManager()
        for a in self.db.get_events(newest_first=False):
            if a.status == "pending":
                self.manager.add(a)

    # ---- generic helpers -------------------------------------------------
    @staticmethod
    def _sort_tree(tree, col, reverse):
        def key(item):
            try:
                return (0, float(item[0]))
            except ValueError:
                return (1, item[0].lower())
        rows = sorted(((tree.set(k, col), k) for k in tree.get_children("")), key=key, reverse=reverse)
        for i, (_v, k) in enumerate(rows):
            tree.move(k, "", i)
        tree.heading(col, command=lambda: App._sort_tree(tree, col, not reverse))

    def _make_tree(self, parent, cols, widths, height=16):
        wrap = ttk.Frame(parent)
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=height)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        for c, w in zip(cols, widths):
            tree.heading(c, text=c.replace("_", " ").title(),
                         command=lambda c=c: self._sort_tree(tree, c, False))
            tree.column(c, width=w, anchor="w")
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return wrap, tree

    @staticmethod
    def _matches(a, query, sev):
        if sev != "All" and a.severity_name != sev:
            return False
        return query.strip().lower() in f"{a.location} {a.description} {a.category}".lower()

    # ---- Dashboard ------------------------------------------------------
    def _tab_dashboard(self, f):
        cards = ttk.Frame(f)
        cards.pack(fill="x")
        self.card_vars = {}
        for key, title in [("total", "TOTAL EVENTS"), ("today", "EVENTS TODAY"),
                           ("pending", "PENDING ALERTS"), ("high", "HIGH-SEVERITY"),
                           ("backend", "AI BACKEND")]:
            box = ttk.Frame(cards, style="Card.TFrame", padding=12)
            box.pack(side="left", expand=True, fill="x", padx=4)
            ttk.Label(box, text=title, style="CardTitle.TLabel").pack(anchor="w")
            var = tk.StringVar(value="-")
            ttk.Label(box, textvariable=var, style="CardValue.TLabel").pack(anchor="w")
            self.card_vars[key] = var
        self.fig = Figure(figsize=(10, 4), dpi=100)
        self.canvas_stats = FigureCanvasTkAgg(self.fig, master=f)
        self.canvas_stats.get_tk_widget().pack(fill="both", expand=True, pady=8)
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Button(bar, text="Refresh statistics (F5)", style="Accent.TButton",
                   command=self.refresh_all).pack(side="right")
        ttk.Button(bar, text="Clear all data", command=self.clear_all_data).pack(side="right", padx=8)

    def clear_all_data(self):
        """Delete every recorded event (rules are kept) and reset all in-memory state."""
        total = self.db.count_events()
        if total == 0:
            messagebox.showinfo("Clear data", "There is no data to clear.")
            return
        if not messagebox.askyesno(
                "Clear all data",
                f"This will permanently delete all {total} recorded events "
                "(alerts and history).\nSecurity rules will NOT be deleted.\n\n"
                "Tip: use Event History > Export CSV first if you want a backup.\n\n"
                "Continue?", icon="warning"):
            return
        self.db.conn.execute("DELETE FROM events")
        try:                                   # restart event ids from 1
            self.db.conn.execute("DELETE FROM sqlite_sequence WHERE name='events'")
        except Exception:
            pass
        self.db.conn.commit()
        self.manager = AlertManager()
        self.history = LinkedList()
        self._last_alert.clear()
        self.refresh_all()
        self.status_var.set("All events cleared. Dashboard reset.")

    @staticmethod
    def _style_ax(ax):
        ax.set_facecolor(P["panel"])
        ax.tick_params(colors=P["pfg"])
        ax.title.set_color(P["pfg"])
        ax.xaxis.label.set_color(P["pfg"])
        ax.yaxis.label.set_color(P["pfg"])
        for sp in ax.spines.values():
            sp.set_color(P["edge"])

    def _refresh_dashboard(self):
        events = self.db.get_events()
        today = date.today()
        self.card_vars["total"].set(str(self.db.count_events()))
        self.card_vars["today"].set(str(sum(1 for a in events if a.timestamp.date() == today)))
        self.card_vars["pending"].set(str(self.manager.pending_count()))
        self.card_vars["high"].set(str(self.db.count_events(min_severity=3)))
        self.card_vars["backend"].set(self.detector.backend if self.detector else "not loaded")

        df = self.db.events_dataframe()
        self.fig.clear()
        self.fig.patch.set_facecolor(P["panel"])
        if df.empty:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "No events recorded yet", ha="center", va="center",
                    fontsize=14, color=P["pfg"])
            ax.axis("off")
        else:
            ax1 = self.fig.add_subplot(131)
            df.groupby("location").size().sort_values().plot.barh(ax=ax1, color="#3498db")
            ax1.set_title("Events by location")
            ax1.set_xlabel("count")
            self._style_ax(ax1)

            ax2 = self.fig.add_subplot(132)
            hours = df.groupby("hour").size().reindex(range(24), fill_value=0)
            ax2.bar(hours.index, hours.values, color="#e67e22")
            ax2.set_title("Events by hour of day")
            ax2.set_xlabel("hour")
            self._style_ax(ax2)

            ax3 = self.fig.add_subplot(133)
            counts = Counter(a.severity_name for a in events)
            ax3.pie(list(counts.values()), labels=list(counts), autopct="%1.0f%%",
                    colors=[SEV_COLORS.get(k, "#95a5a6") for k in counts],
                    textprops={"color": P["pfg"]})
            ax3.set_title("Severity split", color=P["pfg"])
            self.fig.tight_layout()
        self.canvas_stats.draw()

    # ---- Video Monitoring ----------------------------------------------
    def _tab_video(self, f):
        top = ttk.Frame(f)
        top.pack(fill="x")
        self.source_var = tk.StringVar(value="Video file")
        ttk.Label(top, text="Source:").grid(row=0, column=0, padx=3)
        ttk.Combobox(top, textvariable=self.source_var, values=["Webcam", "Video file"],
                     state="readonly", width=11).grid(row=0, column=1)
        ttk.Button(top, text="Browse video...", command=self._browse_video).grid(row=0, column=2, padx=4)
        ttk.Label(top, text="Camera location:").grid(row=0, column=3, padx=3)
        self.cam_loc_var = tk.StringVar(value="Computer Lab")
        ttk.Combobox(top, textvariable=self.cam_loc_var, values=self.graph.locations(),
                     state="readonly", width=16).grid(row=0, column=4)
        ttk.Label(top, text="Simulated time (HH:MM, empty = now):").grid(row=0, column=5, padx=3)
        self.sim_time_var = tk.StringVar(value="")
        ttk.Entry(top, textvariable=self.sim_time_var, width=7).grid(row=0, column=6)

        sett = ttk.Frame(f)
        sett.pack(fill="x", pady=(8, 0))
        self.detect_every_var = tk.IntVar(value=DETECT_EVERY)
        self.cooldown_var = tk.IntVar(value=ALERT_COOLDOWN)
        self.sound_var = tk.BooleanVar(value=True)
        ttk.Label(sett, text="Detect every N frames:").pack(side="left", padx=3)
        ttk.Spinbox(sett, from_=1, to=30, width=4, textvariable=self.detect_every_var).pack(side="left")
        ttk.Label(sett, text="Alert cooldown (s):").pack(side="left", padx=(14, 3))
        ttk.Spinbox(sett, from_=0, to=300, width=5, textvariable=self.cooldown_var).pack(side="left")
        ttk.Checkbutton(sett, text="Alert sound", variable=self.sound_var).pack(side="left", padx=14)
        self.fps_var = tk.StringVar(value="FPS: -   People: -")
        ttk.Label(sett, textvariable=self.fps_var, style="Muted.TLabel").pack(side="right")

        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Start", style="Accent.TButton", command=self.start_video).pack(side="left", padx=3)
        self.pause_btn = ttk.Button(btns, text="Pause", command=self.toggle_pause)
        self.pause_btn.pack(side="left", padx=3)
        ttk.Button(btns, text="Stop", command=self.stop_video).pack(side="left", padx=3)
        ttk.Button(btns, text="Save snapshot", command=self.save_snapshot).pack(side="left", padx=3)
        ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(btns, text="No video? Simulate:").pack(side="left")
        self.sim_count_var = tk.IntVar(value=1)
        ttk.Spinbox(btns, from_=1, to=10, width=4, textvariable=self.sim_count_var).pack(side="left", padx=3)
        ttk.Label(btns, text="person(s)").pack(side="left")
        ttk.Button(btns, text="Simulate detection", command=self.simulate_detection).pack(side="left", padx=6)

        self.video_label = ttk.Label(f, text="Video preview appears here", anchor="center",
                                     background=P["header"], foreground=P["muted"])
        self.video_label.pack(fill="both", expand=True)

    def _browse_video(self):
        path = filedialog.askopenfilename(
            title="Select sample CCTV video",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")])
        if path:
            self.video_path = path
            self.source_var.set("Video file")
            self.status_var.set(f"Selected video: {path}")

    def _now(self) -> datetime:
        text = self.sim_time_var.get().strip()
        if text:
            try:
                return datetime.combine(date.today(), parse_time(text))
            except ValueError:
                self.status_var.set("Invalid simulated time - use HH:MM. Using real time.")
        return datetime.now()

    def start_video(self):
        if self.cap is not None:
            return
        if self.source_var.get() == "Webcam":
            source = 0
        else:
            if not self.video_path:
                messagebox.showinfo("No video", "Please click 'Browse video...' first.")
                return
            source = self.video_path
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            messagebox.showerror("Error", "Could not open the video source.")
            return
        if self.detector is None:
            self.status_var.set("Loading AI model (first time may download it)...")
            self.update_idletasks()
            self.detector = PersonDetector()
        self.cap, self.frame_idx, self.last_dets = cap, 0, []
        self.paused, self._t_prev = False, None
        self.pause_btn.configure(text="Pause")
        self.status_var.set(f"Monitoring started - AI backend: {self.detector.backend}")
        self._refresh_dashboard()
        self._video_step()

    def toggle_pause(self):
        if self.cap is None:
            return
        self.paused = not self.paused
        self.pause_btn.configure(text="Resume" if self.paused else "Pause")
        self.status_var.set("Monitoring paused." if self.paused else "Monitoring resumed.")

    def save_snapshot(self):
        if self._last_shown is None:
            messagebox.showinfo("Snapshot", "No frame available yet - start the video first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png", initialfile=f"snapshot_{datetime.now():%Y%m%d_%H%M%S}.png",
            filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg")])
        if path:
            cv2.imwrite(path, self._last_shown)
            self.status_var.set(f"Snapshot saved: {path}")

    def stop_video(self):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.paused = False
        self.pause_btn.configure(text="Pause")
        self.fps_var.set("FPS: -   People: -")
        self.video_label.configure(image="", text="Video stopped")
        self._photo = None

    def _video_step(self):
        if self.cap is None:
            return
        if self.paused:
            self._after_id = self.after(120, self._video_step)
            return
        ok, frame = self.cap.read()
        if not ok:
            self.stop_video()
            self.status_var.set("Video finished.")
            return
        self.frame_idx += 1
        try:
            n = max(1, int(self.detect_every_var.get()))
        except (tk.TclError, ValueError):
            n = DETECT_EVERY
        if (self.frame_idx - 1) % n == 0:
            self.last_dets = self.detector.detect(frame)
            self._process_detection(self.cam_loc_var.get(), len(self.last_dets), source="video")
        shown = self.detector.draw(frame, self.last_dets)

        # FPS (smoothed) + overlay text
        now = _time.time()
        if self._t_prev is not None:
            inst = 1.0 / max(now - self._t_prev, 1e-6)
            self._fps = inst if self._fps == 0 else 0.9 * self._fps + 0.1 * inst
        self._t_prev = now
        people = len(self.last_dets)
        self.fps_var.set(f"FPS: {self._fps:.1f}   People: {people}")
        cv2.putText(shown, f"{self.cam_loc_var.get()} | People: {people} | {datetime.now():%H:%M:%S}",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
        self._last_shown = shown

        img = Image.fromarray(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB))
        img.thumbnail((max(self.video_label.winfo_width(), 320),
                       max(self.video_label.winfo_height(), 240)))
        self._photo = ImageTk.PhotoImage(img)
        self.video_label.configure(image=self._photo, text="")
        self._after_id = self.after(15, self._video_step)

    def simulate_detection(self):
        self._process_detection(self.cam_loc_var.get(), self.sim_count_var.get(), source="sim")

    def _process_detection(self, location: str, count: int, source: str):
        """The pipeline step: detection -> rule check -> alert -> queues/DB/GUI."""
        if count <= 0:
            return
        now = self._now()
        alert = self.engine.evaluate(location, count, now)
        if alert is None:
            self.status_var.set(f"{count} person(s) in {location} at {now:%H:%M} - access allowed.")
            return
        if source == "video":
            try:
                cooldown = int(self.cooldown_var.get())
            except (tk.TclError, ValueError):
                cooldown = ALERT_COOLDOWN
            if _time.time() - self._last_alert.get(location, 0) < cooldown:
                return
            self._last_alert[location] = _time.time()
        alert.category = self.classifier.predict(now.hour, count, alert.severity)
        alert.id = self.db.add_event(alert)
        self.manager.add(alert)
        self.history.append(alert)
        if self.sound_var.get():
            self.bell()
        self.status_var.set(f"ALERT [{alert.severity_name}]: {alert.description}")
        self.refresh_all()

    # ---- Security Alerts -------------------------------------------------
    def _tab_alerts(self, f):
        top = ttk.Frame(f)
        top.pack(fill="x")
        self.alert_mode = tk.StringVar(value="priority")
        ttk.Radiobutton(top, text="Priority order (Priority Queue)", value="priority",
                        variable=self.alert_mode, command=self._refresh_alerts).pack(side="left", padx=4)
        ttk.Radiobutton(top, text="Arrival order (FIFO Queue)", value="fifo",
                        variable=self.alert_mode, command=self._refresh_alerts).pack(side="left", padx=4)
        ttk.Button(top, text="Review next alert", style="Accent.TButton",
                   command=self.review_next).pack(side="right", padx=4)
        ttk.Button(top, text="Mark selected reviewed", command=self.review_selected).pack(side="right", padx=4)
        ttk.Button(top, text="Route to selected alert", command=self.route_to_alert).pack(side="right", padx=4)

        flt = ttk.Frame(f)
        flt.pack(fill="x", pady=(8, 0))
        ttk.Label(flt, text="Search:").pack(side="left")
        self.alert_search = tk.StringVar()
        ttk.Entry(flt, textvariable=self.alert_search, width=26).pack(side="left", padx=4)
        self.alert_search.trace_add("write", lambda *_: self._refresh_alerts())
        ttk.Label(flt, text="Severity:").pack(side="left", padx=(12, 0))
        self.alert_sev = tk.StringVar(value="All")
        cb = ttk.Combobox(flt, textvariable=self.alert_sev, state="readonly", width=10,
                          values=["All"] + list(SEVERITY_NAMES.values()))
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._refresh_alerts())
        self.alert_count = ttk.Label(flt, text="", style="Muted.TLabel")
        self.alert_count.pack(side="right")

        cols = ("id", "priority", "location", "description", "time", "category")
        wrap, self.alert_tree = self._make_tree(f, cols, (50, 80, 130, 520, 140, 90), height=18)
        wrap.pack(fill="both", expand=True, pady=6)
        self.alert_tree.bind("<Double-1>", lambda _e: self._show_detail(self.alert_tree))
        ttk.Label(f, text="Tip: double-click an alert for details; click a column heading to sort.",
                  style="Muted.TLabel").pack(anchor="w")

    def _refresh_alerts(self):
        self.alert_tree.delete(*self.alert_tree.get_children())
        items = (self.manager.pending_priority() if self.alert_mode.get() == "priority"
                 else self.manager.pending_fifo())
        shown = 0
        for a in items:
            if not self._matches(a, self.alert_search.get(), self.alert_sev.get()):
                continue
            shown += 1
            self.alert_tree.insert("", "end", iid=str(a.id), tags=(a.severity_name,),
                                   values=(a.id, a.severity_name, a.location, a.description,
                                           f"{a.timestamp:%Y-%m-%d %H:%M}", a.category))
        self.alert_count.configure(text=f"Showing {shown} of {len(items)} pending")

    def _show_detail(self, tree):
        sel = tree.selection()
        if not sel:
            return
        win = tk.Toplevel(self)
        win.title("Event details")
        win.configure(bg=P["bg"])
        win.geometry("520x300")
        t = self._make_text(win, wrap="word")
        t.pack(fill="both", expand=True, padx=10, pady=10)
        for c, v in zip(tree["columns"], tree.item(sel[0])["values"]):
            t.insert("end", f"{c.replace('_', ' ').title():<14}: {v}\n")
        t.configure(state="disabled")

    def review_next(self):
        mode = self.alert_mode.get()
        alert = self.manager.next_priority() if mode == "priority" else self.manager.next_fifo()
        if alert is None:
            messagebox.showinfo("Alerts", "No pending alerts.")
            return
        self.db.set_status(alert.id, "reviewed")
        self.status_var.set(f"Reviewed alert #{alert.id}: {alert.description}")
        self.refresh_all()

    def review_selected(self):
        sel = self.alert_tree.selection()
        if not sel:
            messagebox.showinfo("Alerts", "Select an alert from the list first.")
            return
        self.db.set_status(int(sel[0]), "reviewed")
        self._rebuild_manager()
        self.status_var.set(f"Alert #{sel[0]} marked as reviewed.")
        self.refresh_all()

    def route_to_alert(self):
        sel = self.alert_tree.selection()
        if sel:
            target = self.alert_tree.item(sel[0])["values"][2]
        else:
            pending = self.manager.pending_priority()
            if not pending:
                messagebox.showinfo("Alerts", "No pending alerts.")
                return
            target = pending[0].location
        self.route_start.set(SECURITY_BASE)
        self.route_end.set(target)
        self.route_algo.set("A*")
        self.nb.select(self.tabs["Route Planning"])
        self.find_route()

    # ---- Campus Map ------------------------------------------------------
    def _tab_map(self, f):
        self.map_canvas = MapCanvas(f, self.graph)
        self.map_canvas.pack(side="left", padx=4)
        side = ttk.Frame(f)
        side.pack(side="left", fill="both", expand=True, padx=8)
        ttk.Label(side, text="Traversal start:").pack(anchor="w")
        self.trav_start = tk.StringVar(value=SECURITY_BASE)
        ttk.Combobox(side, textvariable=self.trav_start, values=self.graph.locations(),
                     state="readonly").pack(fill="x")
        ttk.Button(side, text="Show BFS order", command=lambda: self._traverse("BFS")).pack(fill="x", pady=3)
        ttk.Button(side, text="Show DFS order", command=lambda: self._traverse("DFS")).pack(fill="x")
        self.trav_text = self._make_text(side, height=14, width=34, wrap="word")
        self.trav_text.pack(fill="both", expand=True, pady=6)
        legend = ttk.Frame(side)
        legend.pack(anchor="w")
        for color, label in [("#e74c3c", "Pending alert"), ("#27ae60", "On route"),
                             ("#f1c40f", "Explored"), ("#3498db", "Normal")]:
            row = ttk.Frame(legend)
            row.pack(anchor="w")
            dot = tk.Canvas(row, width=14, height=14, highlightthickness=0, bg=P["bg"])
            dot.create_oval(2, 2, 12, 12, fill=color, outline="")
            dot.pack(side="left")
            ttk.Label(row, text=label, style="Muted.TLabel").pack(side="left", padx=4)

    def _traverse(self, kind):
        start = self.trav_start.get()
        order = self.graph.bfs_order(start) if kind == "BFS" else self.graph.dfs_order(start)
        self.trav_text.delete("1.0", "end")
        self.trav_text.insert("end", f"{kind} from {start}:\n\n" + "\n".join(
            f"{i}. {n}" for i, n in enumerate(order, 1)))
        self._draw_maps(explored=order)

    def _draw_maps(self, path=None, explored=()):
        alerts = {a.location for a in self.manager.pending_fifo()}
        self.map_canvas.draw(path, explored, alerts)
        if hasattr(self, "route_canvas"):
            self.route_canvas.draw(path, explored, alerts)

    # ---- Route Planning --------------------------------------------------
    def _tab_route(self, f):
        top = ttk.Frame(f)
        top.pack(fill="x")
        locs = self.graph.locations()
        self.route_start = tk.StringVar(value=SECURITY_BASE)
        self.route_end = tk.StringVar(value="Physics Lab")
        self.route_algo = tk.StringVar(value="A*")
        for text, var, vals in [("From:", self.route_start, locs), ("To:", self.route_end, locs),
                                ("Algorithm:", self.route_algo, ["A*", "BFS"])]:
            ttk.Label(top, text=text).pack(side="left", padx=3)
            ttk.Combobox(top, textvariable=var, values=vals, state="readonly",
                         width=16).pack(side="left")
        ttk.Button(top, text="Swap", command=self._swap_route).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Find route", style="Accent.TButton",
                   command=self.find_route).pack(side="left", padx=8)
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=6)
        self.route_canvas = MapCanvas(body, self.graph)
        self.route_canvas.pack(side="left", padx=4)
        self.route_text = self._make_text(body, width=40, wrap="word")
        self.route_text.pack(side="left", fill="both", expand=True, padx=8)

    def _swap_route(self):
        s, e = self.route_start.get(), self.route_end.get()
        self.route_start.set(e)
        self.route_end.set(s)

    def find_route(self):
        s, e = self.route_start.get(), self.route_end.get()
        if not s or not e:
            return
        res_a, res_b = self.graph.astar(s, e), self.graph.bfs_path(s, e)
        chosen = res_a if self.route_algo.get() == "A*" else res_b
        t = self.route_text
        t.delete("1.0", "end")
        for r in (chosen, res_b if chosen is res_a else res_a):
            tag = "SELECTED" if r is chosen else "for comparison"
            t.insert("end", f"[{r.algorithm}] ({tag})\n")
            if r.found:
                t.insert("end", "Route: " + " -> ".join(r.path) + "\n"
                         f"Stops: {len(r.path) - 1}   Distance: {r.cost}\n"
                         f"Nodes explored: {len(r.explored)}\n\n")
            else:
                t.insert("end", "No route found.\n\n")
        t.insert("end", "A* minimises DISTANCE; BFS minimises the NUMBER OF STOPS.")
        self._draw_maps(path=chosen.path, explored=chosen.explored)

    # ---- Event History ---------------------------------------------------
    def _tab_history(self, f):
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Status:").pack(side="left")
        self.hist_filter = tk.StringVar(value="all")
        cb = ttk.Combobox(top, textvariable=self.hist_filter, values=["all", "pending", "reviewed"],
                          state="readonly", width=10)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._refresh_history())
        ttk.Label(top, text="Severity:").pack(side="left", padx=(10, 0))
        self.hist_sev = tk.StringVar(value="All")
        cb2 = ttk.Combobox(top, textvariable=self.hist_sev, state="readonly", width=10,
                           values=["All"] + list(SEVERITY_NAMES.values()))
        cb2.pack(side="left", padx=4)
        cb2.bind("<<ComboboxSelected>>", lambda _e: self._refresh_history())
        ttk.Label(top, text="Search:").pack(side="left", padx=(10, 0))
        self.hist_search = tk.StringVar()
        ttk.Entry(top, textvariable=self.hist_search, width=22).pack(side="left", padx=4)
        self.hist_search.trace_add("write", lambda *_: self._refresh_history())
        ttk.Button(top, text="Export CSV", style="Accent.TButton",
                   command=self.export_csv).pack(side="right")

        cols = ("id", "time", "location", "severity", "people", "category", "status", "description")
        wrap, self.hist_tree = self._make_tree(
            f, cols, (50, 140, 120, 70, 55, 90, 80, 420), height=16)
        wrap.pack(fill="both", expand=True, pady=6)
        self.hist_tree.bind("<Double-1>", lambda _e: self._show_detail(self.hist_tree))
        self.hist_count = ttk.Label(f, text="", style="Muted.TLabel")
        self.hist_count.pack(anchor="w")
        ttk.Label(f, text="Latest 5 events (linked-list traversal):").pack(anchor="w", pady=(6, 0))
        self.ll_label = ttk.Label(f, text="", style="Muted.TLabel", justify="left")
        self.ll_label.pack(anchor="w")

    def _refresh_history(self):
        self.hist_tree.delete(*self.hist_tree.get_children())
        flt = self.hist_filter.get()
        events = self.db.get_events(status=None if flt == "all" else flt)
        shown = 0
        for a in events:
            if not self._matches(a, self.hist_search.get(), self.hist_sev.get()):
                continue
            shown += 1
            self.hist_tree.insert("", "end", tags=(a.severity_name,), values=(
                a.id, f"{a.timestamp:%Y-%m-%d %H:%M}", a.location, a.severity_name,
                a.person_count, a.category, a.status, a.description))
        self.hist_count.configure(text=f"Showing {shown} of {len(events)} events")
        latest = self.history.last(5)
        self.ll_label.configure(text="\n".join(
            f"#{a.id}  {a.timestamp:%H:%M}  {a.location}" for a in reversed(latest)) or "(none)")

    def export_csv(self):
        """Exports exactly the rows currently visible in the history table."""
        rows = [self.hist_tree.item(k)["values"] for k in self.hist_tree.get_children()]
        if not rows:
            messagebox.showinfo("Export", "No events to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(self.hist_tree["columns"])
                w.writerows(rows)
            self.status_var.set(f"Exported {len(rows)} events to {path}")

    # ---- Security Rules --------------------------------------------------
    def _tab_rules(self, f):
        cols = ("location", "allowed_from", "allowed_to", "severity", "enabled")
        wrap, self.rule_tree = self._make_tree(f, cols, (160,) * 5, height=10)
        wrap.pack(fill="x")
        self.rule_tree.bind("<<TreeviewSelect>>", self._rule_selected)

        form = ttk.LabelFrame(f, text="Add / update rule", padding=10)
        form.pack(fill="x", pady=10)
        self.r_loc = tk.StringVar(value="Computer Lab")
        self.r_from = tk.StringVar(value="08:00")
        self.r_to = tk.StringVar(value="20:00")
        self.r_sev = tk.StringVar(value="High")
        self.r_en = tk.BooleanVar(value=True)
        ttk.Label(form, text="Location:").grid(row=0, column=0)
        ttk.Combobox(form, textvariable=self.r_loc, values=self.graph.locations(),
                     state="readonly", width=16).grid(row=0, column=1, padx=4)
        ttk.Label(form, text="Allowed from:").grid(row=0, column=2)
        ttk.Entry(form, textvariable=self.r_from, width=7).grid(row=0, column=3, padx=4)
        ttk.Label(form, text="to:").grid(row=0, column=4)
        ttk.Entry(form, textvariable=self.r_to, width=7).grid(row=0, column=5, padx=4)
        ttk.Label(form, text="Severity:").grid(row=0, column=6)
        ttk.Combobox(form, textvariable=self.r_sev, values=list(SEVERITY_NAMES.values()),
                     state="readonly", width=8).grid(row=0, column=7, padx=4)
        ttk.Checkbutton(form, text="Enabled", variable=self.r_en).grid(row=0, column=8, padx=4)
        ttk.Button(form, text="Save rule", style="Accent.TButton",
                   command=self.save_rule).grid(row=0, column=9, padx=6)
        ttk.Button(f, text="Delete selected rule", command=self.delete_rule).pack(anchor="w")
        ttk.Label(f, text="A rule defines WHEN people are allowed in a location (a window like "
                          "22:00 to 06:00 may cross midnight).\nDetecting people outside that "
                          "window raises an alert.", style="Muted.TLabel").pack(anchor="w", pady=8)

    def _rule_selected(self, _e):
        sel = self.rule_tree.selection()
        if sel:
            loc, a, b, sev, en = self.rule_tree.item(sel[0])["values"]
            self.r_loc.set(loc); self.r_from.set(a); self.r_to.set(b)
            self.r_sev.set(sev); self.r_en.set(en == "yes")

    def save_rule(self):
        try:
            rule = Rule(self.r_loc.get(), parse_time(self.r_from.get()), parse_time(self.r_to.get()),
                        {v: k for k, v in SEVERITY_NAMES.items()}[self.r_sev.get()], self.r_en.get())
        except ValueError:
            messagebox.showerror("Invalid time", "Use 24-hour format HH:MM, e.g. 08:00")
            return
        self.db.save_rule(rule)
        self.engine.set_rule(rule)
        self._refresh_rules()
        self.status_var.set(f"Rule saved for {rule.location}")

    def delete_rule(self):
        sel = self.rule_tree.selection()
        if not sel:
            return
        loc = self.rule_tree.item(sel[0])["values"][0]
        if not messagebox.askyesno("Delete rule", f"Delete the rule for '{loc}'?"):
            return
        self.db.delete_rule(loc)
        self.engine.remove_rule(loc)
        self._refresh_rules()

    def _refresh_rules(self):
        self.rule_tree.delete(*self.rule_tree.get_children())
        for r in self.db.get_rules():
            self.rule_tree.insert("", "end", values=(
                r.location, f"{r.allowed_from:%H:%M}", f"{r.allowed_to:%H:%M}",
                SEVERITY_NAMES[r.severity], "yes" if r.enabled else "no"))

    # =====================================================================
    def refresh_all(self):
        self._refresh_dashboard()
        self._refresh_alerts()
        self._refresh_history()
        self._refresh_rules()
        self._draw_maps()

    def _on_close(self):
        self.stop_video()
        self.db.close()
        self.destroy()


def run(db_path: str = "campus_security.db"):
    App(db_path).mainloop()