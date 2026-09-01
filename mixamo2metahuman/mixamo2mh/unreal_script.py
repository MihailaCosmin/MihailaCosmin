"""Genereaza scriptul Python care se ruleaza in Unreal Engine 5.

Partea de Blender scoate FBX-uri cu nume de oase UE5. Scriptul de aici
automatizeaza pasii din editor: importul FBX-urilor si, optional, retargetarea
in bloc pe MetaHuman folosind un IK Retargeter facut o singura data manual.

Se ruleaza in UE5 cu pluginul "Python Editor Script Plugin" activat:
    Tools > Execute Python Script...  (sau `py "cale/unreal_import.py"` in consola)
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

TEMPLATE = '''# -*- coding: utf-8 -*-
"""Import + retarget pentru FBX-urile convertite din Mixamo.

Generat de mixamo2metahuman. Ruleaza-l in UE5:
    Tools > Execute Python Script...
Cere pluginul "Python Editor Script Plugin" activat.
"""

import os
import unreal

# --------------------------------------------------------------------------- #
# CONFIGURARE  (singura parte pe care o editezi)
# --------------------------------------------------------------------------- #

# FBX-urile produse de aplicatie.
FBX_FILES = [
{fbx_list}
]

# Unde ajung asseturile in proiect.
DESTINATION = "{destination}"

# Ce importam: True = animatii pe un schelet existent, False = personaj (mesh).
IMPORT_AS_ANIMATION = {import_as_animation}

# Scheletul pe care se importa animatiile. Obligatoriu cand
# IMPORT_AS_ANIMATION = True. Exemplu:
#   "/Game/Mixamo/Character/UE5_Mixamo_Skeleton"
SKELETON_PATH = "{skeleton_path}"

# --- Retarget pe MetaHuman (optional) -------------------------------------- #
# Creeaza o data, manual, un IK Retargeter in editor:
#   1. IK Rig pentru scheletul Mixamo convertit (Retarget Root = pelvis)
#   2. IK Rig pentru MetaHuman (sau foloseste IK_Metahuman din proiect)
#   3. IK Retargeter cu sursa = rig-ul Mixamo, tinta = rig-ul MetaHuman
# Apoi pune calea lui aici si scriptul retargeteaza tot ce a importat.
RETARGETER_PATH = ""          # ex: "/Game/Mixamo/RTG_Mixamo_To_MetaHuman"
SOURCE_MESH_PATH = ""         # skeletal mesh-ul sursa (Mixamo)
TARGET_MESH_PATH = ""         # skeletal mesh-ul MetaHuman
RETARGET_DESTINATION = "{destination}/Retargeted"
RETARGET_PREFIX = ""
RETARGET_SUFFIX = "_MH"


# --------------------------------------------------------------------------- #
# import
# --------------------------------------------------------------------------- #
def build_task(fbx_path):
    options = unreal.FbxImportUI()
    options.set_editor_property("import_mesh", not IMPORT_AS_ANIMATION)
    options.set_editor_property("import_as_skeletal", True)
    options.set_editor_property("import_animations", True)
    options.set_editor_property("import_materials", not IMPORT_AS_ANIMATION)
    options.set_editor_property("import_textures", not IMPORT_AS_ANIMATION)
    options.set_editor_property(
        "mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION
        if IMPORT_AS_ANIMATION else unreal.FBXImportType.FBXIT_SKELETAL_MESH
    )

    if SKELETON_PATH:
        skeleton = unreal.load_asset(SKELETON_PATH)
        if skeleton is None:
            raise RuntimeError("Nu gasesc scheletul: " + SKELETON_PATH)
        options.set_editor_property("skeleton", skeleton)
    elif IMPORT_AS_ANIMATION:
        raise RuntimeError(
            "SKELETON_PATH e gol. Importa intai personajul, apoi pune calea "
            "scheletului rezultat aici."
        )

    anim_data = options.get_editor_property("anim_sequence_import_data")
    anim_data.set_editor_property("import_custom_attribute", True)
    anim_data.set_editor_property("remove_redundant_keys", False)
    anim_data.set_editor_property("convert_scene", True)
    anim_data.set_editor_property("force_front_x_axis", False)
    anim_data.set_editor_property("use_default_sample_rate", False)

    mesh_data = options.get_editor_property("skeletal_mesh_import_data")
    mesh_data.set_editor_property("import_morph_targets", True)
    mesh_data.set_editor_property("convert_scene", True)
    mesh_data.set_editor_property("update_skeleton_reference_pose", False)

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", fbx_path)
    task.set_editor_property("destination_path", DESTINATION)
    task.set_editor_property("options", options)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    return task


def import_all():
    missing = [p for p in FBX_FILES if not os.path.isfile(p)]
    for path in missing:
        unreal.log_warning("Lipseste fisierul: " + path)

    tasks = [build_task(p) for p in FBX_FILES if os.path.isfile(p)]
    if not tasks:
        unreal.log_warning("Nu am ce importa.")
        return []

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

    imported = []
    for task in tasks:
        for path in task.get_editor_property("imported_object_paths"):
            imported.append(path)
            unreal.log("Importat: " + path)
    return imported


# --------------------------------------------------------------------------- #
# retarget
# --------------------------------------------------------------------------- #
def retarget(asset_paths):
    """Retargeteaza animatiile importate pe MetaHuman.

    API-ul de batch retarget difera intre versiuni de UE, asa ca incercam
    intai varianta din 5.4+ si cadem pe cea veche daca nu exista.
    """
    if not (RETARGETER_PATH and SOURCE_MESH_PATH and TARGET_MESH_PATH):
        unreal.log(
            "Retarget sarit: completeaza RETARGETER_PATH, SOURCE_MESH_PATH "
            "si TARGET_MESH_PATH."
        )
        return []

    retargeter = unreal.load_asset(RETARGETER_PATH)
    source_mesh = unreal.load_asset(SOURCE_MESH_PATH)
    target_mesh = unreal.load_asset(TARGET_MESH_PATH)
    for asset, name in ((retargeter, RETARGETER_PATH),
                        (source_mesh, SOURCE_MESH_PATH),
                        (target_mesh, TARGET_MESH_PATH)):
        if asset is None:
            raise RuntimeError("Nu gasesc assetul: " + name)

    animations = [
        a for a in (unreal.load_asset(p) for p in asset_paths)
        if isinstance(a, unreal.AnimSequence)
    ]
    if not animations:
        unreal.log_warning("Nu am gasit AnimSequence-uri de retargetat.")
        return []

    batch = unreal.IKRetargetBatchOperation
    if hasattr(batch, "duplicate_and_retarget"):        # UE 5.4+
        return list(batch.duplicate_and_retarget(
            animations, source_mesh, target_mesh, retargeter,
            "", "", RETARGET_PREFIX, RETARGET_SUFFIX, True,
        ))

    context = unreal.IKRetargetBatchOperationContext()  # UE 5.0 - 5.3
    context.set_editor_property("assets_to_retarget", animations)
    context.set_editor_property("source_mesh", source_mesh)
    context.set_editor_property("target_mesh", target_mesh)
    context.set_editor_property("ik_retarget_asset", retargeter)
    context.set_editor_property("remap_referenced_assets", True)
    name_rule = context.get_editor_property("name_rule")
    name_rule.set_editor_property("prefix", RETARGET_PREFIX)
    name_rule.set_editor_property("suffix", RETARGET_SUFFIX)
    name_rule.set_editor_property("folder_path", RETARGET_DESTINATION)
    return list(batch().run_retarget(context))


def main():
    imported = import_all()
    try:
        retargeted = retarget(imported)
    except Exception as exc:
        unreal.log_error("Retarget esuat: %s" % exc)
        retargeted = []
    unreal.log("Gata: %d importate, %d retargetate." % (len(imported), len(retargeted)))


main()
'''


def generate(
    fbx_files: Iterable[str],
    destination: str = "/Game/Mixamo",
    import_as_animation: bool = True,
    skeleton_path: str = "",
) -> str:
    """Textul scriptului pentru Unreal, cu caile deja completate."""
    files = [str(Path(f).resolve()).replace("\\", "/") for f in fbx_files]
    fbx_list = "\n".join('    r"%s",' % f for f in files)
    return TEMPLATE.format(
        fbx_list=fbx_list,
        destination=destination.rstrip("/") or "/Game/Mixamo",
        import_as_animation="True" if import_as_animation else "False",
        skeleton_path=skeleton_path,
    )


def write(
    path: str | Path,
    fbx_files: Iterable[str],
    destination: str = "/Game/Mixamo",
    import_as_animation: bool = True,
    skeleton_path: str = "",
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        generate(fbx_files, destination, import_as_animation, skeleton_path),
        encoding="utf-8",
    )
    return target
