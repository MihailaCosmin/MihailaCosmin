"""Teste pentru partea care nu are nevoie de Blender."""

import ast
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mixamo2mh import unreal_script
from mixamo2mh.blender import (
    _tail,
    collect_fbx,
    find_blender,
    find_portable,
    is_runnable,
    BlenderNotFound,
)
from mixamo2mh.bone_map import (
    MIXAMO_TO_UE5,
    build_rename_map,
    strip_prefix,
    ue_name,
)
from mixamo2mh.blender import FileResult
from mixamo2mh.cli import build_parser, main as cli_main, settings_from_args
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

    def test_collision_is_skipped_in_both_orders(self):
        # un os deja numit "pelvis" trebuie sa isi pastreze numele, indiferent
        # daca apare inainte sau dupa "Hips" in lista scheletului
        for names in (["pelvis", "mixamorig:Hips"], ["mixamorig:Hips", "pelvis"]):
            rename, _ = build_rename_map(names)
            self.assertNotIn("mixamorig:Hips", rename, str(names))
            self.assertEqual(rename, {}, str(names))

    def test_partial_conversion_does_not_duplicate_names(self):
        # schelet convertit pe jumatate: nimeni nu trebuie sa primeasca un nume
        # pe care il poarta deja alt os
        names = ["pelvis", "spine_01", "mixamorig:Hips", "mixamorig:Spine",
                 "mixamorig:LeftArm"]
        rename, _ = build_rename_map(names)
        final = [rename.get(n, n) for n in names]
        self.assertEqual(len(final), len(set(final)), final)
        self.assertEqual(rename, {"mixamorig:LeftArm": "upperarm_l"})

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

    def test_same_name_in_two_folders_gets_two_outputs(self):
        walk = Path(self.tmp.name) / "walk"
        run = Path(self.tmp.name) / "run"
        for folder in (walk, run):
            folder.mkdir()
            (folder / "Walking.fbx").write_bytes(b"x")
        settings = self._valid(inputs=[str(walk / "Walking.fbx"), str(run / "Walking.fbx")])

        planned = settings.output_paths()
        self.assertEqual(len(set(planned.values())), 2, "s-ar suprascrie unul pe altul")
        self.assertEqual(planned[str(walk / "Walking.fbx")].name, "Walking_UE5.fbx")
        self.assertEqual(planned[str(run / "Walking.fbx")].name, "run_Walking_UE5.fbx")

    def test_three_way_name_clash_still_unique(self):
        folders = []
        for name in ("a", "b", "c"):
            folder = Path(self.tmp.name) / name
            folder.mkdir()
            (folder / "Idle.fbx").write_bytes(b"x")
            folders.append(str(folder / "Idle.fbx"))
        settings = self._valid(inputs=folders)
        self.assertEqual(len(set(settings.output_paths().values())), 3)

    def test_distinct_names_are_left_alone(self):
        second = Path(self.tmp.name) / "Run.fbx"
        second.write_bytes(b"x")
        settings = self._valid(inputs=[str(self.fbx), str(second)])
        names = sorted(p.name for p in settings.output_paths().values())
        self.assertEqual(names, ["Run_UE5.fbx", "Walking_UE5.fbx"])

    def test_root_motion_needs_renamed_bones(self):
        for mode in (ROOT_EXTRACT, "inplace"):
            settings = self._valid(root_motion=mode, rename_bones=False)
            self.assertTrue(any("redenumirea" in p for p in settings.validate()),
                            "root motion fara redenumire ar esua in Blender (%s)" % mode)

    def test_keep_works_without_renaming(self):
        self.assertEqual(self._valid(root_motion=ROOT_KEEP, rename_bones=False).validate(), [])

    def test_output_dir_that_is_a_file_is_rejected(self):
        settings = self._valid(output_dir=str(self.fbx))
        self.assertTrue(any("fisier" in p for p in settings.validate()))

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

    def _portable(self, folder, name, executable=True):
        """Creeaza un fals Blender si returneaza calea lui."""
        path = Path(folder) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n")
        path.chmod(0o755 if executable else 0o644)
        return path

    def test_portable_blender_is_found_next_to_app(self):
        # numele difera intre sisteme, asa ca verificam ce e valid pe fiecare
        name = "Blender/blender.exe" if os.name == "nt" else "Blender/blender"
        with tempfile.TemporaryDirectory() as tmp:
            portable = self._portable(tmp, name)
            self.assertEqual(find_portable([Path(tmp)]), str(portable))
            self.assertEqual(find_blender(roots=[Path(tmp)]), str(portable))

    def test_portable_lookup_ignores_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(find_portable([Path(tmp)]), "")

    def test_windows_needs_an_exe_extension(self):
        """Pe Windows executabilitatea vine din extensie, nu din permisiuni."""
        with tempfile.TemporaryDirectory() as tmp:
            self._portable(tmp, "Blender/blender")          # fara .exe
            self.assertEqual(find_portable([Path(tmp)], windows=True), "")
            exe = self._portable(tmp, "Blender/blender.exe")
            self.assertEqual(find_portable([Path(tmp)], windows=True), str(exe))

    def test_posix_needs_the_execute_bit(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = self._portable(tmp, "Blender/blender", executable=False)
            self.assertEqual(find_portable([Path(tmp)], windows=False), "")
            plain.chmod(0o755)
            self.assertEqual(find_portable([Path(tmp)], windows=False), str(plain))

    def test_explicit_app_bundle_is_accepted(self):
        # pe macOS dialogul returneaza folderul "Blender.app", nu binarul
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "Blender.app"
            binary = self._portable(bundle, "Contents/MacOS/Blender")
            self.assertEqual(find_blender(str(bundle)), str(binary))

    def test_explicit_empty_folder_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BlenderNotFound):
                find_blender(tmp)

    def test_no_window_flag_is_inert_off_windows(self):
        from mixamo2mh.blender import NO_WINDOW
        self.assertIsInstance(NO_WINDOW, int)
        if os.name != "nt":
            self.assertEqual(NO_WINDOW, 0)

    def test_is_runnable_on_missing_file(self):
        self.assertFalse(is_runnable("/nu/exista/blender", windows=True))
        self.assertFalse(is_runnable("/nu/exista/blender", windows=False))

    def test_script_path_points_to_blender_ops(self):
        from mixamo2mh.blender import script_path
        self.assertEqual(script_path().name, "blender_ops.py")
        self.assertTrue(script_path().is_file())

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


