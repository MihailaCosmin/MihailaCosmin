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

#: Pe Windows, un executabil fara consola ar deschide cate o fereastra neagra
#: pentru fiecare Blender pornit. Steagul o suprima; pe restul e 0 (ignorat).
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

#: Fisierele care trebuie sa ajunga pe disc langa executabil: Blender le
#: ruleaza ca scripturi, deci nu pot fi compilate in interiorul unui .exe.
SCRIPT_FILES = (SCRIPT_NAME, "bone_map.py")

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


def script_path():
    """Calea catre `blender_ops.py`, si cand aplicatia ruleaza ca executabil.

    PyInstaller dezarhiveaza fisierele de date intr-un folder temporar
    (`sys._MEIPASS`), asa ca il verificam si pe acela, plus folderul de langa
    executabil pentru build-urile "onedir".
    """
    candidates = [Path(__file__).with_name(SCRIPT_NAME)]
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        candidates.append(Path(bundle) / "mixamo2mh" / SCRIPT_NAME)
        candidates.append(Path(bundle) / SCRIPT_NAME)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "mixamo2mh" / SCRIPT_NAME)
        candidates.append(exe_dir / SCRIPT_NAME)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Lipseste scriptul de Blender (%s). Cautat in: %s"
        % (SCRIPT_NAME, ", ".join(str(c) for c in candidates))
    )


#: Numele executabilului, pentru un Blender portabil pus langa aplicatie.
_PORTABLE_NAMES = (
    "blender.exe",
    "blender",
    os.path.join("Contents", "MacOS", "Blender"),   # Blender.app pe macOS
)

#: Subfoldere in care il cautam.
_PORTABLE_DIRS = (".", "Blender", "blender", "Blender.app")

#: Pe Windows "se poate executa" inseamna extensia potrivita: acolo nu exista
#: bit de executie, iar os.access(..., X_OK) raspunde True pentru orice fisier.
_WINDOWS_SUFFIXES = (".exe", ".bat", ".cmd", ".com")


def is_runnable(path, windows: Optional[bool] = None) -> bool:
    """Spune daca fisierul poate fi pornit ca program pe sistemul curent.

    ``windows`` exista ca sa putem testa ambele comportamente pe orice sistem.
    """
    if windows is None:
        windows = os.name == "nt"
    candidate = Path(path)
    if not candidate.is_file():
        return False
    if windows:
        return candidate.suffix.lower() in _WINDOWS_SUFFIXES
    return os.access(str(candidate), os.X_OK)


def app_dirs() -> List[Path]:
    """Folderele "de langa aplicatie", si cand ruleaza ca executabil."""
    roots = [Path(__file__).resolve().parents[1]]
    if getattr(sys, "frozen", False):
        roots.insert(0, Path(sys.executable).resolve().parent)
    return roots


def find_portable(
    roots: Optional[List[Path]] = None, windows: Optional[bool] = None
) -> str:
    """Cauta un Blender portabil adus langa aplicatie (folderul e autonom)."""
    for root in roots if roots is not None else app_dirs():
        for folder in _PORTABLE_DIRS:
            for name in _PORTABLE_NAMES:
                candidate = Path(root) / folder / name
                if is_runnable(candidate, windows):
                    return str(candidate)
    return ""


def find_blender(explicit: str = "", roots: Optional[List[Path]] = None) -> str:
    """Calea executabilului Blender. Ridica BlenderNotFound daca nu il gaseste.

    Ordinea: calea data explicit, variabila BLENDER_PATH, un Blender portabil
    de langa aplicatie, PATH-ul sistemului, apoi locurile uzuale de instalare.
    """
    if explicit:
        chosen = Path(explicit)
        if is_runnable(chosen):
            return explicit
        if chosen.is_dir():
            # din dialog se alege deseori folderul: "Blender.app" pe macOS sau
            # folderul unui Blender portabil pe Windows
            inside = find_portable([chosen])
            if inside:
                return inside
            raise BlenderNotFound(
                f"In folderul ales nu e niciun Blender: {explicit}"
            )
        raise BlenderNotFound(f"Calea data catre Blender nu e valida: {explicit}")

    env = os.environ.get("BLENDER_PATH", "")
    if env and Path(env).is_file():
        return env

    portable = find_portable(roots)

    if portable:
        return portable

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
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip().splitlines()[0].strip() if out.stdout.strip() else ""


@dataclass
class FileResult:
    source: str
    output: str = ""
    ok: bool = False
    skipped: bool = False
    message: str = ""
    renamed_bones: int = 0
    unmapped_bones: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.unmapped_bones is None:
            self.unmapped_bones = []

    @property
    def failed(self) -> bool:
        """Doar esecurile reale; un fisier sarit deliberat nu e o eroare."""
        return not self.ok and not self.skipped

    @property
    def usable(self) -> bool:
        """Exista un FBX bun pe disc pentru aceasta intrare."""
        return self.ok or self.skipped


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

    script = script_path()

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)

    planned = settings.output_paths()
    results: List[FileResult] = []
    total = len(settings.inputs)
    for index, source in enumerate(settings.inputs, start=1):
        emit(f"[{index}/{total}] {Path(source).name}")
        results.append(
            _run_one(executable, script, settings, source, planned[source], emit)
        )
    return results


def _run_one(
    executable: str,
    script: Path,
    settings: ConversionSettings,
    source: str,
    output: Path,
    emit: Callable[[str], None],
) -> FileResult:
    result = FileResult(source=source, output=str(output))

    if output.exists() and not settings.overwrite:
        result.skipped = True
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
        proc = subprocess.run(command, capture_output=True, text=True, check=False,
                              creationflags=NO_WINDOW)

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
