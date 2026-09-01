"""Teste pentru partea care nu are nevoie de Blender."""

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mixamo2mh import unreal_script
from mixamo2mh.blender import _tail, collect_fbx, find_blender, BlenderNotFound
from mixamo2mh.bone_map import (
    MIXAMO_TO_UE5,
    build_rename_map,
    strip_prefix,
    ue_name,
)
from mixamo2mh.cli import build_parser, settings_from_args
from mixamo2mh.settings import (
    MODE_CHARACTER,
    ROOT_EXTRACT,
    ROOT_KEEP,
    ConversionSettings,
)

# Scheletul complet exportat de Mixamo (fara oasele frunza).
MIXAMO_SKELETON = [
    "mixamorig:Hips", "mixamorig:Spine", "mixamorig:Spine1", "mixamorig:Spine2",
    "mixamorig:Neck", "mixamorig:Head",
    "mixamorig:LeftShoulder", "mixamorig:LeftArm", "mixamorig:LeftForeArm",
    "mixamorig:LeftHand", "mixamorig:RightShoulder", "mixamorig:RightArm",
    "mixamorig:RightForeArm", "mixamorig:RightHand",
    "mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:LeftFoot",
    "mixamorig:LeftToeBase", "mixamorig:RightUpLeg", "mixamorig:RightLeg",
    "mixamorig:RightFoot", "mixamorig:RightToeBase",
] + [
    "mixamorig:%sHand%s%d" % (side, finger, i)
    for side in ("Left", "Right")
    for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky")
    for i in (1, 2, 3)
]


class TestBoneMap(unittest.TestCase):
    def test_strip_prefix_variants(self):
        for name in ("mixamorig:Hips", "mixamorig1:Hips", "mixamorig_Hips", "Hips"):
            self.assertEqual(strip_prefix(name), "Hips")

    def test_core_bones(self):
        self.assertEqual(ue_name("mixamorig:Hips"), "pelvis")
        self.assertEqual(ue_name("mixamorig:Spine2"), "spine_03")
        self.assertEqual(ue_name("mixamorig:LeftArm"), "upperarm_l")
        self.assertEqual(ue_name("mixamorig:RightForeArm"), "lowerarm_r")
        self.assertEqual(ue_name("mixamorig:LeftUpLeg"), "thigh_l")
        self.assertEqual(ue_name("mixamorig:RightToeBase"), "ball_r")
        self.assertEqual(ue_name("mixamorig:LeftHandPinky3"), "pinky_03_l")

    def test_unknown_bone(self):
        self.assertIsNone(ue_name("mixamorig:Ponytail"))

    def test_full_skeleton_is_mapped(self):
        rename, unmapped = build_rename_map(MIXAMO_SKELETON)
        self.assertEqual(unmapped, [])
        self.assertEqual(len(rename), len(MIXAMO_SKELETON))
        self.assertIn("pelvis", rename.values())

    def test_no_duplicate_targets(self):
        targets = list(MIXAMO_TO_UE5.values())
        self.assertEqual(len(targets), len(set(targets)))

    def test_unmapped_bones_keep_clean_name(self):
        rename, unmapped = build_rename_map(["mixamorig:Skirt_01"])
        self.assertEqual(unmapped, ["mixamorig:Skirt_01"])
        self.assertEqual(rename["mixamorig:Skirt_01"], "Skirt_01")

    def test_unmapped_bones_can_be_left_alone(self):
        rename, _ = build_rename_map(["mixamorig:Skirt_01"], keep_unmapped=False)
        self.assertEqual(rename, {})

    def test_collision_is_skipped(self):
        # Un os deja numit "pelvis" plus "Hips" ar produce doua "pelvis".
        rename, _ = build_rename_map(["pelvis", "mixamorig:Hips"])
        self.assertNotIn("mixamorig:Hips", rename)

    def test_already_converted_skeleton_is_a_noop(self):
        rename, _ = build_rename_map(["pelvis", "spine_01", "thigh_l"])
        self.assertEqual(rename, {})


class TestSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fbx = Path(self.tmp.name) / "Walking.fbx"
        self.fbx.write_bytes(b"fake")

    def tearDown(self):
        self.tmp.cleanup()

    def _valid(self, **kwargs):
        base = dict(inputs=[str(self.fbx)], output_dir=self.tmp.name)
        base.update(kwargs)
        return ConversionSettings(**base)

    def test_valid_settings(self):
        self.assertEqual(self._valid().validate(), [])

    def test_missing_input(self):
        problems = ConversionSettings(output_dir=self.tmp.name).validate()
        self.assertTrue(any("FBX" in p for p in problems))

    def test_missing_file(self):
        settings = self._valid(inputs=["/nu/exista.fbx"])
        self.assertTrue(any("nu exista" in p for p in settings.validate()))

    def test_wrong_extension(self):
        other = Path(self.tmp.name) / "model.obj"
        other.write_bytes(b"x")
        settings = self._valid(inputs=[str(other)])
        self.assertTrue(any("Nu e un FBX" in p for p in settings.validate()))

    def test_root_motion_needs_root_bone(self):
        settings = self._valid(root_motion=ROOT_EXTRACT, add_root_bone=False)
        self.assertTrue(any("root" in p for p in settings.validate()))

    def test_negative_scale(self):
        self.assertTrue(any("Scala" in p for p in self._valid(scale=0).validate()))

    def test_output_path_uses_suffix(self):
        settings = self._valid(suffix="_UE5")
        self.assertEqual(settings.output_path(str(self.fbx)).name, "Walking_UE5.fbx")

    def test_roundtrip_json(self):
        settings = self._valid(mode=MODE_CHARACTER, root_motion=ROOT_KEEP, scale=0.01)
        restored = ConversionSettings.from_dict(json.loads(settings.to_json()))
        self.assertEqual(restored, settings)

    def test_from_dict_ignores_extra_keys(self):
        restored = ConversionSettings.from_dict({"scale": 2.0, "necunoscut": 1})
        self.assertEqual(restored.scale, 2.0)


class TestCollectFbx(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "sub").mkdir()
        for name in ("a.FBX", "b.fbx", "c.txt"):
            (root / name).write_bytes(b"x")
        (root / "sub" / "d.fbx").write_bytes(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_folder_recursion_and_filtering(self):
        found = collect_fbx([self.tmp.name])
        names = sorted(Path(p).name for p in found)
        self.assertEqual(names, ["a.FBX", "b.fbx", "d.fbx"])

    def test_no_duplicates(self):
        single = str(Path(self.tmp.name) / "b.fbx")
        self.assertEqual(len(collect_fbx([self.tmp.name, single])), 3)

    def test_non_recursive(self):
        self.assertEqual(len(collect_fbx([self.tmp.name], recursive=False)), 2)


class TestBlenderHelpers(unittest.TestCase):
    def test_explicit_bad_path_raises(self):
        with self.assertRaises(BlenderNotFound):
            find_blender("/nu/exista/blender")

    def test_tail_keeps_last_lines(self):
        self.assertEqual(_tail("a\n\nb\nc", lines=2), "b | c")

    def test_blender_script_exists(self):
        script = Path(__file__).resolve().parents[1] / "mixamo2mh" / "blender_ops.py"
        self.assertTrue(script.is_file())
        ast.parse(script.read_text(encoding="utf-8"))


class TestUnrealScript(unittest.TestCase):
    def test_generated_script_is_valid_python(self):
        text = unreal_script.generate(["/tmp/Walk_UE5.fbx"], "/Game/Mixamo", True, "/Game/Sk")
        ast.parse(text)

    def test_paths_are_embedded(self):
        text = unreal_script.generate(["/tmp/Walk_UE5.fbx"])
        self.assertIn("Walk_UE5.fbx", text)
        self.assertIn('DESTINATION = "/Game/Mixamo"', text)

    def test_windows_paths_are_escaped(self):
        text = unreal_script.generate([r"C:\anim\Walk.fbx"])
        ast.parse(text)
        self.assertNotIn("\\a", text.split("FBX_FILES")[1].split("]")[0])

    def test_mode_flag(self):
        self.assertIn("IMPORT_AS_ANIMATION = False",
                      unreal_script.generate(["/tmp/a.fbx"], import_as_animation=False))

    def test_write_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = unreal_script.write(Path(tmp) / "sub" / "unreal_import.py", ["/tmp/a.fbx"])
            self.assertTrue(target.is_file())
            ast.parse(target.read_text(encoding="utf-8"))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fbx = Path(self.tmp.name) / "Run.fbx"
        self.fbx.write_bytes(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults(self):
        args = build_parser().parse_args([str(self.fbx), "-o", self.tmp.name])
        settings = settings_from_args(args)
        self.assertEqual(settings.validate(), [])
        self.assertTrue(settings.rename_bones)
        self.assertTrue(settings.add_root_bone)
        self.assertEqual(settings.root_motion, ROOT_EXTRACT)

    def test_flags(self):
        args = build_parser().parse_args(
            [self.tmp.name, "-o", "out", "--no-rename", "--no-root-bone",
             "--root-motion", "keep", "--scale", "0.01", "--mode", "character"]
        )
        settings = settings_from_args(args)
        self.assertFalse(settings.rename_bones)
        self.assertFalse(settings.add_root_bone)
        self.assertEqual(settings.scale, 0.01)
        self.assertEqual(settings.mode, MODE_CHARACTER)
        self.assertEqual(settings.inputs, [str(self.fbx)])

    def test_missing_output_is_rejected(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([str(self.fbx)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
