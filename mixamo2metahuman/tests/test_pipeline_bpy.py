"""Test de integrare: FBX Mixamo -> conversie -> reimport si verificare.

Are nevoie de Blender ca modul Python (`pip install bpy`). Fara el testul se
sare, ca suita de baza sa ramana rulabila oriunde.
"""

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "mixamo2mh"))   # blender_ops se importa ca script

try:
    import bpy
    import blender_ops as ops
    import fixture_mixamo
    SKIP_REASON = ""
except ImportError as exc:
    SKIP_REASON = "cere `pip install bpy` (%s)" % exc

from mixamo2mh.blender import run_conversion
from mixamo2mh.settings import ConversionSettings


def reimport(path):
    """Reimporta pastrand oasele frunza si orientarea originala.

    `automatic_bone_orientation` ar reconecta oasele si ar pierde canalele de
    translatie la citire - un artefact al importului, nu al fisierului.
    """
    ops.reset_scene()
    bpy.ops.import_scene.fbx(filepath=str(path), ignore_leaf_bones=False,
                             automatic_bone_orientation=False)
    return ops.find_armature()


def world_path(path, bone):
    arm = reimport(path)
    start, end = ops.frame_range(ops.get_action(arm))
    positions = []
    for frame in range(start, end + 1):
        bpy.context.scene.frame_set(frame)
        positions.append((arm.matrix_world @ arm.pose.bones[bone].matrix).translation.copy())
    return positions


@unittest.skipIf(SKIP_REASON, SKIP_REASON)
class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.source = str(fixture_mixamo.build(str(cls.dir / "Mixamo_Walking.fbx")))
        cls.source_path = world_path(cls.source, "mixamorig:Hips")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def job(self, name, **kwargs):
        base = dict(input=self.source, output=str(self.dir / name), mode="animation",
                    root_motion="extract", add_root_bone=True, rename_bones=True,
                    keep_unmapped_bones=True, automatic_bone_orientation=True,
                    scale=1.0, rename_action=True)
        base.update(kwargs)
        return base

    # ------------------------------------------------------------ schelet --
    def test_bones_get_ue5_names(self):
        report = ops.run_job(self.job("names.fbx"))
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["renamed_bones"], fixture_mixamo.RENAMED_BONE_COUNT)
        self.assertEqual(report["unmapped_bones"], fixture_mixamo.UNMAPPED_BONES)

        arm = reimport(self.dir / "names.fbx")
        names = [b.name for b in arm.data.bones]
        for expected in ("root", "pelvis", "spine_01", "spine_03", "neck_01", "head",
                         "clavicle_l", "upperarm_r", "lowerarm_l", "hand_r",
                         "thumb_01_l", "thumb_02_l", "index_01_l",
                         "thigh_l", "calf_r", "foot_l", "ball_r"):
            self.assertIn(expected, names)
        self.assertFalse([n for n in names if n.startswith("mixamorig")])
        self.assertIn("Ponytail", names, "oasele extra trebuie pastrate")
        self.assertEqual(arm.data.bones["pelvis"].parent.name, "root")

    def test_animation_mode_drops_mesh(self):
        ops.run_job(self.job("anim.fbx"))
        reimport(self.dir / "anim.fbx")
        self.assertFalse([o for o in bpy.data.objects if o.type == "MESH"])

    def test_take_name_follows_file_name(self):
        ops.run_job(self.job("Walk_UE5.fbx"))
        arm = reimport(self.dir / "Walk_UE5.fbx")
        self.assertIn("Walk_UE5", ops.get_action(arm).name)

    # -------------------------------------------------------- root motion --
    def test_root_motion_preserves_world_trajectory(self):
        ops.run_job(self.job("root.fbx"))
        converted = world_path(self.dir / "root.fbx", "pelvis")
        self.assertEqual(len(converted), len(self.source_path))
        worst = max((a - b).length for a, b in zip(converted, self.source_path))
        self.assertLess(worst, 1e-3, "soldurile s-au deplasat cu %.6f m" % worst)

    def test_root_bone_carries_horizontal_motion(self):
        ops.run_job(self.job("root2.fbx"))
        track = world_path(self.dir / "root2.fbx", "root")
        self.assertGreater(track[-1].y - track[0].y, fixture_mixamo.TRAVEL * 0.95)
        self.assertLess(max(abs(p.z) for p in track), 1e-6, "root trebuie sa stea la sol")
        drift = max(abs(r.x - s.x) for r, s in zip(track, self.source_path))
        self.assertLess(drift, 1e-5)

    def test_inplace_locks_horizontal_but_keeps_bob(self):
        ops.run_job(self.job("inplace.fbx", root_motion="inplace"))
        track = world_path(self.dir / "inplace.fbx", "pelvis")
        self.assertLess(max(abs(p.y - track[0].y) for p in track), 1e-6)
        self.assertLess(max(abs(p.x - track[0].x) for p in track), 1e-6)
        bob = max(p.z for p in track) - min(p.z for p in track)
        self.assertGreater(bob, fixture_mixamo.BOB, "miscarea verticala nu trebuie atinsa")

    def test_keep_leaves_animation_untouched(self):
        ops.run_job(self.job("keep.fbx", root_motion="keep"))
        track = world_path(self.dir / "keep.fbx", "pelvis")
        worst = max((a - b).length for a, b in zip(track, self.source_path))
        self.assertLess(worst, 1e-3)

    # ------------------------------------------------------------- moduri --
    def test_character_mode_exports_skinned_mesh(self):
        report = ops.run_job(self.job("character.fbx", mode="character", root_motion="keep"))
        self.assertTrue(report["ok"], report)
        reimport(self.dir / "character.fbx")
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        self.assertEqual(len(meshes), 1)
        self.assertTrue(any(m.type == "ARMATURE" for m in meshes[0].modifiers))
        self.assertIn("pelvis", [g.name for g in meshes[0].vertex_groups],
                      "grupurile de vertecsi trebuie sa urmeze redenumirea")

    def test_rename_disabled_keeps_mixamo_names(self):
        ops.run_job(self.job("raw.fbx", rename_bones=False, add_root_bone=False,
                             root_motion="keep"))
        arm = reimport(self.dir / "raw.fbx")
        names = [b.name for b in arm.data.bones]
        self.assertTrue([n for n in names if n.startswith("mixamorig")])
        self.assertNotIn("root", names)

    def test_scale_is_applied_on_export(self):
        ops.run_job(self.job("scaled.fbx", scale=100.0, root_motion="keep"))
        scaled = world_path(self.dir / "scaled.fbx", "pelvis")
        self.assertAlmostEqual(scaled[0].z / self.source_path[0].z, 100.0, delta=0.5)

    def test_converting_twice_is_harmless(self):
        ops.run_job(self.job("once.fbx"))
        report = ops.run_job(self.job("twice.fbx", input=str(self.dir / "once.fbx")))
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["renamed_bones"], 0, "al doilea pas nu mai are ce redenumi")

    def test_broken_file_raises_clear_error(self):
        broken = self.dir / "broken.fbx"
        broken.write_bytes(b"nu sunt un FBX")
        with self.assertRaises(Exception):
            ops.run_job(self.job("from_broken.fbx", input=str(broken)))


