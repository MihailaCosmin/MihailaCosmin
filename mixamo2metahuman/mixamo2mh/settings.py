"""Setarile unei conversii, partajate intre GUI, CLI si scriptul de Blender."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List

#: Ce exportam: personaj (mesh + schelet) sau doar animatia (armatura).
MODE_CHARACTER = "character"
MODE_ANIMATION = "animation"
MODES = (MODE_CHARACTER, MODE_ANIMATION)

#: Ce facem cu deplasarea din animatie.
ROOT_KEEP = "keep"        # lasam totul pe pelvis (asa vine de la Mixamo)
ROOT_EXTRACT = "extract"  # mutam deplasarea orizontala pe osul "root"
ROOT_INPLACE = "inplace"  # animatie pe loc (in-place), utila pentru blendspace
ROOT_MODES = (ROOT_KEEP, ROOT_EXTRACT, ROOT_INPLACE)


@dataclass
class ConversionSettings:
    """Optiunile unei rulari. Serializabile in JSON pentru procesul de Blender."""

    inputs: List[str] = field(default_factory=list)
    output_dir: str = ""
    mode: str = MODE_ANIMATION
    root_motion: str = ROOT_EXTRACT
    add_root_bone: bool = True
    rename_bones: bool = True
    keep_unmapped_bones: bool = True
    automatic_bone_orientation: bool = True
    scale: float = 1.0
    suffix: str = "_UE5"
    rename_action: bool = True
    overwrite: bool = True
    blender: str = ""

    def validate(self) -> List[str]:
        """Returneaza lista de probleme (goala = setari valide)."""
        problems: List[str] = []

        if not self.inputs:
            problems.append("Nu ai ales niciun fisier FBX.")
        for item in self.inputs:
            if not Path(item).exists():
                problems.append(f"Fisierul nu exista: {item}")
            elif Path(item).suffix.lower() != ".fbx":
                problems.append(f"Nu e un FBX: {item}")

        if not self.output_dir:
            problems.append("Nu ai ales folderul de iesire.")

        if self.mode not in MODES:
            problems.append(f"Mod necunoscut: {self.mode}")
        if self.root_motion not in ROOT_MODES:
            problems.append(f"Optiune root motion necunoscuta: {self.root_motion}")
        if self.root_motion == ROOT_EXTRACT and not self.add_root_bone:
            problems.append(
                "Extragerea root motion cere si adaugarea osului 'root'."
            )
        if self.scale <= 0:
            problems.append("Scala trebuie sa fie un numar pozitiv.")

        return problems

    def output_path(self, source: str) -> Path:
        """Calea fisierului rezultat pentru un FBX sursa."""
        return Path(self.output_dir) / f"{Path(source).stem}{self.suffix}.fbx"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversionSettings":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def load(cls, path: str | Path) -> "ConversionSettings":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")
