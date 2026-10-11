"""Keys for the spear acrobatics take, read off references/spear_acrobatics.

Frames are view-A reference frame numbers (-6..163; view B shows frame f at
reference frame f + 170). Screen right in view A = +X, toward camera A = -Y.
A key only sets the channels it lists; see rig.py for the channel meanings.
"""

from keylib import HALF, K, arm, body, fk_leg, free, grip, planted, spear_carry, spear_world  # noqa: F401


# Hip centre in the reference image (pixels, 1280x720), from YOLO pose keypoints
# with obviously wrong detections dropped. The reference character's legs are
# shorter relative to her height than ch_02's, so heights are scaled by leg
# length: floor at y=625, standing hip at y=390 <-> 0.84 m.
HIP_TRACK = {
    0: (659, 456), 3: (686, 427), 5: (691, 406), 6: (687, 405), 7: (675, 424), 8: (661, 460),
    9: (640, 485), 10: (669, 497), 12: (632, 492), 16: (614, 512), 18: (591, 517),
    20: (524, 537), 21: (555, 514), 23: (539, 525), 24: (533, 520), 25: (502, 501),
    26: (538, 421), 27: (569, 385), 28: (584, 355), 29: (601, 344), 30: (595, 350),
    32: (611, 328), 34: (621, 335), 37: (606, 337), 38: (612, 345), 39: (604, 407),
    40: (601, 453), 41: (608, 508), 43: (628, 536), 44: (643, 534), 47: (630, 528),
    49: (615, 520), 51: (612, 515), 53: (578, 514), 55: (567, 508), 57: (580, 506),
    59: (610, 495), 61: (628, 510), 63: (622, 552), 65: (630, 548), 67: (640, 525),
    68: (651, 508), 70: (670, 360), 72: (667, 289), 74: (662, 312), 76: (673, 309),
    78: (630, 307), 86: (607, 502), 88: (549, 458), 90: (514, 462), 92: (499, 453),
    96: (666, 266), 98: (703, 230), 100: (721, 160), 102: (736, 223), 104: (689, 214),
    106: (690, 236), 108: (691, 267), 110: (654, 307), 112: (607, 341), 114: (584, 385),
    116: (545, 495), 118: (512, 520), 122: (476, 530), 126: (476, 528), 129: (490, 510),
    132: (510, 464), 135: (526, 425), 138: (519, 383), 141: (505, 384), 144: (500, 379),
    146: (496, 372), 148: (493, 382), 150: (536, 398), 153: (580, 392), 163: (585, 379),
}
PX_PER_M = 235.0 / 0.84
# While she is on the planted spear camera A pans, so she is placed relative to
# the pole: (dx, dy) from the pole base. View B shows she circles the pole on
# the camera-A side while she swings.
POLE_HIP = {84: (0.11, 0.0), 86: (-0.17, -0.25), 88: (-0.28, -0.35), 90: (-0.33, -0.38),
            92: (-0.33, -0.38), 96: (0.23, 0.0), 98: (0.25, 0.0)}
HIP_Z_FIX = {84: 0.55, 86: 0.52, 88: 0.66, 90: 0.66, 92: 0.68}


def hip_from_ref(x_img, y_img):
    return (x_img - 640.0) / PX_PER_M, (625.0 - y_img) / PX_PER_M


