# -*- mode: python ; coding: utf-8 -*-
"""Reteta PyInstaller: un executabil cu interfata + unul de linie de comanda.

`blender_ops.py` si `bone_map.py` sunt incluse ca FISIERE DE DATE, nu compilate:
Blender le ruleaza ca scripturi, deci trebuie sa existe pe disc.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), os.pardir))
sys.path.insert(0, ROOT)

from mixamo2mh.blender import SCRIPT_FILES  # noqa: E402

SCRIPTS = [(os.path.join(ROOT, "mixamo2mh", name), "mixamo2mh") for name in SCRIPT_FILES]
DOCS = [(os.path.join(ROOT, "README.md"), ".")]

gui_analysis = Analysis(
    [os.path.join(ROOT, "build", "entry_gui.py")],
    pathex=[ROOT],
    datas=SCRIPTS + DOCS,
    hiddenimports=["mixamo2mh.gui", "mixamo2mh.cli"],
    excludes=["numpy", "bpy", "pytest", "PIL", "matplotlib"],
    noarchive=False,
)

cli_analysis = Analysis(
    [os.path.join(ROOT, "build", "entry_cli.py")],
    pathex=[ROOT],
    datas=SCRIPTS + DOCS,
    hiddenimports=["mixamo2mh.cli"],
    excludes=["numpy", "bpy", "pytest", "PIL", "matplotlib", "tkinter"],
    noarchive=False,
)

gui_exe = EXE(
    PYZ(gui_analysis.pure, gui_analysis.zipped_data),
    gui_analysis.scripts,
    gui_analysis.binaries,
    gui_analysis.datas,
    [],
    name="Mixamo2MetaHuman",
    console=False,          # fara fereastra neagra de consola
    upx=False,
    icon=os.environ.get("M2M_ICON") or None,
)

cli_exe = EXE(
    PYZ(cli_analysis.pure, cli_analysis.zipped_data),
    cli_analysis.scripts,
    cli_analysis.binaries,
    cli_analysis.datas,
    [],
    name="mixamo2mh-cli",
    console=True,
    upx=False,
)