@unittest.skipIf(SKIP_REASON, SKIP_REASON)
class TestRunConversion(unittest.TestCase):
    """Verifica si plumbing-ul aplicatiei (subproces + raport JSON).

    Blender-ul e inlocuit cu un mic script care ruleaza acelasi `blender_ops.py`
    prin interpretorul curent, unde `bpy` e disponibil ca modul.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.source = fixture_mixamo.build(str(cls.dir / "Mixamo_Run.fbx"))

        cls.fake = cls.dir / "fake_blender.sh"
        cls.fake.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "--version" ]; then echo "Blender 5.0.1 (fake)"; exit 0; fi\n'
            "# pastram doar argumentele de dupa --python\n"
            "while [ \"$1\" != \"--python\" ]; do shift; done\n"
            "shift\n"
            'exec "%s" "$@"\n' % sys.executable,
            encoding="utf-8",
        )
        cls.fake.chmod(cls.fake.stat().st_mode | stat.S_IEXEC)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_batch_reports_success_and_writes_files(self):
        out = self.dir / "export"
        settings = ConversionSettings(
            inputs=[self.source], output_dir=str(out), blender=str(self.fake),
        )
        self.assertEqual(settings.validate(), [])

        lines = []
        results = run_conversion(settings, log=lines.append)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok, results[0].message)
        self.assertEqual(results[0].renamed_bones, fixture_mixamo.RENAMED_BONE_COUNT)
        self.assertTrue(os.path.isfile(results[0].output))
        self.assertEqual(Path(results[0].output).name, "Mixamo_Run_UE5.fbx")
        self.assertTrue(any("Blender" in line for line in lines))

    def test_failure_is_reported_not_raised(self):
        broken = self.dir / "broken.fbx"
        broken.write_bytes(b"nu sunt un FBX")
        settings = ConversionSettings(
            inputs=[str(broken)], output_dir=str(self.dir / "export2"),
            blender=str(self.fake),
        )
        results = run_conversion(settings, log=lambda _m: None)
        self.assertFalse(results[0].ok)
        self.assertTrue(results[0].message, "erorile trebuie sa ajunga in raport")

    def test_overwrite_disabled_skips_existing(self):
        out = self.dir / "export3"
        settings = ConversionSettings(
            inputs=[self.source], output_dir=str(out), blender=str(self.fake),
        )
        run_conversion(settings, log=lambda _m: None)
        settings.overwrite = False
        results = run_conversion(settings, log=lambda _m: None)
        self.assertFalse(results[0].ok)
        self.assertIn("exista deja", results[0].message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