def build(tl):
    # ------------------------------------------------------------- 0-8: start pose,
    # weight onto the left leg, spear taken into both hands overhead and swung down
    # lead-in (only in view B, reference 164-169): same stance, spear low in the
    # right hand pointing at camera A's side, swung up into the left hand
    K(tl, -6,
      body(0.07, 0.0, 0.62, yaw=-35, roll=-10, sb=10, ss=-8, st=5, nb=8, ns=8, nt=-5),
      planted("l", 0.23, -0.05, yaw=-20), planted("r", -0.48, 0.25, yaw=-80, rol=-8),
      arm("r", 60, -55, 0.9), grip("r", 0.10, g=1), spear_carry("r", -20, -40),
      arm("l", 30, -30, 0.8), free("l"))
    K(tl, -3,
      arm("r", 35, 5, 0.85), grip("r", 0.0, g=1), spear_carry("r", -55, -25),
      arm("l", 40, 35, 0.85), free("l"))
    for f in (0, 1):
        K(tl, f,
          body(0.06, 0.0, 0.70, yaw=-35, roll=-10, sb=8, ss=-10, st=10, nb=5, ns=10, nt=-5),
          planted("l", 0.23, -0.05, yaw=-20), planted("r", -0.48, 0.25, yaw=-80, rol=-8),
          arm("l", 50, 62, 0.92), grip("l", 0.0, g=-1), spear_carry("l", -80, 8),
          arm("r", 10, -55, 0.55, curl=0.6), free("r"))
    K(tl, 3,
      body(0.15, 0.0, 0.77, yaw=-15, roll=-5, sb=4, ss=-5, st=5, nb=2, ns=6),
      planted("l", 0.23, -0.05, yaw=-15), planted("r", -0.05, 0.15, yaw=-40, pit=35, z=0.03),
      arm("l", 35, 48, 0.85), grip("l", -0.05, g=-1), spear_carry("l", -90, 5),
      arm("r", 80, 35, 0.9, curl=0.85), free("r"))
    K(tl, 5,
      body(0.17, 0.0, 0.83, yaw=-5, sb=2, ss=-3, nb=0, ns=4),
      planted("l", 0.23, -0.05, yaw=-10), fk_leg("r", -8, 80, an=25),
      arm("l", 25, 45, 0.8), grip("l", -0.35, g=-1),
      arm("r", 20, 75, 0.9), grip("r", -0.62, g=-1),
      spear_world(0.10, -0.12, 1.24, -108, 10, sa=-0.62))
    K(tl, 6,
      body(0.17, 0.0, 0.84, yaw=0, sb=0, nb=-5, ns=8, nt=10),
      planted("l", 0.23, -0.05, yaw=-5), fk_leg("r", 30, 70, an=20),
      arm("l", 30, 70, 0.9), grip("l", -0.70, g=-1),
      arm("r", 20, 70, 0.9), grip("r", -0.50, g=-1),
      spear_world(0.24, -0.10, 1.32, -170, 55, sa=-0.70))
    K(tl, 7,
      body(0.12, 0.0, 0.79, yaw=5, sb=3, nb=0, ns=10, nt=10),
      planted("l", 0.23, -0.05, yaw=0), planted("r", 0.03, 0.02, yaw=5, pit=25, z=0.02),
      grip("l", -0.62, g=-1), grip("r", -0.36, g=-1),
      spear_world(0.22, -0.05, 1.30, 160, 40, sa=-0.62))
    K(tl, 8,
      body(0.07, 0.0, 0.71, yaw=12, sb=4, nb=8, ns=6, nt=5),
      planted("l", 0.18, -0.03, yaw=10), planted("r", 0.0, 0.02, yaw=10),
      grip("l", -0.18, g=1), grip("r", 0.12, g=1),
      spear_world(-0.02, -0.15, 1.17, 138, 25, sa=0.12))
    # ------------------------------------------------------------- 9-17: drop into a
    # deep crouch turning to face right, spear brought down in front, torso folds
    K(tl, 9,
      body(-0.03, 0.0, 0.60, yaw=35, sb=30, ss=0, st=-10, nb=-10, nt=10),
      planted("l", 0.14, -0.02, yaw=30), planted("r", -0.04, 0.03, yaw=30),
      grip("l", -0.18, g=1), grip("r", 0.10, g=1),
      spear_world(0.15, -0.25, 0.92, 140, -15, sa=0.10))
    K(tl, 10,
      body(0.08, 0.0, 0.55, yaw=65, pitch=10, sb=45, st=-10, nb=-20, nt=10),
      planted("l", 0.14, -0.02, yaw=55), planted("r", -0.02, 0.05, yaw=55),
      grip("l", -0.15, g=1), grip("r", 0.08, g=1),
      spear_world(0.45, -0.18, 0.52, 138, -40, sa=0.0))
    K(tl, 12,
      body(-0.02, 0.02, 0.52, yaw=100, pitch=25, sb=55, st=-5, nb=-35, nt=0),
      planted("l", 0.12, 0.0, yaw=80), planted("r", -0.06, 0.06, yaw=80),
      arm("r", -40, 60, 0.9, curl=0.7), free("r"),
      arm("l", 10, -60, 0.8), grip("l", 0.0, g=1),
      spear_carry("l", 180, 45))
    K(tl, 16,
      body(-0.09, 0.03, 0.52, yaw=125, pitch=28, sb=55, st=-5, nb=-35, nt=10),
      planted("l", 0.10, 0.02, yaw=95), planted("r", -0.10, 0.08, yaw=95),
      arm("r", -30, 55, 0.9, curl=0.7), free("r"),
      arm("l", 30, -40, 0.8), grip("l", 0.0, g=1),
      spear_carry("l", 180, 45))
    # ------------------------------------------------------------- 17-25: rise into a
    # kneeling lunge facing the camera, spear spun flat at shoulder height, turn right
    K(tl, 18,
      body(-0.15, 0.03, 0.55, yaw=95, pitch=15, sb=30, st=10, nb=-15, nt=20),
      planted("l", 0.0, 0.0, yaw=60, pit=10), planted("r", -0.20, 0.10, yaw=80, pit=40),
      arm("r", 60, 20, 0.9), grip("r", 0.0, g=1), arm("l", 50, 0, 0.85), free("l"),
      spear_carry("r", 0, 90))
    K(tl, 19,
      body(-0.25, 0.02, 0.52, yaw=45, pitch=10, sb=20, st=5, nb=0, nt=10),
      planted("l", -0.30, -0.10, yaw=30), planted("r", -0.15, 0.20, yaw=40, pit=60, z=0.05),
      arm("r", 10, 15, 0.9), grip("r", 0.0, g=1), arm("l", 60, 10, 0.85), free("l"),
      spear_carry("r", 0, 180))
    K(tl, 20,
      body(-0.33, 0.02, 0.50, yaw=35, pitch=10, sb=15, st=5, nb=5, nt=10),
      planted("l", -0.36, -0.12, yaw=30), planted("r", -0.20, 0.22, yaw=35, pit=65, z=0.06),
      arm("r", -10, 15, 0.9), grip("r", 0.0, g=1),
      spear_carry("r", 0, 320))
    K(tl, 21,
      body(-0.28, 0.02, 0.52, yaw=40, pitch=8, sb=12, st=5, nb=0, nt=15),
      planted("l", -0.36, -0.12, yaw=30), planted("r", -0.20, 0.22, yaw=35, pit=65, z=0.06),
      arm("r", -5, 20, 0.95), grip("r", -0.10, g=1), arm("l", 70, 0, 0.8), free("l"),
      spear_carry("r", 0, 538))
    K(tl, 23,
      body(-0.30, 0.02, 0.54, yaw=75, pitch=8, sb=12, st=0, nb=0, nt=10),
      planted("l", -0.36, -0.12, yaw=50), planted("r", -0.24, 0.20, yaw=60, pit=60, z=0.05),
      arm("r", -20, 25, 0.95), grip("r", -0.10, g=1),
      spear_carry("r", 0, 490))
    K(tl, 24,
      body(-0.36, 0.02, 0.56, yaw=95, pitch=10, sb=15, st=-10, nb=0, nt=10),
      planted("l", -0.30, -0.10, yaw=80, pit=10), planted("r", -0.42, 0.15, yaw=80, pit=40),
      arm("r", -5, 0, 0.95), grip("r", 0.45, g=-1), arm("l", 40, -40, 0.7), free("l"),
      spear_carry("r", 0, 465))
    K(tl, 25,
      body(-0.44, 0.02, 0.62, yaw=130, pitch=10, sb=10, st=-20, nb=0, nt=10),
      planted("l", -0.30, -0.10, yaw=110, pit=40), planted("r", -0.42, 0.15, yaw=110, pit=50),
      arm("r", 30, 0, 0.9), grip("r", 0.45, g=-1),
      spear_carry("r", 10, 450))
    # ------------------------------------------------------------- 26-41: jump with a
    # full left turn, left leg crescent kick over the top, tuck, land on the left foot
    K(tl, 26,
      body(-0.34, 0.03, 0.80, yaw=185, pitch=0, roll=0, sb=0, st=-20, nb=0, nt=10),
      planted("l", -0.30, -0.10, yaw=150, pit=70, z=0.10), fk_leg("r", 40, 90, an=30),
      arm("r", 75, 15, 0.85), grip("r", -0.20, g=-1), spear_carry("r", -90, 55),
      arm("l", 30, -10, 0.8), free("l"))
    K(tl, 27,
      body(-0.24, 0.03, 0.92, yaw=300, pitch=-5, roll=-5, sb=0, st=-20, nb=0, nt=20),
      fk_leg("l", 75, 100, an=30), fk_leg("r", -15, 35, an=40),
      arm("l", 95, -5, 0.9), grip("l", -0.10, g=-1), spear_carry("l", -75, -10),
      arm("r", 10, 10, 0.8, curl=0.7), free("r"))
    K(tl, 28,
      body(-0.19, 0.03, 1.03, yaw=355, pitch=-10, roll=-10, sb=-5, st=-10, nb=5, nt=0),
      fk_leg("l", 45, 40, ab=35, an=30), fk_leg("r", -10, 30, an=40),
      arm("l", 80, 30, 0.9), grip("l", 0.15, g=1), spear_carry("l", -40, 40),
      arm("r", 30, 30, 0.8), free("r"))
    K(tl, 29,
      body(-0.13, 0.03, 1.07, yaw=375, pitch=-20, roll=-20, sb=-10, st=-10, nb=10, nt=-10),
      fk_leg("l", 70, 5, ab=55, an=35), fk_leg("r", 10, 60, an=35),
      arm("r", 70, 30, 0.9), grip("r", -0.45, g=1), arm("l", 80, 30, 0.9, curl=0.6), free("l"),
      spear_carry("r", -17, 0))
    K(tl, 30,
      body(-0.15, 0.03, 1.05, yaw=395, pitch=-30, roll=-15, sb=-10, st=-10, nb=15, nt=-20),
      fk_leg("l", 130, 5, ab=20, an=30), fk_leg("r", 20, 110, an=30),
      arm("r", 85, 15, 0.95), grip("r", -0.55, g=1), arm("l", 80, 20, 0.9, curl=0.6), free("l"),
      spear_carry("r", 22, 0))
    K(tl, 31,
      body(-0.10, 0.03, 1.10, yaw=430, pitch=-15, roll=10, sb=0, st=0, nb=10, nt=-10),
      fk_leg("l", 120, 10, ab=-20, an=30), fk_leg("r", 40, 110, an=30),
      arm("r", 60, 40, 0.9), grip("r", -0.40, g=1),
      spear_carry("r", 63, 0))
    K(tl, 32,
      body(-0.10, 0.03, 1.10, yaw=470, pitch=0, roll=20, sb=10, st=0, nb=0, nt=0),
      fk_leg("l", 95, 15, ab=-10, an=30), fk_leg("r", 60, 120, an=30),
      arm("r", 30, 70, 0.9), grip("r", -0.60, g=1), arm("l", 80, 10, 0.85, curl=0.6), free("l"),
      spear_carry("r", 90, -35))
    K(tl, 34,
      body(-0.09, 0.03, 1.10, yaw=530, pitch=15, roll=5, sb=20, nb=-10, nt=0),
      fk_leg("l", 100, 120, ab=10, an=30), fk_leg("r", 90, 125, ab=10, an=30),
      arm("r", 25, 85, 0.95), grip("r", -0.72, g=1), arm("l", 70, 10, 0.85), free("l"),
      spear_carry("r", 105, -30))
    K(tl, 37,
      body(-0.09, 0.03, 1.07, yaw=560, pitch=15, roll=0, sb=20, nb=-10, nt=0),
      fk_leg("l", 100, 120, ab=10, an=30), fk_leg("r", 90, 125, ab=10, an=30),
      arm("r", 35, 75, 0.95), grip("r", -0.72, g=1), arm("l", 60, 20, 0.85), free("l"),
      spear_carry("r", 130, -25))
    K(tl, 38,
      body(-0.10, 0.02, 1.02, yaw=620, pitch=10, sb=15, nb=-5, nt=0),
      fk_leg("l", 50, 60, an=25), fk_leg("r", 80, 110, an=25),
      arm("r", 40, 60, 0.9), grip("r", -0.40, g=1),
      spear_carry("r", 140, 0))
    K(tl, 39,
      body(-0.12, 0.0, 0.84, yaw=700, pitch=0, sb=5, nb=0, nt=0),
      planted("l", -0.10, -0.03, yaw=690, pit=10), fk_leg("r", 60, 100, ab=10, an=20),
      arm("r", 60, 50, 0.85), grip("r", 0.25, g=1), arm("l", 70, 30, 0.8), grip("l", -0.35, g=1),
      spear_carry("r", 147, 25))
    K(tl, 40,
      body(-0.13, 0.0, 0.67, yaw=715, pitch=10, sb=10, nb=0),
      planted("l", -0.10, -0.03, yaw=700), planted("r", -0.20, 0.05, yaw=700),
      arm("r", 60, 45, 0.85), grip("r", 0.25, g=1), arm("l", 70, 25, 0.8), grip("l", -0.35, g=1),
      spear_carry("r", 150, 25))
    K(tl, 41,
      body(-0.11, 0.0, 0.56, yaw=730, pitch=15, sb=15, nb=0),
      planted("l", -0.10, -0.03, yaw=705), planted("r", -0.22, 0.08, yaw=700, pit=40, z=0.02),
      spear_carry("r", 148, 25))
    build_floor_and_pole(tl)
    build_finish(tl)
    for f, (xi, yi) in HIP_TRACK.items():
        x, z = hip_from_ref(xi, yi)
        if f in POLE_HIP:
            dx, dy = POLE_HIP[f]
            tl.key(f, hx=POLE["x"] + dx, hy=POLE["y"] + dy, hz=HIP_Z_FIX.get(f, z))
        else:
            tl.key(f, hx=x, hz=z)
    tl.key(94, hx=-0.05, hz=1.0)


