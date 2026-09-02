"""Construieste un FBX cu structura unui export Mixamo (are nevoie de `bpy`).

Folosit de testul de integrare ca sa nu depindem de un fisier binar in repo.
"""

import math

import bpy
from mathutils import Matrix, Vector

PREFIX = "mixamorig:"

#: (nume, cap, coada, parinte) - un schelet Mixamo redus, dar cu toate zonele.
HIERARCHY = [
    ("Hips", (0, 0, 1.0), (0, 0, 1.1), None),
    ("Spine", (0, 0, 1.1), (0, 0, 1.25), "Hips"),
    ("Spine1", (0, 0, 1.25), (0, 0, 1.4), "Spine"),
    ("Spine2", (0, 0, 1.4), (0, 0, 1.55), "Spine1"),
    ("Neck", (0, 0, 1.55), (0, 0, 1.65), "Spine2"),
    ("Head", (0, 0, 1.65), (0, 0, 1.8), "Neck"),
    ("LeftShoulder", (0, 0, 1.5), (0.15, 0, 1.5), "Spine2"),
    ("LeftArm", (0.15, 0, 1.5), (0.45, 0, 1.5), "LeftShoulder"),
    ("LeftForeArm", (0.45, 0, 1.5), (0.7, 0, 1.5), "LeftArm"),
    ("LeftHand", (0.7, 0, 1.5), (0.8, 0, 1.5), "LeftForeArm"),
    ("LeftHandThumb1", (0.8, 0.02, 1.5), (0.84, 0.04, 1.5), "LeftHand"),
    ("LeftHandThumb2", (0.84, 0.04, 1.5), (0.87, 0.06, 1.5), "LeftHandThumb1"),
    ("LeftHandIndex1", (0.8, 0, 1.5), (0.85, 0, 1.5), "LeftHand"),
    ("RightShoulder", (0, 0, 1.5), (-0.15, 0, 1.5), "Spine2"),
    ("RightArm", (-0.15, 0, 1.5), (-0.45, 0, 1.5), "RightShoulder"),
    ("RightForeArm", (-0.45, 0, 1.5), (-0.7, 0, 1.5), "RightArm"),
    ("RightHand", (-0.7, 0, 1.5), (-0.8, 0, 1.5), "RightForeArm"),
    ("LeftUpLeg", (0.1, 0, 1.0), (0.1, 0, 0.55), "Hips"),
    ("LeftLeg", (0.1, 0, 0.55), (0.1, 0, 0.1), "LeftUpLeg"),
    ("LeftFoot", (0.1, 0, 0.1), (0.1, 0.15, 0.02), "LeftLeg"),
    ("LeftToeBase", (0.1, 0.15, 0.02), (0.1, 0.22, 0.02), "LeftFoot"),
    ("RightUpLeg", (-0.1, 0, 1.0), (-0.1, 0, 0.55), "Hips"),
    ("RightLeg", (-0.1, 0, 0.55), (-0.1, 0, 0.1), "RightUpLeg"),
    ("RightFoot", (-0.1, 0, 0.1), (-0.1, 0.15, 0.02), "RightLeg"),
    ("RightToeBase", (-0.1, 0.15, 0.02), (-0.1, 0.22, 0.02), "RightFoot"),
    ("Ponytail", (0, 0, 1.8), (0, -0.1, 1.85), "Head"),   # os fara corespondent UE5
]

#: Oasele fara corespondent UE5 (li se scoate doar prefixul "mixamorig:").
UNMAPPED_BONES = ["mixamorig:Ponytail"]

#: Cate oase primesc un nume nou: cele mapate + cele carora li se curata prefixul.
RENAMED_BONE_COUNT = len(HIERARCHY)

FRAMES = 30
TRAVEL = 2.0      # deplasare inainte, in metri
BOB = 0.03        # amplitudinea urcarii/coborarii soldurilor


def build(filepath):
    """Scrie FBX-ul de test si returneaza calea lui."""
    bpy.ops.wm.read_homefile(use_empty=True)

    arm_data = bpy.data.armatures.new("Armature")
    arm = bpy.data.objects.new("Armature", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)

    bpy.ops.object.mode_set(mode="EDIT")
    for name, head, tail, parent in HIERARCHY:
        bone = arm_data.edit_bones.new(PREFIX + name)
        bone.head, bone.tail = Vector(head), Vector(tail)
        if parent:
            bone.parent = arm_data.edit_bones[PREFIX + parent]
    bpy.ops.object.mode_set(mode="OBJECT")

    arm.animation_data_create()
    arm.animation_data.action = bpy.data.actions.new("mixamo.com")

    hips = arm.pose.bones[PREFIX + "Hips"]
    knee = arm.pose.bones[PREFIX + "LeftLeg"]
    hips.rotation_mode = knee.rotation_mode = "QUATERNION"
    rest = hips.bone.matrix_local

    for frame in range(1, FRAMES + 1):
        t = (frame - 1) / float(FRAMES - 1)
        # deplasare reala in lume (nu pe axele locale ale osului)
        offset = Vector((0.05 * math.sin(t * 6.28), TRAVEL * t, BOB * math.sin(t * 12.56)))
        hips.matrix = Matrix.Translation(offset) @ rest @ Matrix.Rotation(t * 0.6, 4, "Y")
        bpy.context.view_layer.update()
        hips.keyframe_insert("location", frame=frame)
        hips.keyframe_insert("rotation_quaternion", frame=frame)
        knee.rotation_quaternion = (math.cos(t * 0.5), math.sin(t * 0.5), 0, 0)
        knee.keyframe_insert("rotation_quaternion", frame=frame)

    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(0, 0, 1.2))
    mesh = bpy.context.object
    mesh.name = "Body"
    group = mesh.vertex_groups.new(name=PREFIX + "Hips")
    group.add(range(len(mesh.data.vertices)), 1.0, "REPLACE")
    mesh.parent = arm
    mesh.modifiers.new("Armature", "ARMATURE").object = arm

    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, FRAMES
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    arm.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(filepath=filepath, use_selection=True,
                             add_leaf_bones=True, bake_anim=True)
    return filepath
