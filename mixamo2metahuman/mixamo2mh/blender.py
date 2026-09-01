"""Gasirea si rularea Blender-ului in mod background.

Conversia efectiva (import FBX, redenumire oase, root motion, export) se face
in Blender pentru ca acolo exista un importer/exporter FBX matur. Aplicatia
doar il conduce si citeste ce raporteaza scriptul.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from .settings import ConversionSettings

SCRIPT_NAME = "blender_ops.py"

#: Locuri uzuale de instalare, verificate cand blender nu e in PATH.
_CANDIDATE_GLOBS = {
    "win32": [
        r"C:\Program Files\Blender Foundation\Blender*\blender.exe",
        r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
    ],
    "darwin": [
        "/Applications/Blender.app/Contents/MacOS/Blender",
        str(Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"),
    ],
    "linux": [
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/snap/bin/blender",
        str(Path.home() / ".local/bin/blender"),
        "/opt/blender*/blender",
    ],
}


class BlenderNotFound(RuntimeError):
    pass


def find_blender(explicit: str = "") -> str:
    """Calea executabilului Blender. Ridica BlenderNotFound daca nu il gaseste."""
    if explicit:
        if Path(explicit).is_file() and os.access(explicit, os.X_OK):
            return explicit
        raise BlenderNotFound(f"Calea data catre Blender nu e valida: {explicit}")

    env = os.environ.get("BLENDER_PATH", "")
    if env and Path(env).is_file():
        return env

    found = shutil.which("blender")
    if found:
        return found

    platform = "win32" if sys.platform.startswith("win") else (
        "darwin" if sys.platform == "darwin" else "linux"
    )
    for pattern in _CANDIDATE_GLOBS[platform]:
        if any(ch in pattern for ch in "*?"):
            root = Path(pattern).anchor or "."
            rel = str(Path(pattern).relative_to(root)) if Path(pattern).anchor else pattern
            matches = sorted(Path(root).glob(rel), reverse=True)
            if matches:
                return str(matches[0])
        elif Path(pattern).is_file():
            return pattern

    raise BlenderNotFound(
        "Nu am gasit Blender. Instaleaza-l de pe blender.org (3.x sau 4.x) si, "
        "daca nu e in PATH, indica executabilul din interfata sau prin "
        "variabila de mediu BLENDER_PATH."
    )


def blender_version(executable: str) -> str:
    """Prima linie din `blender --version`, sau '' daca nu raspunde."""
    try:
        out = subprocess.run(
            [executable, "--version"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip().splitlines()[0].strip() if out.stdout.strip() else ""


@dataclass
class FileResult:
    source: str
    output: str = ""
    ok: bool = False
    message: str = ""
    renamed_bones: int = 0
    unmapped_bones: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.unmapped_bones is None:
            self.unmapped_bones = []


def run_conversion(
    settings: ConversionSettings,
    log: Optional[Callable[[str], None]] = None,
) -> List[FileResult]:
    """Ruleaza conversia pentru toate fisierele din setari.

    Fiecare FBX e procesat intr-un proces Blender separat, ca o scena stricata
    sau un crash sa nu darame tot batch-ul.
    """
    emit = log or (lambda _msg: None)
    executable = find_blender(settings.blender)
    version = blender_version(executable)
    emit(f"Blender: {executable}" + (f" ({version})" if version else ""))

    script = Path(__file__).with_name(SCRIPT_NAME)
    if not script.is_file():
        raise FileNotFoundError(f"Lipseste scriptul de Blender: {script}")

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)

    results: List[FileResult] = []
    total = len(settings.inputs)
    for index, source in enumerate(settings.inputs, start=1):
        emit(f"[{index}/{total}] {Path(source).name}")
        results.append(_run_one(executable, script, settings, source, emit))
    return results


def _run_one(
    executable: str,
    script: Path,
    settings: ConversionSettings,
    source: str,
    emit: Callable[[str], None],
) -> FileResult:
    output = settings.output_path(source)
    result = FileResult(source=source, output=str(output))

    if output.exists() and not settings.overwrite:
        result.message = "Sarit: fisierul exista deja (overwrite dezactivat)."
        emit("    " + result.message)
        return result

    job = {
        "input": str(Path(source).resolve()),
        "output": str(output.resolve()),
        "mode": settings.mode,
        "root_motion": settings.root_motion,
        "add_root_bone": settings.add_root_bone,
        "rename_bones": settings.rename_bones,
        "keep_unmapped_bones": settings.keep_unmapped_bones,
        "automatic_bone_orientation": settings.automatic_bone_orientation,
        "scale": settings.scale,
        "rename_action": settings.rename_action,
    }

    with tempfile.TemporaryDirectory(prefix="mixamo2mh_") as tmp:
        job_file = Path(tmp) / "job.json"
        report_file = Path(tmp) / "report.json"
        job_file.write_text(json.dumps(job), encoding="utf-8")

        command = [
            executable, "--background", "--factory-startup",
            "--python-exit-code", "77",
            "--python", str(script),
            "--", "--job", str(job_file), "--report", str(report_file),
        ]
        proc = subprocess.run(command, capture_output=True, text=True, check=False)

        report = {}
        if report_file.is_file():
            try:
                report = json.loads(report_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                report = {}

    result.ok = bool(report.get("ok")) and proc.returncode == 0
    result.renamed_bones = int(report.get("renamed_bones", 0))
    result.unmapped_bones = list(report.get("unmapped_bones", []))
    result.message = report.get("message", "")

    if result.ok:
        emit(f"    OK -> {output.name} ({result.renamed_bones} oase redenumite)")
        if result.unmapped_bones:
            emit("    Oase fara corespondent UE5: " + ", ".join(result.unmapped_bones))
    else:
        if not result.message:
            result.message = _tail(proc.stderr) or _tail(proc.stdout) or (
                f"Blender a iesit cu codul {proc.returncode}."
            )
        emit(f"    EROARE: {result.message}")

    return result


def _tail(text: str, lines: int = 6) -> str:
    """Ultimele linii nevide dintr-un output, pentru mesaje de eroare scurte."""
    useful = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return " | ".join(useful[-lines:])


def collect_fbx(paths: Iterable[str], recursive: bool = True) -> List[str]:
    """Expandeaza foldere in fisiere .fbx, pastrand ordinea si fara duplicate."""
    out: List[str] = []
    seen = set()
    for raw in paths:
        path = Path(raw)
        # glob e case-sensitive pe Linux/macOS, deci filtram noi extensia:
        # Mixamo livreaza uneori ".FBX".
        found = (
            sorted(item for item in (path.rglob("*") if recursive else path.glob("*"))
                   if item.is_file())
            if path.is_dir() else [path]
        )
        for item in found:
            key = str(item.resolve())
            if key not in seen and item.suffix.lower() == ".fbx":
                seen.add(key)
                out.append(str(item))
    return out