POLE = dict(x=0.05, y=0.10)   # where the spear is stabbed into the ground (blade first)
POLE_TIP_Z = -0.70             # blade tip below the floor; the top sticks out ~1.3 m


def pole(k=0.0, kd=180.0, lean=0.0, kp=0.0):
    # anchored where the shaft enters the floor, rising straight up from it
    return spear_world(POLE["x"], POLE["y"], 0.0, -90 + lean, 0, sa=HALF + POLE_TIP_Z, k=k, kd=kd,
                       at=1.0, kp=kp)


def build_floor_and_pole(tl):
    # ------------------------------------------------------------- 42-58: spin down into a
    # low side lunge, turn, then prowl along the floor facing left, spear over her back
    K(tl, 42,
      body(-0.08, 0.0, 0.50, yaw=680, pitch=20, sb=20, nb=0),
      planted("l", -0.10, -0.02, yaw=670, pit=20), planted("r", 0.25, 0.05, yaw=650, pit=30, z=0.02),
      arm("r", 60, 40, 0.9), grip("r", 0.1, g=1), spear_carry("r", 170, -30),
      arm("l", 70, 10, 0.85), free("l"))
    K(tl, 43,
      body(-0.04, 0.0, 0.40, yaw=630, pitch=30, sb=20, ss=-10, nb=-20, nt=20),
      planted("l", -0.12, -0.05, yaw=630, ko=10), planted("r", 0.55, 0.05, yaw=630, rol=-20),
      grip("r", -0.30, g=1), arm("l", 30, -60, 1.0), free("l"),
      spear_world(-0.25, 0.0, 0.55, 175, 0, sa=0.0))
    K(tl, 44,
      body(0.01, 0.0, 0.45, yaw=650, pitch=15, sb=10, ss=-10, nb=-10, nt=20),
      planted("l", -0.05, -0.05, yaw=640, ko=10), planted("r", 0.60, 0.05, yaw=640, rol=-20),
      grip("r", -0.40, g=1), arm("l", 30, -60, 1.0), free("l"),
      spear_world(-0.45, -0.05, 0.50, 180, 0, sa=0.0))
    K(tl, 45,
      body(-0.03, 0.0, 0.50, yaw=560, pitch=15, sb=15, nb=0),
      planted("l", -0.05, -0.03, yaw=560, pit=20), planted("r", 0.30, 0.10, yaw=560, pit=30),
      arm("r", 40, 15, 0.95), grip("r", -0.40, g=1), spear_carry("r", 180, 10))
    K(tl, 47,
      body(-0.03, 0.02, 0.38, yaw=450, pitch=35, sb=15, nb=-25),
      planted("l", -0.75, 0.05, yaw=450, rol=-15), planted("r", 0.05, 0.0, yaw=450, ko=10),
      arm("r", 0, -45, 1.0), free("r"), arm("l", 20, 0, 0.8), grip("l", -0.35, g=1),
      spear_world(-0.40, -0.08, 0.48, 180, 0, sa=0.0))
    K(tl, 49,
      body(-0.08, 0.0, 0.48, yaw=360, pitch=25, sb=15, nb=-10),
      planted("l", -0.30, 0.02, yaw=380, pit=20), planted("r", 0.10, 0.05, yaw=350, pit=20),
      arm("r", 30, 30, 0.9), grip("r", -0.35, g=1), arm("l", 30, -60, 1.0), free("l"),
      spear_world(-0.40, -0.10, 0.62, 180, 0, sa=0.0))
    for f, x, z, ang in ((51, -0.12, 0.42, 2), (53, -0.10, 0.40, 0), (55, -0.21, 0.42, -5)):
        K(tl, f,
          body(x, 0.05, z, yaw=270, pitch=65, sb=15, nb=-35, nt=0),
          planted("l", x + 0.30, 0.0, yaw=270, pit=80, z=0.02), planted("r", x + 0.60, 0.12, yaw=270, pit=60),
          arm("l", 0, -25, 1.0, curl=0.2), free("l"),
          arm("r", 40, 40, 0.8), grip("r", -0.25, g=1),
          spear_world(x + 0.15, 0.12, 0.50, ang, 0, sa=-0.25))
    K(tl, 57,
      body(-0.20, 0.05, 0.45, yaw=270, pitch=60, sb=15, nb=-30),
      planted("l", 0.10, 0.0, yaw=270, pit=80, z=0.02), planted("r", 0.22, 0.12, yaw=270, pit=75, z=0.02),
      arm("l", 0, -30, 1.0, curl=0.2), free("l"),
      arm("r", 40, 20, 0.85), grip("r", -0.25, g=1),
      spear_carry("r", -25, -30))
    K(tl, 58,
      arm("r", 40, 25, 0.85), grip("r", -0.20, g=1),
      spear_carry("r", -160, 0))
    # ------------------------------------------------------------- 59-67: squat, spear
    # whirled overhead and round the body
    K(tl, 59,
      body(-0.16, 0.05, 0.52, yaw=280, pitch=55, sb=20, nb=-30),
      planted("l", -0.32, -0.05, yaw=290), planted("r", 0.08, 0.12, yaw=260),
      arm("r", 40, 40, 0.8), grip("r", -0.10, g=1), arm("l", 30, -50, 0.9), free("l"),
      spear_carry("r", 180, 0))
    K(tl, 61,
      body(-0.05, 0.05, 0.48, yaw=320, pitch=40, sb=20, nb=-20),
      planted("l", -0.25, -0.05, yaw=320), planted("r", 0.15, 0.10, yaw=300),
      arm("r", 30, 50, 0.85), grip("r", -0.10, g=1), arm("l", 50, -20, 0.9), free("l"),
      spear_carry("r", 150, 50))
    K(tl, 63,
      body(-0.07, 0.05, 0.40, yaw=180, pitch=25, sb=15, nb=-10),
      planted("l", 0.15, 0.05, yaw=200, ko=20), planted("r", -0.25, 0.05, yaw=160, ko=20),
      arm("r", 10, 80, 0.9), grip("r", -0.60, g=1), arm("l", 60, 0, 0.9), free("l"),
      spear_carry("r", 88, 70))
    K(tl, 65,
      body(0.0, 0.05, 0.42, yaw=225, pitch=25, sb=15, nb=-10),
      planted("l", 0.18, 0.05, yaw=225, ko=20), planted("r", -0.20, 0.05, yaw=210, ko=20),
      arm("r", 60, 20, 0.9), grip("r", -0.20, g=1), arm("l", 60, -20, 0.9), free("l"),
      spear_carry("r", 25, -40))
    K(tl, 66,
      body(0.0, 0.03, 0.40, yaw=300, pitch=25, sb=20, nb=-5),
      arm("r", 50, -10, 0.9), grip("r", -0.10, g=1),
      spear_carry("r", -5, -35))
    K(tl, 67,
      body(0.0, 0.0, 0.52, yaw=360, pitch=20, sb=20, nb=0),
      planted("l", 0.15, 0.0, yaw=360), planted("r", -0.15, 0.05, yaw=350),
      arm("r", 50, -30, 0.9), grip("r", 0.0, g=1), arm("l", 50, -30, 0.9), free("l"),
      spear_carry("r", -150, 0))
    # ------------------------------------------------------------- 68-81: hop, big jump
    # sitting in the air with the spear across the body, point it down
    K(tl, 68,
      body(0.04, 0.0, 0.66, yaw=480, pitch=10, sb=10, nb=0),
      planted("l", 0.15, 0.0, yaw=470, pit=60, z=0.06), planted("r", -0.05, 0.10, yaw=470, pit=50, z=0.04),
      arm("r", 60, -40, 0.95), grip("r", 0.10, g=1), arm("l", 10, 20, 0.85), free("l"),
      spear_carry("r", -160, 10))
    K(tl, 70,
      body(0.10, 0.0, 1.00, yaw=380, pitch=-5, sb=0),
      fk_leg("l", 20, 40, an=40), fk_leg("r", 30, 70, an=40),
      arm("r", 60, 0, 0.85), grip("r", 0.0, g=1), arm("l", 70, 10, 0.85), free("l"),
      spear_carry("r", -140, 35))
    K(tl, 72,
      body(0.09, 0.0, 1.25, yaw=330, pitch=0, sb=5),
      fk_leg("l", 40, 80, an=40), fk_leg("r", 20, 60, an=40),
      arm("l", 70, -30, 0.95), grip("l", 0.0, g=1), arm("r", 40, -10, 0.85), free("r"),
      spear_carry("l", -70, -60))
    for f, z, ang in ((74, 1.20, -20), (76, 1.22, -20), (78, 1.21, -25)):
        K(tl, f,
          body(0.07 if f < 78 else -0.03, 0.0, z, yaw=320, pitch=-5, sb=10, nb=5),
          fk_leg("l", 100, 110, an=30), fk_leg("r", 80, 120, an=30),
          arm("l", 20, -45, 0.75), grip("l", -0.10, g=1), arm("r", 20, -45, 0.7), free("r"),
          spear_carry("l", ang - 10, 35))
    K(tl, 80,
      body(0.05, 0.0, 1.12, yaw=350, pitch=0, sb=5),
      fk_leg("l", 60, 90, an=30), fk_leg("r", 50, 90, an=30),
      arm("l", 70, -20, 0.95), grip("l", -0.70, g=1), arm("r", 30, -30, 0.8), free("r"),
      spear_carry("l", -80, -30))
    K(tl, 81,
      body(0.05, 0.05, 1.05, yaw=380, pitch=5, sb=5),
      fk_leg("l", 50, 70, an=30), fk_leg("r", 40, 70, an=30),
      arm("l", 40, -70, 0.95), grip("l", -0.70, g=1), free("r"),
      spear_carry("l", -90, -30))
    # ------------------------------------------------------------- 82-96: spear stabbed
    # into the ground, she swings round the bending pole and goes over the top
    K(tl, 83,
      body(0.10, 0.05, 0.62, yaw=420, pitch=0, sb=5),
      fk_leg("l", 70, 60, an=20), fk_leg("r", 50, 100, an=20),
      arm("l", 50, 30, 0.9), grip("l", -0.55, g=-1), arm("r", 40, 50, 0.9), grip("r", -0.70, g=-1),
      pole())
    K(tl, 86,
      body(-0.11, -0.15, 0.55, yaw=540, pitch=5, sb=10, nb=-15),
      planted("l", -0.20, -0.12, yaw=540, pit=30), planted("r", 0.02, -0.08, yaw=540, pit=40),
      arm("l", 10, 40, 0.9), grip("l", -0.55, g=-1), arm("r", 10, 55, 0.9), grip("r", -0.72, g=-1),
      pole())
    for f, x, k in ((88, -0.30, 0.55), (90, -0.40, 0.85), (92, -0.39, 0.80)):
        K(tl, f,
          body(x, 0.10, 0.66, yaw=490, pitch=22, roll=0, sb=-5, ss=0, nb=-15),
          fk_leg("l", 60 if f != 90 else 30, 100, an=30), fk_leg("r", 20 if f != 90 else 60, 115, an=30),
          arm("l", 10, 70, 0.95), grip("l", -0.62, g=-1), arm("r", 10, 80, 0.95), grip("r", -0.80, g=-1),
          pole(k=k, kd=180, kp=-60))
    K(tl, 94,
      body(-0.18, 0.12, 1.00, yaw=450, pitch=-95, roll=0, sb=-10, nb=-20),
      fk_leg("l", 30, 40, an=40), fk_leg("r", 50, 80, an=40),
      arm("l", 0, 100, 0.9), grip("l", -0.70, g=-1), arm("r", 0, 110, 0.9), grip("r", -0.82, g=-1),
      pole(k=0.35, kd=180, kp=-40))
    K(tl, 96,
      body(0.09, 0.12, 1.33, yaw=450, pitch=-165, sb=-5, nb=-25),
      fk_leg("l", 0, 30, ab=10, an=40), fk_leg("r", 30, 60, ab=10, an=40),
      arm("l", 0, 140, 0.8), grip("l", -0.72, g=-1), arm("r", 0, 150, 0.8), grip("r", -0.84, g=-1),
      pole(k=0.1))
    # ------------------------------------------------------------- 98-116: pull the spear
    # out upside down, roll back over in the air and come down onto the left foot
    K(tl, 98,
      body(0.21, 0.10, 1.50, yaw=450, pitch=-182, roll=-30, sb=0, nb=-30),
      fk_leg("l", -5, 20, ab=8, an=40), fk_leg("r", 5, 30, ab=8, an=40),
      arm("r", 0, 170, 0.75), grip("r", -0.75, g=-1), arm("l", 0, 170, 0.75), grip("l", -0.55, g=-1),
      spear_carry("r", -95, 35))
    K(tl, 100,
      body(0.27, 0.10, 1.80, yaw=450, pitch=-190, sb=-5, nb=-30),
      fk_leg("l", 30, 90, ab=8, an=40), fk_leg("r", 10, 40, ab=8, an=40),
      arm("r", 0, 160, 0.85), grip("r", -0.25, g=-1), arm("l", 30, 150, 0.8), free("l"),
      spear_carry("r", -62, 0))
    K(tl, 102,
      body(0.32, 0.10, 1.55, yaw=450, pitch=-250, sb=-10, nb=-20),
      fk_leg("l", 80, 90, ab=8, an=40), fk_leg("r", 60, 60, ab=8, an=40),
      arm("r", 30, 120, 0.85), grip("r", -0.70, g=-1), arm("l", 40, 100, 0.8), free("l"),
      spear_carry("r", -50, 50))
    K(tl, 104,
      body(0.16, 0.10, 1.56, yaw=450, pitch=-270, sb=-10, nb=-10),
      fk_leg("l", 120, 60, ab=8, an=40), fk_leg("r", 70, 80, ab=8, an=40),
      arm("r", 40, 60, 0.85), grip("r", -0.70, g=1), arm("l", 70, 20, 0.85), free("l"),
      spear_carry("r", 35, -30))
    K(tl, 106,
      body(0.16, 0.10, 1.48, yaw=450, pitch=-265, sb=0, nb=-10),
      fk_leg("l", 100, 70, ab=8, an=40), fk_leg("r", 60, 90, ab=8, an=40),
      arm("r", 40, 10, 0.85), grip("r", -0.30, g=1),
      spear_carry("r", -40, 0))
    K(tl, 108,
      body(0.17, 0.10, 1.36, yaw=450, pitch=-250, sb=5, nb=-10),
      fk_leg("l", 70, 90, ab=8, an=40), fk_leg("r", 40, 70, ab=8, an=40),
      arm("r", 30, -30, 0.85), grip("r", -0.50, g=1), arm("l", 70, 0, 0.85), free("l"),
      spear_carry("r", -80, 0))
    K(tl, 110,
      body(0.05, 0.10, 1.21, yaw=450, pitch=-250, sb=5, nb=-10),
      fk_leg("l", 60, 100, ab=8, an=40), fk_leg("r", 30, 60, ab=8, an=40),
      arm("r", 20, -40, 0.85), grip("r", -0.60, g=1),
      spear_carry("r", -90, 0))
    K(tl, 112,
      body(-0.11, 0.10, 1.08, yaw=450, pitch=-280, sb=10, nb=-10),
      fk_leg("l", 70, 90, ab=8, an=40), fk_leg("r", 40, 80, ab=8, an=40),
      arm("r", 30, -10, 0.85), grip("r", -0.30, g=1),
      spear_carry("r", -100, 40))
    K(tl, 114,
      body(-0.19, 0.10, 0.92, yaw=450, pitch=-310, sb=10, nb=0),
      fk_leg("l", 30, 50, ab=8, an=30), fk_leg("r", -20, 60, ab=8, an=30),
      arm("r", 40, 40, 0.85), grip("r", -0.20, g=1),
      spear_carry("r", 95, 0))
    K(tl, 116,
      body(-0.32, 0.05, 0.56, yaw=450, pitch=-322, sb=10, nb=-10),
      planted("l", -0.32, 0.0, yaw=450), fk_leg("r", -70, 40, ab=5, an=40),
      arm("r", 30, -30, 0.9), grip("r", -0.25, g=1), arm("l", 10, -40, 0.85), grip("l", -0.50, g=1),
      spear_world(0.95, -0.55, 0.03, -14, -30, sa=HALF))


