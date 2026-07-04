#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Selly Time Tracker — monitorizeaza automat orele lucrate la proiectul "selly".

Urmareste fereastra activa din Windows si contorizeaza timpul petrecut in
Ableton Live, Unreal Engine, Blender si DaVinci Resolve. Pentru Ableton,
timpul e considerat "selly" doar daca titlul ferestrei (numele set-ului
deschis) contine unul din cuvintele-cheie din config.json — altfel e trecut
separat la "altele" (alte piese / mixaje).

Comenzi:
    python selly_tracker.py                  -> porneste urmarirea (ruleaza continuu)
    python selly_tracker.py report           -> raport pe saptamana curenta
    python selly_tracker.py report azi
    python selly_tracker.py report saptamana
    python selly_tracker.py report luna
    python selly_tracker.py report tot
    python selly_tracker.py report 2026-07-01 2026-07-04
    python selly_tracker.py report ... --csv raport.csv
    python selly_tracker.py status           -> verifica daca trackerul ruleaza + totalul de azi

Nu are nevoie de niciun pachet extern — doar Python 3.9+ standard pe Windows.
"""

import csv
import ctypes
import ctypes.wintypes as wintypes
import datetime as dt
import json
import os
import signal
import sqlite3
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DB_PATH = os.path.join(BASE_DIR, "selly_tracker.db")
PID_PATH = os.path.join(BASE_DIR, "tracker.pid")

DEFAULT_CONFIG = {
    "project_name": "selly",
    "keywords": ["selly"],
    "poll_seconds": 2,
    "idle_seconds": 180,
    "apps": [
        {
            "name": "Ableton Live",
            "exe_contains": ["ableton"],
            "match": "title",
        },
        {
            "name": "Unreal Engine",
            "exe_contains": ["unrealeditor", "ue4editor", "ue5editor"],
            "match": "always",
        },
        {
            "name": "Blender",
            "exe_contains": ["blender"],
            "match": "always",
        },
        {
            "name": "DaVinci Resolve",
            "exe_contains": ["resolve"],
            "match": "always",
        },
    ],
}


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for key, value in DEFAULT_CONFIG.items():
        cfg.setdefault(key, value)
    return cfg


# ----------------------------------------------------------------------------
# Windows API: fereastra activa + timp de inactivitate
# ----------------------------------------------------------------------------

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    def get_foreground_info():
        """Returneaza (nume_exe_lowercase, titlu_fereastra) sau (None, None)."""
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, None

        length = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        title = title_buf.value

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None, title

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return None, title
        try:
            size = wintypes.DWORD(4096)
            path_buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, path_buf, ctypes.byref(size)):
                exe = os.path.basename(path_buf.value).lower()
                return exe, title
        finally:
            kernel32.CloseHandle(handle)
        return None, title

    def get_idle_seconds():
        """Secunde de la ultima miscare de mouse / apasare de tasta."""
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        millis = kernel32.GetTickCount() - info.dwTime
        return millis / 1000.0
else:
    # Pe alte sisteme (doar pentru teste) nu exista fereastra activa.
    def get_foreground_info():
        return None, None

    def get_idle_seconds():
        return 0.0


# ----------------------------------------------------------------------------
# Baza de date
# ----------------------------------------------------------------------------

def open_db():
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS intervals (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            app      TEXT NOT NULL,
            project  TEXT NOT NULL,   -- numele proiectului sau 'altele'
            title    TEXT,
            start_ts INTEGER NOT NULL,
            end_ts   INTEGER NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_intervals_start ON intervals(start_ts)")
    db.commit()
    return db


# ----------------------------------------------------------------------------
# Potrivirea aplicatiei si a proiectului
# ----------------------------------------------------------------------------

def classify(cfg, exe, title):
    """Returneaza (nume_aplicatie, proiect) sau (None, None) daca fereastra
    activa nu e una dintre aplicatiile urmarite."""
    if not exe:
        return None, None
    for app in cfg["apps"]:
        if any(fragment in exe for fragment in app["exe_contains"]):
            if app.get("match", "title") == "always":
                return app["name"], cfg["project_name"]
            title_lower = (title or "").lower()
            if any(kw.lower() in title_lower for kw in cfg["keywords"]):
                return app["name"], cfg["project_name"]
            return app["name"], "altele"
    return None, None


# ----------------------------------------------------------------------------
# Bucla de urmarire
# ----------------------------------------------------------------------------

class Tracker:
    """Transforma esantioanele (la fiecare poll_seconds) in intervale continue
    salvate in baza de date. Intervalul curent este actualizat periodic ca sa
    nu se piarda timp daca procesul e oprit brusc."""

    FLUSH_EVERY = 30  # secunde intre actualizarile intervalului deschis

    def __init__(self, cfg, db):
        self.cfg = cfg
        self.db = db
        self.current_id = None
        self.current_key = None      # (app, project)
        self.current_end = None
        self.last_flush = 0.0

    def sample(self, now, app, project, title):
        key = (app, project) if app else None
        gap_limit = self.cfg["poll_seconds"] * 3

        if self.current_id is not None:
            if key == self.current_key and now - self.current_end <= gap_limit:
                self.current_end = now
                if time.monotonic() - self.last_flush >= self.FLUSH_EVERY:
                    self._flush()
                return
            self.close(self.current_end)

        if key is not None:
            cur = self.db.execute(
                "INSERT INTO intervals (app, project, title, start_ts, end_ts) VALUES (?,?,?,?,?)",
                (app, project, title, int(now), int(now)),
            )
            self.db.commit()
            self.current_id = cur.lastrowid
            self.current_key = key
            self.current_end = now
            self.last_flush = time.monotonic()
            stamp = dt.datetime.fromtimestamp(now).strftime("%H:%M:%S")
            print(f"[{stamp}] ▶ {app} ({project})", flush=True)

    def _flush(self):
        self.db.execute(
            "UPDATE intervals SET end_ts=? WHERE id=?",
            (int(self.current_end), self.current_id),
        )
        self.db.commit()
        self.last_flush = time.monotonic()

    def close(self, end_ts):
        if self.current_id is None:
            return
        app, project = self.current_key
        self.current_end = end_ts
        self._flush()
        row = self.db.execute(
            "SELECT start_ts, end_ts FROM intervals WHERE id=?", (self.current_id,)
        ).fetchone()
        # Intervalele prea scurte (sub 5s, ex. alt-tab rapid) nu se pastreaza.
        if row and row[1] - row[0] < 5:
            self.db.execute("DELETE FROM intervals WHERE id=?", (self.current_id,))
            self.db.commit()
        else:
            stamp = dt.datetime.fromtimestamp(end_ts).strftime("%H:%M:%S")
            print(f"[{stamp}] ⏹ {app} ({project}) — {fmt_duration(row[1] - row[0])}", flush=True)
        self.current_id = None
        self.current_key = None


def run_tracking():
    if sys.platform != "win32":
        print("Urmarirea functioneaza doar pe Windows.")
        sys.exit(1)

    # O singura instanta: verificam PID-ul din fisier.
    if os.path.exists(PID_PATH):
        try:
            with open(PID_PATH) as f:
                old_pid = int(f.read().strip())
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, old_pid)  # QUERY_LIMITED
            if handle:
                kernel32.CloseHandle(handle)
                print(f"Trackerul ruleaza deja (PID {old_pid}). Iesire.")
                sys.exit(0)
        except (ValueError, OSError):
            pass
    with open(PID_PATH, "w") as f:
        f.write(str(os.getpid()))

    cfg = load_config()
    db = open_db()
    tracker = Tracker(cfg, db)
    poll = max(1, int(cfg["poll_seconds"]))
    idle_limit = int(cfg["idle_seconds"])

    def shutdown(*_args):
        tracker.close(time.time())
        try:
            os.remove(PID_PATH)
        except OSError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    apps = ", ".join(a["name"] for a in cfg["apps"])
    print(f"Selly Time Tracker pornit. Aplicatii urmarite: {apps}")
    print(f"Cuvinte-cheie proiect: {', '.join(cfg['keywords'])}")
    print("Apasa Ctrl+C pentru oprire.\n", flush=True)

    try:
        while True:
            now = time.time()
            idle = get_idle_seconds()
            if idle >= idle_limit:
                # Utilizator inactiv: inchidem intervalul la momentul in care
                # a inceput inactivitatea, nu la momentul curent.
                tracker.close(now - idle)
            else:
                exe, title = get_foreground_info()
                app, project = classify(cfg, exe, title)
                tracker.sample(now, app, project, title)
            time.sleep(poll)
    finally:
        tracker.close(time.time())
        try:
            os.remove(PID_PATH)
        except OSError:
            pass


# ----------------------------------------------------------------------------
# Rapoarte
# ----------------------------------------------------------------------------

def fmt_duration(seconds):
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def parse_period(args):
    """Returneaza (start_date, end_date) inclusiv, ca obiecte date."""
    today = dt.date.today()
    if not args or args[0] == "saptamana":
        start = today - dt.timedelta(days=today.weekday())
        return start, today
    word = args[0]
    if word == "azi":
        return today, today
    if word == "ieri":
        y = today - dt.timedelta(days=1)
        return y, y
    if word == "luna":
        return today.replace(day=1), today
    if word == "tot":
        return dt.date(2000, 1, 1), today
    start = dt.date.fromisoformat(word)
    end = dt.date.fromisoformat(args[1]) if len(args) > 1 else start
    return start, end


def split_by_day(start_ts, end_ts):
    """Imparte un interval [start_ts, end_ts) pe zile calendaristice locale.
    Genereaza (data, secunde)."""
    cursor = start_ts
    while cursor < end_ts:
        day = dt.date.fromtimestamp(cursor)
        next_midnight = dt.datetime.combine(
            day + dt.timedelta(days=1), dt.time.min
        ).timestamp()
        chunk_end = min(end_ts, next_midnight)
        yield day, chunk_end - cursor
        cursor = chunk_end


def collect_report(db, start_date, end_date):
    """Aduna secundele pe (zi, aplicatie, proiect)."""
    start_ts = dt.datetime.combine(start_date, dt.time.min).timestamp()
    end_ts = dt.datetime.combine(end_date + dt.timedelta(days=1), dt.time.min).timestamp()
    rows = db.execute(
        "SELECT app, project, start_ts, end_ts FROM intervals "
        "WHERE end_ts > ? AND start_ts < ? ORDER BY start_ts",
        (start_ts, end_ts),
    ).fetchall()

    totals = {}  # (day, app, project) -> secunde
    for app, project, s, e in rows:
        s, e = max(s, start_ts), min(e, end_ts)
        for day, secs in split_by_day(s, e):
            key = (day, app, project)
            totals[key] = totals.get(key, 0) + secs
    return totals


def run_report(args):
    csv_path = None
    if "--csv" in args:
        i = args.index("--csv")
        csv_path = args[i + 1] if i + 1 < len(args) else "raport.csv"
        args = args[:i] + args[i + 2:]

    try:
        start_date, end_date = parse_period(args)
    except ValueError:
        print("Perioada invalida. Exemple: report azi | saptamana | luna | tot | 2026-07-01 2026-07-04")
        sys.exit(1)

    cfg = load_config()
    project = cfg["project_name"]
    db = open_db()
    totals = collect_report(db, start_date, end_date)

    if not totals:
        print(f"Nicio activitate inregistrata intre {start_date} si {end_date}.")
        return

    per_app_project = {}
    per_app_other = {}
    per_day_project = {}
    for (day, app, proj), secs in totals.items():
        if proj == project:
            per_app_project[app] = per_app_project.get(app, 0) + secs
            per_day_project[day] = per_day_project.get(day, 0) + secs
        else:
            per_app_other[app] = per_app_other.get(app, 0) + secs

    total_project = sum(per_app_project.values())
    print(f"=== Raport proiect '{project}': {start_date} → {end_date} ===\n")
    print(f"Total proiect: {fmt_duration(total_project)}")
    for app, secs in sorted(per_app_project.items(), key=lambda kv: -kv[1]):
        print(f"  {app:<18} {fmt_duration(secs)}")

    if per_app_other:
        print("\nIn afara proiectului (alte piese / alte fisiere):")
        for app, secs in sorted(per_app_other.items(), key=lambda kv: -kv[1]):
            print(f"  {app:<18} {fmt_duration(secs)}")

    if per_day_project:
        print("\nPe zile (doar proiect):")
        for day in sorted(per_day_project):
            print(f"  {day}  {fmt_duration(per_day_project[day])}")

    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["zi", "aplicatie", "proiect", "secunde", "durata"])
            for (day, app, proj), secs in sorted(totals.items()):
                writer.writerow([day.isoformat(), app, proj, int(secs), fmt_duration(secs)])
        print(f"\nCSV salvat: {csv_path}")


def run_status():
    running = False
    if os.path.exists(PID_PATH):
        try:
            with open(PID_PATH) as f:
                pid = int(f.read().strip())
            if sys.platform == "win32":
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    running = True
        except (ValueError, OSError):
            pass
    print("Tracker: " + ("RULEAZA ✔" if running else "OPRIT ✘"))
    run_report(["azi"])


# ----------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args or args[0] == "track":
        run_tracking()
    elif args[0] == "report":
        run_report(args[1:])
    elif args[0] == "status":
        run_status()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