class TestFileResult(unittest.TestCase):
    def test_success(self):
        result = FileResult(source="a.fbx", ok=True)
        self.assertFalse(result.failed)
        self.assertTrue(result.usable)

    def test_skipped_is_not_a_failure(self):
        result = FileResult(source="a.fbx", skipped=True)
        self.assertFalse(result.failed, "un fisier sarit deliberat nu e o eroare")
        self.assertTrue(result.usable, "fisierul existent ramane bun de folosit")

    def test_real_failure(self):
        result = FileResult(source="a.fbx", message="boom")
        self.assertTrue(result.failed)
        self.assertFalse(result.usable)


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

    def _run_cli(self, results, extra=()):
        """Ruleaza CLI-ul cu un run_conversion simulat; returneaza (cod, iesire)."""
        args = [str(self.fbx), "-o", self.tmp.name] + list(extra)
        out = io.StringIO()
        with mock.patch("mixamo2mh.cli.run_conversion", return_value=results):
            with contextlib.redirect_stdout(out):
                code = cli_main(args)
        return code, out.getvalue()

    def test_skipped_files_are_not_errors(self):
        skipped = FileResult(source=str(self.fbx), output=str(self.fbx),
                             skipped=True, message="Sarit: fisierul exista deja.")
        code, out = self._run_cli([skipped])
        self.assertEqual(code, 0, "sarirea unui fisier nu trebuie sa dea cod de eroare")
        self.assertIn("sarite", out)
        self.assertNotIn("esuat", out)

    def test_real_failure_sets_exit_code(self):
        failure = FileResult(source=str(self.fbx), message="ceva nu a mers")
        code, out = self._run_cli([failure])
        self.assertEqual(code, 1)
        self.assertIn("esuat", out)

    def test_skipped_files_reach_the_unreal_script(self):
        existing = Path(self.tmp.name) / "Run_UE5.fbx"
        existing.write_bytes(b"x")
        skipped = FileResult(source=str(self.fbx), output=str(existing), skipped=True)
        code, _ = self._run_cli([skipped], extra=["--unreal-script"])
        self.assertEqual(code, 0)
        script = Path(self.tmp.name) / "unreal_import.py"
        self.assertTrue(script.is_file(), "scriptul trebuie generat si pentru fisiere sarite")
        self.assertIn("Run_UE5.fbx", script.read_text(encoding="utf-8"))

    def test_system_errors_are_reported_cleanly(self):
        err = io.StringIO()
        with mock.patch("mixamo2mh.cli.run_conversion",
                        side_effect=PermissionError("acces interzis")):
            with contextlib.redirect_stderr(err):
                code = cli_main([str(self.fbx), "-o", self.tmp.name])
        self.assertEqual(code, 4)
        self.assertIn("acces interzis", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_missing_output_is_rejected(self):
        with open(os.devnull, "w") as quiet, contextlib.redirect_stderr(quiet):
            with self.assertRaises(SystemExit):
                build_parser().parse_args([str(self.fbx)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