def build_finish(tl):
    # ------------------------------------------------------------- 118-131: crouch with the
    # blade resting on the floor, then rise
    for f, x, z in ((118, -0.43, 0.43), (122, -0.50, 0.40), (126, -0.52, 0.40), (129, -0.50, 0.44)):
        K(tl, f,
          body(x, 0.05, z, yaw=450, pitch=-325, sb=20, nb=-25, ns=0),
          planted("l", -0.40, -0.05, yaw=445, ko=5), planted("r", -0.55, 0.15, yaw=450, pit=20, ko=5),
          arm("r", 20, -20, 0.95), grip("r", -0.20, g=1), arm("l", 10, -30, 0.9), grip("l", -0.42, g=1),
          spear_world(0.90, -0.55, 0.03, -14, -30, sa=HALF))
    K(tl, 132,
      body(-0.43, 0.05, 0.62, yaw=450, pitch=-335, sb=10, nb=-10),
      planted("l", -0.40, -0.05, yaw=445), planted("r", -0.55, 0.15, yaw=450, pit=30),
      arm("r", 20, -10, 0.95), grip("r", -0.15, g=1), arm("l", 20, -30, 0.9), grip("l", -0.40, g=1),
      spear_world(0.55, -0.40, 0.10, -30, -20, sa=HALF))
    # ------------------------------------------------------------- 134-150: stand, swing
    # the spear behind the back and round, turn to face the camera
    K(tl, 135,
      body(-0.36, 0.05, 0.80, yaw=455, pitch=-350, sb=0, nb=0),
      planted("l", -0.30, -0.05, yaw=450, pit=20), planted("r", -0.50, 0.12, yaw=450, pit=40),
      arm("r", 60, 10, 0.9), grip("r", 0.0, g=1), arm("l", 40, -40, 0.85), free("l"),
      spear_carry("r", -50, 30))
    K(tl, 136, spear_carry("r", -80, -10))
    K(tl, 138,
      body(-0.40, 0.05, 0.84, yaw=495, pitch=-360, sb=0, nb=0),
      planted("l", -0.32, -0.05, yaw=460), planted("r", -0.52, 0.12, yaw=455, pit=20),
      arm("r", 30, 20, 0.95), grip("r", -0.30, g=1), arm("l", 40, -60, 0.85), free("l"),
      spear_carry("r", 40, 0))
    K(tl, 141,
      body(-0.47, 0.05, 0.85, yaw=500, pitch=-360, sb=0),
      planted("l", -0.35, -0.05, yaw=460), planted("r", -0.55, 0.12, yaw=455, pit=10),
      arm("r", 40, 20, 0.95), grip("r", -0.25, g=1), arm("l", 30, -60, 0.85), free("l"),
      spear_carry("r", 155, 20))
    K(tl, 144,
      body(-0.47, 0.05, 0.85, yaw=500, pitch=-360),
      planted("l", -0.35, -0.05, yaw=460, pit=30), planted("r", -0.55, 0.12, yaw=455),
      arm("r", 40, 30, 0.95), grip("r", 0.15, g=1),
      spear_carry("r", 125, 20))
    K(tl, 146,
      body(-0.48, 0.03, 0.85, yaw=330, pitch=-360, nb=0, nt=10),
      planted("l", -0.30, 0.10, yaw=360, pit=40), planted("r", -0.55, 0.0, yaw=320),
      arm("r", -45, 10, 0.75), grip("r", -0.10, g=1), arm("l", 50, -60, 0.85), free("l"),
      spear_carry("r", 95, 35))
    K(tl, 148,
      body(-0.40, 0.0, 0.84, yaw=355, pitch=-360, nb=0, nt=0),
      planted("l", -0.20, 0.0, yaw=370), planted("r", -0.55, 0.0, yaw=345),
      arm("r", 20, -10, 0.8), grip("r", 0.0, g=1),
      spear_carry("r", 60, 30))
    K(tl, 150,
      body(-0.30, 0.0, 0.83, yaw=360, pitch=-360, roll=0, nb=5),
      planted("l", -0.05, 0.0, yaw=370), planted("r", -0.45, 0.0, yaw=350),
      arm("r", 30, -50, 0.9), grip("r", -0.20, g=1), arm("l", 60, -70, 0.9, curl=0.4), free("l"),
      spear_carry("r", -125, -45))
    # ------------------------------------------------------------- 152-163: end pose
    for f, x in ((153, -0.20, ), (163, -0.18)):
        K(tl, f,
          body(x, 0.0, 0.82, yaw=365, pitch=-360, roll=-3, sb=2, ss=3, nb=5, ns=-6, nt=5),
          planted("l", 0.08, 0.0, yaw=375), planted("r", -0.45, 0.0, yaw=345),
          arm("r", 25, -68, 0.95), grip("r", -0.45, g=1), arm("l", 70, -78, 0.92, curl=0.35), free("l"),
          spear_carry("r", -140, -37))
