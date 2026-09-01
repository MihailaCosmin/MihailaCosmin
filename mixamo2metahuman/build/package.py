#!/usr/bin/env python3
"""Construieste executabilele si asambleaza folderul gata de copiat.

    python build/package.py                      # construieste in dist/
    python build/package.py --dest D:\\Proiecte   # si copiaza acolo

Executabilul rezultat e pentru sistemul pe care rulezi scriptul: ca sa obtii
un .exe de Windows, ruleaza-l pe Windows (PyInstaller nu face cross-compile).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
SPEC = BUILD / "Mixamo2MetaHuman.spec"
FOLDER_NAME = "Mixamo2MetaHuman"
WINDOWS = os.name == "nt"
EXE = ".exe" if WINDOWS else ""

GUI_EXE = "Mixamo2MetaHuman" + EXE
CLI_EXE = "mixamo2mh-cli" + EXE

README_TXT = """\
Mixamo -> MetaHuman (UE5)
=========================

Ce e in folder
--------------
  {gui}     - aplicatia cu interfata (dublu-click)
  {cli}     - aceleasi optiuni, din linia de comanda
  README.md                  - manualul complet, cu pasii din Unreal
  Exemple/                   - model de script de import pentru UE5

Inainte de prima rulare
-----------------------
Instaleaza Blender (gratuit, de pe blender.org, versiunea 3.x, 4.x sau 5.x).
Aplicatia il foloseste in fundal ca sa citeasca si sa scrie FBX. Il gaseste
singur daca e instalat normal; altfel ii dai calea din butonul "Alege...".

Nu ai nevoie de Python instalat - e deja inclus in executabil.

Vrei folderul complet portabil (de pus pe un stick sau pe alt calculator)?
Descarca "Blender Portable" (arhiva .zip de pe blender.org), dezarhiveaza-o
in acest folder si redenumeste folderul rezultat in "Blender". Aplicatia il
foloseste automat, fara nicio setare:

    Mixamo2MetaHuman\
        Mixamo2MetaHuman.exe
        Blender\blender.exe        <- gasit automat

Pornire rapida
--------------
1. Descarci de pe Mixamo personajul (FBX Binary, T-pose) si animatiile
   (FBX Binary, Without Skin, 30 FPS, Keyframe Reduction: none).
2. Deschizi {gui}.
3. Personajul: adaugi FBX-ul, alegi "Personaj (mesh + schelet)" si
   "Root motion: Lasa asa", apesi Converteste.
4. Animatiile: adaugi fisierele sau tot folderul, alegi "Doar animatie" si
   "Root motion: Extrage pe osul root", apesi Converteste.
5. Importi rezultatele in Unreal Engine 5 si faci retargetul pe MetaHuman.
   Pasii exacti sunt in README.md, sectiunea "Fluxul complet".

Ce face conversia
-----------------
- redenumeste oasele in conventia UE5 / MetaHuman (pelvis, thigh_l, hand_r...),
  ca IK Retargeter-ul din Unreal sa mapeze lanturile automat
- adauga osul "root" si muta deplasarea pe el (root motion)
- exporta FBX cu setarile pe care le asteapta Unreal

Daca ceva nu merge
------------------
Jurnalul din partea de jos a ferestrei spune exact ce fisier a esuat si de ce.
Tabelul cu probleme uzuale e la finalul fisierului README.md.
"""


def run_pyinstaller(clean: bool) -> Path:
    """Ruleaza PyInstaller si returneaza folderul cu executabilele."""
    dist = BUILD / "_dist"
    work = BUILD / "_work"
    command = [
        sys.executable, "-m", "PyInstaller", str(SPEC),
        "--distpath", str(dist), "--workpath", str(work), "--noconfirm",
    ]
    if clean:
        command.append("--clean")

    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=str(ROOT))
    if result.returncode != 0:
        raise SystemExit(
            "PyInstaller a esuat. Verifica daca e instalat: "
            "pip install pyinstaller"
        )
    return dist


def assemble(dist: Path) -> Path:
    """Aduna executabilele si documentatia intr-un singur folder."""
    target = ROOT / "dist" / FOLDER_NAME
    if target.exists():
        shutil.rmtree(target)
    (target / "Exemple").mkdir(parents=True)

    missing = []
    for name in (GUI_EXE, CLI_EXE):
        built = dist / name
        if built.is_file():
            shutil.copy2(built, target / name)
            os.chmod(target / name, 0o755)
        else:
            missing.append(name)
    if missing:
        raise SystemExit("PyInstaller nu a produs: " + ", ".join(missing))

    shutil.copy2(ROOT / "README.md", target / "README.md")
    (target / "Citeste-ma.txt").write_text(
        README_TXT.format(gui=GUI_EXE, cli=CLI_EXE), encoding="utf-8"
    )

    sys.path.insert(0, str(ROOT))
    from mixamo2mh import unreal_script

    unreal_script.write(
        target / "Exemple" / "unreal_import_exemplu.py",
        [str(Path("C:/Proiecte/UE5_Export/Walking_UE5.fbx"))],
        destination="/Game/Mixamo",
        import_as_animation=True,
    )
    return target


def copy_to(target: Path, dest: str) -> Path:
    """Copiaza folderul pe destinatie (fuzioneaza, nu sterge nimic)."""
    destination = Path(dest).expanduser()
    if destination.name.lower() != FOLDER_NAME.lower():
        destination = destination / FOLDER_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(target, destination, dirs_exist_ok=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", default="",
                        help=r"unde se copiaza folderul final (ex: D:\Proiecte)")
    parser.add_argument("--clean", action="store_true",
                        help="sterge cache-ul PyInstaller inainte de build")
    parser.add_argument("--skip-build", action="store_true",
                        help="doar reasambleaza folderul, fara sa reconstruiasca")
    args = parser.parse_args()

    dist = BUILD / "_dist" if args.skip_build else run_pyinstaller(args.clean)
    target = assemble(dist)
    print("\nFolder gata: %s" % target)
    for item in sorted(target.rglob("*")):
        if item.is_file():
            print("  %-40s %8.1f KB" % (item.relative_to(target), item.stat().st_size / 1024))

    if args.dest:
        final = copy_to(target, args.dest)
        print("\nCopiat pe: %s" % final)
    else:
        print("\nCopiaza folderul unde vrei, sau ruleaza cu --dest CALE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
