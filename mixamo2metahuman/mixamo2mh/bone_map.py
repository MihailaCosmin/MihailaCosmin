"""Maparea numelor de oase Mixamo -> UE5 (Mannequin / MetaHuman).

Scheletul MetaHuman foloseste aceeasi conventie de nume ca UE5 Mannequin
(pelvis, spine_01, thigh_l, ...). Daca oasele din FBX-ul Mixamo poarta aceste
nume, IK Retargeter-ul din Unreal potriveste automat lanturile (chains),
ceea ce scurteaza drastic setup-ul manual.

Modulul nu depinde de bpy, ca sa poata fi importat si testat in afara Blender.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

# "mixamorig:Hips", "mixamorig1:Hips", "mixamorigHips" -> "Hips"
_PREFIX_RE = re.compile(r"^mixamorig\d*[:_]?", re.IGNORECASE)

#: Coloana: Mixamo are Spine/Spine1/Spine2. UE5 are spine_01..spine_05, dar
#: retargeting-ul functioneaza si cand lantul sursa are mai putine oase.
SPINE: Dict[str, str] = {
    "Hips": "pelvis",
    "Spine": "spine_01",
    "Spine1": "spine_02",
    "Spine2": "spine_03",
    "Neck": "neck_01",
    "Neck1": "neck_02",
    "Head": "head",
}

_ARM = {
    "Shoulder": "clavicle",
    "Arm": "upperarm",
    "ForeArm": "lowerarm",
    "Hand": "hand",
}

_LEG = {
    "UpLeg": "thigh",
    "Leg": "calf",
    "Foot": "foot",
    "ToeBase": "ball",
}

_FINGERS = {
    "Thumb": "thumb",
    "Index": "index",
    "Middle": "middle",
    "Ring": "ring",
    "Pinky": "pinky",
}

_SIDES = (("Left", "l"), ("Right", "r"))


def _build_limbs() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for side, suffix in _SIDES:
        for mixamo, ue in _ARM.items():
            out[f"{side}{mixamo}"] = f"{ue}_{suffix}"
        for mixamo, ue in _LEG.items():
            out[f"{side}{mixamo}"] = f"{ue}_{suffix}"
        for mixamo, ue in _FINGERS.items():
            # Mixamo numeroteaza 1..3 falangele + 4 = varful (leaf bone).
            # UE5/MetaHuman are doar 01..03, deci varful ramane nemapat.
            for i in (1, 2, 3):
                out[f"{side}Hand{mixamo}{i}"] = f"{ue}_0{i}_{suffix}"
    return out


#: Mapare completa, fara prefixul "mixamorig:".
MIXAMO_TO_UE5: Dict[str, str] = {**SPINE, **_build_limbs()}

#: Numele osului radacina asteptat de Unreal pentru root motion.
ROOT_BONE = "root"

#: Osul din varful ierarhiei animate (copilul lui root).
PELVIS_BONE = "pelvis"


def strip_prefix(name: str) -> str:
    """Elimina prefixul 'mixamorig:' (sau variantele lui) dintr-un nume de os."""
    return _PREFIX_RE.sub("", name)


def ue_name(name: str) -> str | None:
    """Numele UE5 pentru un os Mixamo, sau None daca nu exista corespondent."""
    return MIXAMO_TO_UE5.get(strip_prefix(name))


def build_rename_map(
    bone_names: Iterable[str], keep_unmapped: bool = True
) -> Tuple[Dict[str, str], List[str]]:
    """Construieste {nume_vechi: nume_nou} pentru o lista de oase.

    Returneaza si lista oaselor fara corespondent UE5 (varfuri de degete,
    oase de par/fusta adaugate de utilizator etc.). Cand ``keep_unmapped``
    e True, acelea isi pastreaza numele curatat de prefix; altfel raman
    exact cum sunt.

    Numele care ar intra in coliziune cu unul deja alocat sunt sarite, ca sa
    nu stricam ierarhia scheletului.
    """
    names = list(bone_names)
    rename: Dict[str, str] = {}
    unmapped: List[str] = []
    targets: Dict[str, str] = {}
    taken = set()

    # Pas 1: aflam ce nume vrea fiecare os si rezervam numele oaselor care
    # raman neschimbate - altfel un os care se cheama deja "pelvis" ar putea
    # fi luat de "mixamorig:Hips", iar Blender ar produce un "pelvis.001".
    for original in names:
        mapped = ue_name(original)
        if mapped is None:
            unmapped.append(original)
            mapped = strip_prefix(original) if keep_unmapped else original
        targets[original] = mapped
        if not mapped or mapped == original:
            taken.add(original)

    # Pas 2: dam numele noi, sarind peste cele deja ocupate.
    for original in names:
        mapped = targets[original]
        if not mapped or mapped == original or mapped in taken:
            continue
        taken.add(mapped)
        rename[original] = mapped

    return rename, unmapped
