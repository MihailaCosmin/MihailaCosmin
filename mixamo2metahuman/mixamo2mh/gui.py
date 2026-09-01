"""Interfata grafica (tkinter, fara dependinte externe)."""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
from typing import List

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import unreal_script
from .blender import BlenderNotFound, blender_version, collect_fbx, find_blender, run_conversion
from .settings import (
    MODE_ANIMATION,
    MODE_CHARACTER,
    ROOT_EXTRACT,
    ROOT_INPLACE,
    ROOT_KEEP,
    ConversionSettings,
)

APP_TITLE = "Mixamo -> MetaHuman (UE5)"
PAD = 8


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(760, 620)

        self.messages: "queue.Queue[tuple]" = queue.Queue()
        self.worker: threading.Thread | None = None
        self.sources: List[str] = []

        self.var_blender = tk.StringVar()
        self.var_output = tk.StringVar()
        self.var_mode = tk.StringVar(value=MODE_ANIMATION)
        self.var_root = tk.StringVar(value=ROOT_EXTRACT)
        self.var_rename = tk.BooleanVar(value=True)
        self.var_add_root = tk.BooleanVar(value=True)
        self.var_auto_orient = tk.BooleanVar(value=True)
        self.var_overwrite = tk.BooleanVar(value=True)
        self.var_ue_script = tk.BooleanVar(value=True)
        self.var_scale = tk.StringVar(value="1.0")
        self.var_suffix = tk.StringVar(value="_UE5")
        self.var_status = tk.StringVar(value="Gata.")

        self._build()
        self._detect_blender(quiet=True)
        self.after(100, self._drain)

    # ----------------------------------------------------------------- UI --
    def _build(self) -> None:
        root = ttk.Frame(self, padding=PAD)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        root.rowconfigure(4, weight=1)

        self._build_blender(root).grid(row=0, column=0, sticky="ew", pady=(0, PAD))
        self._build_files(root).grid(row=1, column=0, sticky="nsew", pady=(0, PAD))
        self._build_options(root).grid(row=2, column=0, sticky="ew", pady=(0, PAD))
        self._build_actions(root).grid(row=3, column=0, sticky="ew", pady=(0, PAD))
        self._build_log(root).grid(row=4, column=0, sticky="nsew")

        ttk.Label(root, textvariable=self.var_status, anchor="w").grid(
            row=5, column=0, sticky="ew", pady=(PAD, 0)
        )

    def _build_blender(self, parent: ttk.Frame) -> ttk.Widget:
        box = ttk.LabelFrame(parent, text="Blender", padding=PAD)
        box.columnconfigure(0, weight=1)
        ttk.Entry(box, textvariable=self.var_blender).grid(row=0, column=0, sticky="ew")
        ttk.Button(box, text="Alege...", command=self._pick_blender).grid(
            row=0, column=1, padx=(PAD, 0)
        )
        ttk.Button(box, text="Detecteaza", command=self._detect_blender).grid(
            row=0, column=2, padx=(4, 0)
        )
        ttk.Label(
            box,
            text="Conversia foloseste Blender in fundal (3.x sau 4.x, gratuit de pe blender.org).",
            foreground="#666",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        return box

    def _build_files(self, parent: ttk.Frame) -> ttk.Widget:
        box = ttk.LabelFrame(parent, text="Fisiere FBX de la Mixamo", padding=PAD)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(box, selectmode="extended", activestyle="none")
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scroll.set)

        buttons = ttk.Frame(box)
        buttons.grid(row=0, column=2, sticky="ns", padx=(PAD, 0))
        for text, command in (
            ("Adauga fisiere", self._add_files),
            ("Adauga folder", self._add_folder),
            ("Sterge selectia", self._remove_selected),
            ("Goleste lista", self._clear_files),
        ):
            ttk.Button(buttons, text=text, command=command, width=16).pack(
                fill="x", pady=2
            )
        return box

    def _build_options(self, parent: ttk.Frame) -> ttk.Widget:
        box = ttk.LabelFrame(parent, text="Optiuni", padding=PAD)
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Folder iesire:").grid(row=0, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.var_output).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )
        ttk.Button(box, text="Alege...", command=self._pick_output).grid(
            row=0, column=2, padx=(4, 0)
        )

        modes = ttk.Frame(box)
        modes.grid(row=1, column=0, columnspan=3, sticky="w", pady=(PAD, 0))
        ttk.Label(modes, text="Export:").pack(side="left")
        ttk.Radiobutton(modes, text="Doar animatie", value=MODE_ANIMATION,
                        variable=self.var_mode).pack(side="left", padx=(4, 0))
        ttk.Radiobutton(modes, text="Personaj (mesh + schelet)", value=MODE_CHARACTER,
                        variable=self.var_mode).pack(side="left", padx=(4, 0))

        roots = ttk.Frame(box)
        roots.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(roots, text="Root motion:").pack(side="left")
        for text, value in (
            ("Extrage pe osul root", ROOT_EXTRACT),
            ("In place", ROOT_INPLACE),
            ("Lasa asa", ROOT_KEEP),
        ):
            ttk.Radiobutton(roots, text=text, value=value,
                            variable=self.var_root).pack(side="left", padx=(4, 0))

        flags = ttk.Frame(box)
        flags.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Checkbutton(flags, text="Redenumeste oasele in conventia UE5",
                        variable=self.var_rename).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(flags, text="Adauga osul 'root'",
                        variable=self.var_add_root).grid(row=0, column=1, sticky="w", padx=(PAD, 0))
        ttk.Checkbutton(flags, text="Orientare automata a oaselor",
                        variable=self.var_auto_orient).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(flags, text="Suprascrie fisierele existente",
                        variable=self.var_overwrite).grid(row=1, column=1, sticky="w", padx=(PAD, 0))
        ttk.Checkbutton(flags, text="Genereaza scriptul de import pentru UE5",
                        variable=self.var_ue_script).grid(row=2, column=0, columnspan=2, sticky="w")

        extra = ttk.Frame(box)
        extra.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(extra, text="Scala:").pack(side="left")
        ttk.Entry(extra, textvariable=self.var_scale, width=8).pack(side="left", padx=(4, PAD))
        ttk.Label(extra, text="Sufix fisiere:").pack(side="left")
        ttk.Entry(extra, textvariable=self.var_suffix, width=12).pack(side="left", padx=(4, 0))
        return box

    def _build_actions(self, parent: ttk.Frame) -> ttk.Widget:
        box = ttk.Frame(parent)
        box.columnconfigure(1, weight=1)
        self.button_convert = ttk.Button(box, text="Converteste", command=self._start)
        self.button_convert.grid(row=0, column=0)
        self.progress = ttk.Progressbar(box, mode="determinate")
        self.progress.grid(row=0, column=1, sticky="ew", padx=(PAD, PAD))
        ttk.Button(box, text="Deschide folderul", command=self._open_output).grid(
            row=0, column=2
        )
        return box

    def _build_log(self, parent: ttk.Frame) -> ttk.Widget:
        box = ttk.LabelFrame(parent, text="Jurnal", padding=PAD)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.log = tk.Text(box, height=10, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        return box

    # ------------------------------------------------------------ actiuni --
    def _pick_blender(self) -> None:
        path = filedialog.askopenfilename(title="Alege executabilul Blender")
        if path:
            self.var_blender.set(path)
            self._write("Blender: %s" % path)

    def _detect_blender(self, quiet: bool = False) -> None:
        try:
            path = find_blender(self.var_blender.get().strip())
        except BlenderNotFound as exc:
            if not quiet:
                messagebox.showwarning(APP_TITLE, str(exc))
            self._write("Blender negasit. Alege-l manual.")
            return
        self.var_blender.set(path)
        version = blender_version(path)
        self._write("Blender gasit: %s%s" % (path, " (%s)" % version if version else ""))

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Alege FBX-uri de la Mixamo",
            filetypes=[("Fisiere FBX", "*.fbx"), ("Toate fisierele", "*.*")],
        )
        self._add(list(paths))

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Alege un folder cu FBX-uri")
        if folder:
            self._add([folder])

    def _add(self, paths: List[str]) -> None:
        found = collect_fbx(paths)
        added = 0
        for path in found:
            if path not in self.sources:
                self.sources.append(path)
                self.listbox.insert("end", path)
                added += 1
        if not self.var_output.get() and self.sources:
            default = Path(self.sources[0]).parent / "UE5_Export"
            self.var_output.set(str(default))
        self._write("Adaugate %d fisiere (total %d)." % (added, len(self.sources)))

    def _remove_selected(self) -> None:
        for index in sorted(self.listbox.curselection(), reverse=True):
            self.listbox.delete(index)
            del self.sources[index]

    def _clear_files(self) -> None:
        self.listbox.delete(0, "end")
        self.sources.clear()

    def _pick_output(self) -> None:
        folder = filedialog.askdirectory(title="Alege folderul de iesire")
        if folder:
            self.var_output.set(folder)

    def _open_output(self) -> None:
        folder = self.var_output.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showinfo(APP_TITLE, "Folderul de iesire nu exista inca.")
            return
        _open_in_file_manager(folder)

    # ---------------------------------------------------------- conversie --
    def _collect_settings(self) -> ConversionSettings | None:
        try:
            scale = float(self.var_scale.get().replace(",", "."))
        except ValueError:
            messagebox.showerror(APP_TITLE, "Scala trebuie sa fie un numar.")
            return None

        settings = ConversionSettings(
            inputs=list(self.sources),
            output_dir=self.var_output.get().strip(),
            mode=self.var_mode.get(),
            root_motion=self.var_root.get(),
            add_root_bone=self.var_add_root.get(),
            rename_bones=self.var_rename.get(),
            automatic_bone_orientation=self.var_auto_orient.get(),
            scale=scale,
            suffix=self.var_suffix.get().strip(),
            overwrite=self.var_overwrite.get(),
            blender=self.var_blender.get().strip(),
        )
        problems = settings.validate()
        if problems:
            messagebox.showerror(APP_TITLE, "\n".join(problems[:8]))
            return None
        return settings

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        settings = self._collect_settings()
        if settings is None:
            return

        self.button_convert.state(["disabled"])
        self.progress.configure(maximum=len(settings.inputs), value=0)
        self.var_status.set("Conversie in curs...")
        self._write("--- Start (%d fisiere) ---" % len(settings.inputs))

        self.worker = threading.Thread(
            target=self._work, args=(settings, self.var_ue_script.get()), daemon=True
        )
        self.worker.start()

    def _work(self, settings: ConversionSettings, want_ue_script: bool) -> None:
        """Ruleaza in thread separat; comunica doar prin coada de mesaje."""
        try:
            results = run_conversion(settings, log=lambda m: self.messages.put(("log", m)))
            done = [r for r in results if r.ok]

            if want_ue_script and done:
                target = Path(settings.output_dir) / "unreal_import.py"
                unreal_script.write(
                    target,
                    [r.output for r in done],
                    import_as_animation=(settings.mode == MODE_ANIMATION),
                )
                self.messages.put(("log", "Script pentru UE5: %s" % target))

            self.messages.put(("done", (len(done), len(results))))
        except BlenderNotFound as exc:
            self.messages.put(("error", str(exc)))
        except Exception as exc:
            self.messages.put(("log", traceback.format_exc()))
            self.messages.put(("error", "%s: %s" % (type(exc).__name__, exc)))

    def _drain(self) -> None:
        """Muta mesajele din thread-ul de lucru in interfata."""
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self._write(payload)
                if payload.startswith("["):
                    self.progress.step(1)
            elif kind == "done":
                done, total = payload
                self._finish("Gata: %d din %d fisiere convertite." % (done, total))
                if done < total:
                    messagebox.showwarning(
                        APP_TITLE,
                        "%d fisiere nu au putut fi convertite. Detalii in jurnal."
                        % (total - done),
                    )
            elif kind == "error":
                self._finish("Eroare.")
                messagebox.showerror(APP_TITLE, payload)

        self.after(100, self._drain)

    def _finish(self, status: str) -> None:
        self.progress.configure(value=self.progress["maximum"])
        self.button_convert.state(["!disabled"])
        self.var_status.set(status)
        self._write(status)

    def _write(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def _open_in_file_manager(folder: str) -> None:
    import subprocess
    import sys

    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", folder])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])
    else:
        subprocess.Popen(["xdg-open", folder])


def main() -> int:
    try:
        app = App()
    except tk.TclError as exc:
        print("Nu pot deschide interfata grafica: %s" % exc)
        print("Foloseste varianta din linia de comanda: python -m mixamo2mh --help")
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
