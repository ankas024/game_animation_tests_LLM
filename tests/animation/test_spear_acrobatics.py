"""Checks for assets/animations/combat/A_ch02_SpearAcrobatics.fbx.

    python -I tests/animation/test_spear_acrobatics.py

Re-imports the exported FBX with Blender (bpy) and checks the skeleton, the
take length, that the baked pose matches the generator, ground contact, the
spear bend chain, and the start/end poses.
"""
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "spear_acrobatics"))

import bpy  # noqa: E402

import clips  # noqa: E402
import rig  # noqa: E402
import scene  # noqa: E402

FBX = os.path.join(ROOT, "assets/animations/combat/A_ch02_SpearAcrobatics.fbx")
META = os.path.join(ROOT, "assets/animations/combat/A_ch02_SpearAcrobatics.json")
P = rig.P


def world_heads(arm):
    return {pb.name: arm.matrix_world @ pb.head for pb in arm.pose.bones}


class SpearAcrobaticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # generator reference poses
        gen_arm = scene.setup()
        r = rig.Rig(gen_arm)
        tl = clips.build_timeline()
        cls.n = clips.F1 - clips.F0 + 1
        cls.sample = list(range(0, cls.n, 13)) + [cls.n - 1]
        cls.gen = {}
        for k in cls.sample:
            r.apply(tl.at(clips.F0 + k))
            bpy.context.view_layer.update()
            cls.gen[k] = world_heads(gen_arm)
        # exported file
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=FBX)
        cls.arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
        cls.act = cls.arm.animation_data.action
        cls.meshes = {o.name: o for o in bpy.data.objects if o.type == "MESH"}
        cls.frames = {}
        start = int(round(cls.act.frame_range[0]))   # the FBX importer starts takes at frame 1
        for k in range(cls.n):
            bpy.context.scene.frame_set(start + k)
            cls.frames[k] = world_heads(cls.arm)
        with open(META) as fh:
            cls.meta = json.load(fh)

    def test_skeleton(self):
        bones = {b.name for b in self.arm.data.bones}
        for b in ("Hips", "Spine2", "Head", "LeftHand", "RightHand", "LeftFoot", "RightFoot"):
            self.assertIn(P + b, bones)
        for b in rig.SPEAR_FWD + rig.SPEAR_BACK:
            self.assertIn(b, bones)
        self.assertEqual(self.arm.data.bones[rig.SPEAR].parent.name, P + "Hips")
        roots = [b.name for b in self.arm.data.bones if b.parent is None]
        self.assertEqual(roots, [P + "Hips"], "single root bone")

    def test_meshes(self):
        for name in ("c002_body", "c002_head", "SM_Spear"):
            self.assertIn(name, self.meshes)
        spear = self.meshes["SM_Spear"]
        self.assertEqual({g.name for g in spear.vertex_groups}, set(rig.SPEAR_FWD + rig.SPEAR_BACK))

    def test_length(self):
        lo, hi = self.act.frame_range
        self.assertEqual(int(round(hi - lo)) + 1, self.n)
        self.assertEqual(self.n, 170)
        self.assertEqual(self.meta["frames"], 170)
        self.assertEqual(bpy.context.scene.render.fps, 30)

    def test_matches_generator(self):
        worst = 0.0
        for k in self.sample:
            for b in (P + "Hips", P + "Head", P + "LeftHand", P + "RightHand", P + "LeftFoot",
                      P + "RightFoot", rig.SPEAR, "weapon_spear_f2", "weapon_spear_b2"):
                worst = max(worst, (self.frames[k][b] - self.gen[k][b]).length)
        self.assertLess(worst, 0.01, f"exported pose drifts from the generator by {worst * 100:.1f} cm")

    def test_ground(self):
        lowest = min(min(h[P + "LeftToeBase"].z, h[P + "RightToeBase"].z) for h in self.frames.values())
        self.assertGreater(lowest, -0.05, "toes go through the floor")
        # she leaves the ground for the jumps and the inverted pole trick
        top = max(h[P + "Hips"].z for h in self.frames.values())
        self.assertGreater(top, 1.4)

    def test_spear_chain_stays_together(self):
        seg = rig.SEG
        for h in self.frames.values():
            for chain in (rig.SPEAR_FWD, rig.SPEAR_BACK):
                for a, b in zip(chain, chain[1:]):
                    self.assertLess(abs((h[b] - h[a]).length - seg), 0.03)

    def test_start_and_end(self):
        first, last = self.frames[0], self.frames[self.n - 1]
        for h in (first, last):
            # standing on both feet
            self.assertLess(h[P + "LeftToeBase"].z, 0.08)
            self.assertLess(h[P + "RightToeBase"].z, 0.08)
        # end pose: spear held at the right hip, blade end down near the floor
        tip_end = min(last["weapon_spear_f2"].z, last["weapon_spear_b2"].z)
        self.assertLess(tip_end, 0.6)
        self.assertLess((last[P + "RightHand"] - last[rig.SPEAR]).length, 0.8)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], "-v"])
