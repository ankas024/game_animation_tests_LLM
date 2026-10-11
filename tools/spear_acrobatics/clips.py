"""Clip definition: one animation, filmed twice in the reference.

references/spear_acrobatics/ holds the same take from two cameras, back to
back (hard cut between frames 163 and 164; frame 334 is the first frame of the
next reel item and is ignored):

    view A  frames   0-163  low camera in front of her start/end facing
    view B  frames 164-333  high camera behind her left shoulder, looking down

The views are 170 frames apart (B = A + 170) and B starts 6 frames earlier,
so the animation is 170 frames long. Keys are authored in "A frame" numbers
(-6 .. 163); exported animation frame k = A frame k - 6 = B frame 164 + k.
"""
import importlib

import timeline

FPS = 30
NAME = "A_ch02_SpearAcrobatics"
F0, F1 = -6, 163            # timeline range in A frame numbers
B_OFFSET = 170              # reference frame of view B = A frame + 170


def ref_a(f):
    return f if 0 <= f <= 163 else None


def ref_b(f):
    g = f + B_OFFSET
    return g if 164 <= g <= 333 else None


# Comparison cameras (Blender world; her start/end facing is -Y, toward camera A).
#   pos:    fixed camera position
#   follow: aim at the hips path smoothed over `follow` frames, at height aim_z,
#           from `dist` metres back along the view direction
#   az: 0 looks along +Y, -140 looks from behind her left shoulder; el: tilt down
VIEWS = {
    "A": dict(ref=ref_a, cam=dict(lens=50.0, az=0.0, el=8.0, pos=(0.0, -5.85, 1.72))),
    "B": dict(ref=ref_b, cam=dict(lens=50.0, az=-140.0, el=25.0, dist=7.4, aim_z=0.75, follow=10.0)),
}


def build_timeline():
    tl = timeline.Timeline(F0, F1)
    mod = importlib.import_module("keys")
    importlib.reload(mod)
    mod.build(tl)
    # light low-pass: takes the edge off one-frame spikes between dense keys
    tl.default_sigma = 0.7
    for ch in ("sang", "sdep", "sx", "sy", "sz"):
        tl.sigma[ch] = 1.0
    tl.bake()
    return tl
