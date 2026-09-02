"""Ruleaza INAUNTRUL Blender-ului (`blender --background --python blender_ops.py`).

Primeste un job JSON, face conversia unui singur FBX Mixamo si scrie un raport
JSON. Nu e importat de aplicatie ca modul, ci pornit ca script, deci isi adauga
singur folderul in sys.path ca sa gaseasca `bone_map`.
"""

import json
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import bpy  # noqa: E402  (disponibil doar in Blender)
from mathutils import Matrix, Vector  # noqa: E402

from bone_map import PELVIS_BONE, ROOT_BONE, build_rename_map  # noqa: E402


# --------------------------------------------------------------------------- #
# scena
# --------------------------------------------------------------------------- #
def reset_scene():
    bpy.ops.wm.read_homefile(use_empty=True)


def ensure_fbx_addon():
    """Se asigura ca importatorul/exportatorul FBX e activ.

    Cu `--factory-startup` e activ implicit, dar daca cineva a dezactivat
    add-on-ul in preferinte, il pornim doar pentru aceasta rulare.
    """
    try:
        import addon_utils
        addon_utils.enable("io_scene_fbx", default_set=False, persistent=True)
    except Exception:
        pass  # in versiunile unde e integrat, nu exista nimic de activat


def import_fbx(path, automatic_bone_orientation=True):
    ensure_fbx_addon()
    bpy.ops.import_scene.fbx(
        filepath=path,
        use_anim=True,
        ignore_leaf_bones=True,           # scapa de *_end / *Toe_End
        automatic_bone_orientation=automatic_bone_orientation,
        use_custom_props=False,
    )


def find_armature():
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not armatures:
        raise RuntimeError(
            "FBX-ul nu contine niciun schelet (armature). "
            "Verifica daca e un export Mixamo cu 'skin'."
        )
    if len(armatures) > 1:
        # Mixamo exporta un singur schelet; daca sunt mai multe il luam pe
        # cel cu cele mai multe oase si mergem mai departe.
        armatures.sort(key=lambda o: len(o.data.bones), reverse=True)
    return armatures[0]


def activate(obj):
    current = bpy.context.object
    if current is not None and current.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


# --------------------------------------------------------------------------- #
# oase
# --------------------------------------------------------------------------- #
def rename_bones(arm_obj, keep_unmapped=True):
    """Redenumeste oasele Mixamo in conventia UE5. Returneaza (nr, nemapate)."""
    names = [b.name for b in arm_obj.data.bones]
    rename, unmapped = build_rename_map(names, keep_unmapped=keep_unmapped)

    for old, new in rename.items():
        bone = arm_obj.data.bones.get(old)
        if bone is not None:
            bone.name = new

    _fix_action_paths(arm_obj, rename)
    return len(rename), unmapped


def iter_fcurves(action):
    """F-Curves-urile unei actiuni, indiferent de versiunea de Blender.

    Pana in 4.3 stateau in `action.fcurves`; din 4.4 (slotted actions) sunt in
    `action.layers[].strips[].channelbags[].fcurves`.
    """
    if action is None:
        return []
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    curves = []
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                curves.extend(bag.fcurves)
    return curves


def iter_groups(action):
    """Grupurile de canale ale unei actiuni (vezi `iter_fcurves`)."""
    if action is None:
        return []
    if hasattr(action, "groups"):
        return list(action.groups)
    groups = []
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                groups.extend(bag.groups)
    return groups


def _fix_action_paths(arm_obj, rename):
    """Plasa de siguranta pentru caile din F-Curves.

    Blender rescrie de obicei singur `pose.bones["..."]` la redenumire; daca
    dintr-un motiv oarecare nu a facut-o, corectam manual.
    """
    anim = arm_obj.animation_data
    actions = {anim.action} if anim and anim.action else set()
    for action in actions:
        if action is None:
            continue
        for fcurve in iter_fcurves(action):
            for old, new in rename.items():
                token = 'pose.bones["%s"]' % old
                if token in fcurve.data_path:
                    fcurve.data_path = fcurve.data_path.replace(
                        token, 'pose.bones["%s"]' % new
                    )
        for group in iter_groups(action):
            if group.name in rename:
                group.name = rename[group.name]


def add_root_bone(arm_obj):
    """Adauga osul `root` la origine si ii pune scheletul dedesubt.

    Unreal citeste root motion de pe primul os din ierarhie; Mixamo nu exporta
    unul, deci il cream noi si il facem parinte pentru pelvis.
    """
    if ROOT_BONE in arm_obj.data.bones:
        return False

    activate(arm_obj)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        edit_bones = arm_obj.data.edit_bones
        root = edit_bones.new(ROOT_BONE)
        root.head = Vector((0.0, 0.0, 0.0))
        root.tail = Vector((0.0, 0.25, 0.0))   # orientat pe +Y, ca in UE
        root.roll = 0.0
        for bone in edit_bones:
            if bone is not root and bone.parent is None:
                bone.parent = root
                bone.use_connect = False
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    return True


# --------------------------------------------------------------------------- #
# animatie
# --------------------------------------------------------------------------- #
def get_action(arm_obj):
    anim = arm_obj.animation_data
    return anim.action if anim else None


def frame_range(action):
    start, end = action.frame_range
    return int(round(start)), int(round(end))


def _rotation_path(pose_bone):
    if pose_bone.rotation_mode == "QUATERNION":
        return "rotation_quaternion"
    if pose_bone.rotation_mode == "AXIS_ANGLE":
        return "rotation_axis_angle"
    return "rotation_euler"


