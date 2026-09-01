"""Interfata de linie de comanda (utila pentru batch-uri si scripturi)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import unreal_script
from .blender import BlenderNotFound, collect_fbx, run_conversion
from .settings import (
    MODE_ANIMATION,
    MODES,
    ROOT_EXTRACT,
    ROOT_MODES,
    ConversionSettings,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mixamo2mh",
        description="Converteste personaje si animatii Mixamo pentru UE5 / MetaHuman.",
    )
    parser.add_argument("inputs", nargs="+", help="fisiere .fbx sau foldere cu .fbx")
    parser.add_argument("-o", "--output", required=True, help="folderul de iesire")
    parser.add_argument("--mode", choices=MODES, default=MODE_ANIMATION,
                        help="animation = doar schelet + animatie, character = si mesh")
    parser.add_argument("--root-motion", choices=ROOT_MODES, default=ROOT_EXTRACT,
                        help="keep = nimic, extract = pe osul root, inplace = pe loc")
    parser.add_argument("--no-root-bone", action="store_true",
                        help="nu adauga osul 'root'")
    parser.add_argument("--no-rename", action="store_true",
                        help="pastreaza numele de oase Mixamo")
    parser.add_argument("--scale", type=float, default=1.0, help="scala la export")
    parser.add_argument("--suffix", default="_UE5", help="sufix pentru fisierele iesite")
    parser.add_argument("--blender", default="", help="calea catre executabilul Blender")
    parser.add_argument("--no-overwrite", action="store_true",
                        help="sari peste fisierele care exista deja")
    parser.add_argument("--unreal-script", nargs="?", const="auto", default=None,
                        metavar="CALE",
                        help="scrie si scriptul de import pentru UE5")
    parser.add_argument("--ue-content-path", default="/Game/Mixamo",
                        help="folderul din proiectul UE5 (implicit /Game/Mixamo)")
    parser.add_argument("--ue-skeleton", default="",
                        help="calea scheletului UE5 pe care se importa animatiile")
    return parser


def settings_from_args(args: argparse.Namespace) -> ConversionSettings:
    return ConversionSettings(
        inputs=collect_fbx(args.inputs),
        output_dir=args.output,
        mode=args.mode,
        root_motion=args.root_motion,
        add_root_bone=not args.no_root_bone,
        rename_bones=not args.no_rename,
        scale=args.scale,
        suffix=args.suffix,
        blender=args.blender,
        overwrite=not args.no_overwrite,
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    settings = settings_from_args(args)

    problems = settings.validate()
    if problems:
        for problem in problems:
            print("Eroare: " + problem, file=sys.stderr)
        return 2

    try:
        results = run_conversion(settings, log=print)
    except BlenderNotFound as exc:
        print("Eroare: " + str(exc), file=sys.stderr)
        return 3

    ok = [r for r in results if r.ok]
    print("\nGata: %d din %d fisiere convertite." % (len(ok), len(results)))
    for result in results:
        if not result.ok:
            print("  esuat: %s (%s)" % (Path(result.source).name, result.message))

    if args.unreal_script and ok:
        target = (
            Path(settings.output_dir) / "unreal_import.py"
            if args.unreal_script == "auto" else Path(args.unreal_script)
        )
        unreal_script.write(
            target,
            [r.output for r in ok],
            destination=args.ue_content_path,
            import_as_animation=(settings.mode == MODE_ANIMATION),
            skeleton_path=args.ue_skeleton,
        )
        print("Script pentru UE5: %s" % target)

    return 0 if len(ok) == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