def _key(pose_bone, frame):
    pose_bone.keyframe_insert(data_path="location", frame=frame)
    pose_bone.keyframe_insert(data_path=_rotation_path(pose_bone), frame=frame)


def process_root_motion(arm_obj, mode):
    """`extract` muta deplasarea orizontala pe root, `inplace` o anuleaza.

    Lucram pe matricile in spatiul armaturii, nu direct pe F-Curves, pentru ca
    orientarea de repaus a soldurilor Mixamo nu e aliniata la axe si un
    transfer naiv de curbe ar deforma traiectoria.
    """
    action = get_action(arm_obj)
    if action is None or mode == "keep":
        return False

    pelvis = arm_obj.pose.bones.get(PELVIS_BONE)
    if pelvis is None:
        raise RuntimeError(
            "Nu gasesc osul '%s'. Root motion cere redenumirea oaselor "
            "(optiunea 'Redenumeste oasele') activata." % PELVIS_BONE
        )
    root = arm_obj.pose.bones.get(ROOT_BONE)
    if mode == "extract" and root is None:
        raise RuntimeError("Nu gasesc osul '%s' pentru root motion." % ROOT_BONE)

    scene = bpy.context.scene
    start, end = frame_range(action)
    scene.frame_start, scene.frame_end = start, end
    frames = list(range(start, end + 1))

    # Pas 1: memoram pozitia reala a soldurilor pe fiecare cadru, inainte sa
    # modificam ceva (altfel cheile noi ar contamina citirile urmatoare).
    cached = {}
    for frame in frames:
        scene.frame_set(frame)
        cached[frame] = pelvis.matrix.copy()

    reference = cached[frames[0]].translation.copy()

    # Pas 2: rescriem cadrele.
    for frame in frames:
        scene.frame_set(frame)
        original = cached[frame]

        if mode == "extract":
            offset = original.translation
            root.matrix = Matrix.Translation((offset.x, offset.y, 0.0))
            bpy.context.view_layer.update()
            pelvis.matrix = original          # pelvis ramane unde era in lume
            bpy.context.view_layer.update()
            _key(root, frame)
        else:  # inplace
            locked = original.copy()
            locked.translation.x = reference.x
            locked.translation.y = reference.y
            pelvis.matrix = locked
            bpy.context.view_layer.update()

        _key(pelvis, frame)

    for fcurve in iter_fcurves(action):
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "LINEAR"

    return True


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def drop_meshes():
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for obj in meshes:
        bpy.data.objects.remove(obj, do_unlink=True)
    return len(meshes)


def export_fbx(path, arm_obj, mode, scale=1.0):
    activate(arm_obj)
    object_types = {"ARMATURE"}
    if mode == "character":
        object_types.add("MESH")
        for child in arm_obj.children:
            if child.type == "MESH":
                child.select_set(True)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=True,
        object_types=object_types,
        global_scale=scale,
        apply_scale_options="FBX_SCALE_ALL",   # scala ajunge in unitatile FBX
        apply_unit_scale=True,
        bake_space_transform=False,
        add_leaf_bones=False,                  # UE nu vrea oasele frunza
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        armature_nodetype="NULL",
        use_armature_deform_only=False,
        mesh_smooth_type="FACE",
        bake_anim=True,
        bake_anim_use_all_bones=True,
        bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=True,   # take-ul FBX preia numele actiunii
        bake_anim_force_startend_keying=True,
        bake_anim_simplify_factor=0.0,
        path_mode="COPY",
        embed_textures=(mode == "character"),
        axis_forward="-Z",
        axis_up="Y",
    )


# --------------------------------------------------------------------------- #
# job
# --------------------------------------------------------------------------- #
def run_job(job):
    report = {"ok": False, "renamed_bones": 0, "unmapped_bones": [], "message": ""}

    reset_scene()
    import_fbx(job["input"], job.get("automatic_bone_orientation", True))
    arm = find_armature()
    arm.name = "Armature"

    if job.get("rename_bones", True):
        count, unmapped = rename_bones(arm, job.get("keep_unmapped_bones", True))
        report["renamed_bones"] = count
        report["unmapped_bones"] = unmapped

    if job.get("add_root_bone", True):
        add_root_bone(arm)

    process_root_motion(arm, job.get("root_motion", "keep"))

    action = get_action(arm)
    if action is not None and job.get("rename_action", True):
        action.name = os.path.splitext(os.path.basename(job["output"]))[0]
        action.use_fake_user = True

    if job.get("mode") == "animation":
        drop_meshes()

    export_fbx(job["output"], arm, job.get("mode", "animation"), float(job.get("scale", 1.0)))

    report["ok"] = os.path.isfile(job["output"])
    if not report["ok"]:
        report["message"] = "Exportul nu a produs niciun fisier."
    return report


def parse_args(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    args = {}
    for i in range(0, len(argv) - 1, 2):
        args[argv[i].lstrip("-")] = argv[i + 1]
    return args


def main():
    args = parse_args(sys.argv)
    report_path = args.get("report")
    report = {"ok": False, "message": "Scriptul nu a primit un job valid."}
    try:
        with open(args["job"], "r", encoding="utf-8") as handle:
            job = json.load(handle)
        report = run_job(job)
    except Exception as exc:  # raportam eroarea inapoi in aplicatie
        report = {
            "ok": False,
            "renamed_bones": 0,
            "unmapped_bones": [],
            "message": "%s: %s" % (type(exc).__name__, exc),
        }
        traceback.print_exc()
    finally:
        if report_path:
            with open(report_path, "w", encoding="utf-8") as handle:
                json.dump(report, handle)

    sys.exit(0 if report.get("ok") else 1)


if __name__ == "__main__":
    main()
