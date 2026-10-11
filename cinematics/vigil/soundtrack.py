"""Synthesised score + sound design for VIGIL (numpy only, no samples).

Usage:  python soundtrack.py renders/contacts.json renders/vigil.wav

Footsteps are placed on the exact heel-strike frames exported by build.py,
everything else is cued to the picture by frame number (24 fps).
"""

import json
import sys
import wave

import numpy as np

SR = 48000
FPS = 24
PICTURE_END = 840          # last rendered frame
TOTAL_FRAMES = 936         # + 4 s title card on black
N = int(TOTAL_FRAMES / FPS * SR)
T = np.arange(N) / SR
rng = np.random.default_rng(1977)


def fr(f):
    return f / FPS


def env(points, t=T):
    """Piecewise-linear envelope from [(seconds, value), ...]."""
    xs, ys = zip(*points)
    return np.interp(t, xs, ys)


def fft_filter(x, response):
    """Zero-phase filter: ``response(freqs_hz) -> gain``."""
    n = len(x)
    size = 1 << (n - 1).bit_length()
    X = np.fft.rfft(x, size)
    f = np.fft.rfftfreq(size, 1 / SR)
    return np.fft.irfft(X * response(f), size)[:n]


def lowpass(fc, order=2):
    return lambda f: 1 / np.sqrt(1 + (f / fc) ** (2 * order))


def highpass(fc, order=2):
    return lambda f: 1 / np.sqrt(1 + (fc / np.maximum(f, 1e-3)) ** (2 * order))


def bandpass(lo, hi, order=2):
    lp, hp = lowpass(hi, order), highpass(lo, order)
    return lambda f: lp(f) * hp(f)


def noise(n=N):
    return rng.standard_normal(n)


def place(dst, src, t0, gain=1.0):
    i = int(t0 * SR)
    if i >= len(dst):
        return
    j = min(len(dst), i + len(src))
    dst[i:j] += src[: j - i] * gain


def note_hz(name):
    names = {"C": -9, "C#": -8, "D": -7, "D#": -6, "Eb": -6, "E": -5, "F": -4, "F#": -3,
             "G": -2, "G#": -1, "Ab": -1, "A": 0, "A#": 1, "Bb": 1, "B": 2}
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((names[pitch] + 12 * (octave - 4)) / 12)


# --------------------------------------------------------------------------- reverb

def cathedral_ir(rt60=4.6, length=5.5):
    n = int(length * SR)
    t = np.arange(n) / SR
    ir = np.zeros((2, n))
    for ch in range(2):
        tail = noise(n) * np.exp(-6.91 * t / rt60)
        # highs die faster in stone rooms
        bright = fft_filter(tail, highpass(2500)) * np.exp(-6.91 * t / (rt60 * 0.35))
        dark = fft_filter(tail, lowpass(2500))
        ir[ch] = (dark + bright) * np.clip(t / 0.03, 0, 1)
        for d, g in ((0.017, 0.5), (0.029, 0.4), (0.041, 0.35), (0.063, 0.3), (0.087, 0.22)):
            ir[ch, int((d + ch * 0.003) * SR)] += g * 8
    ir /= np.max(np.abs(ir))
    return ir


def convolve(x, ir):
    n = len(x) + ir.shape[1]
    size = 1 << (n - 1).bit_length()
    X = np.fft.rfft(x, size)
    out = np.stack([np.fft.irfft(X * np.fft.rfft(ir[c], size), size)[: len(x)] for c in range(2)])
    return out / np.sqrt(np.sum(ir ** 2) / 2) * 0.12


# --------------------------------------------------------------------------- layers

def wind():
    """Night wind through the open door; fades as she walks deeper in."""
    w = fft_filter(noise(), bandpass(220, 1200, 1))
    gust = 0.6 + 0.4 * np.sin(2 * np.pi * T / 9.0 + 1.0) * np.sin(2 * np.pi * T / 4.1)
    whistle = fft_filter(noise(), bandpass(900, 1400, 4)) * (0.5 + 0.5 * np.sin(2 * np.pi * T / 6.3)) * 0.35
    level = env([(0, 0.0), (0.4, 1.0), (fr(130), 0.85), (fr(350), 0.35), (fr(840), 0.25), (39, 0.0)])
    return (w * gust + whistle) * level * 0.05


def drone():
    """Low D drone with slow beating, the bed of the whole piece."""
    out = np.zeros(N)
    for hz, amp, det, ph0 in ((note_hz("D2"), 1.0, 0.045, 0.3), (note_hz("A2"), 0.55, 0.071, 1.9),
                              (note_hz("D3"), 0.35, 0.058, 4.1)):
        for s, extra in ((-1, 0.0), (1, 2.2), (0, 1.1)):
            ph = 2 * np.pi * (hz + s * det) * T + ph0 + extra
            out += amp * (np.sin(ph) + 0.3 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph))
    out *= 0.8 + 0.2 * np.sin(2 * np.pi * T / 11.0)
    out = fft_filter(out, lowpass(400))
    level = env([(0, 0), (3.5, 0.6), (fr(351), 0.75), (fr(470), 1.0), (fr(650), 0.55), (fr(742), 0.8),
                 (fr(840), 0.6), (fr(850), 0.0), (39, 0.0)])
    return out * level * 0.035


def choir_voice(f0, dur, vowel=(750, 1150, 2600), voices=5, seed=0):
    r = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    nyq = SR / 2
    for v in range(voices):
        cents = r.uniform(-9, 9)
        vib_rate, vib_depth = r.uniform(4.6, 5.6), r.uniform(0.002, 0.004)
        inst = f0 * 2 ** (cents / 1200) * (1 + vib_depth * np.sin(2 * np.pi * vib_rate * t + r.uniform(0, 6)))
        phase = 2 * np.pi * np.cumsum(inst) / SR
        for k in range(1, 28):
            fk = f0 * k
            if fk > nyq * 0.9:
                break
            g = sum(a * np.exp(-0.5 * ((fk - F) / w) ** 2) for F, w, a in
                    ((vowel[0], 110, 1.0), (vowel[1], 140, 0.6), (vowel[2], 260, 0.25)))
            g = (g + 0.04) / k ** 0.6
            out += g * np.sin(k * phase + r.uniform(0, 6))
    # breath
    out += fft_filter(r.standard_normal(n), bandpass(vowel[0], vowel[1] * 1.5)) * 0.02
    return out / voices


def chord(names, t0, t1, fade_in=1.6, fade_out=2.0, gain=1.0, vowel=(750, 1150, 2600), seed=0):
    dur = t1 - t0 + fade_out
    n = int(dur * SR)
    t = np.arange(n) / SR
    e = np.clip(t / fade_in, 0, 1) ** 1.5 * np.clip((dur - t) / fade_out, 0, 1)
    s = sum(choir_voice(note_hz(nm), dur, vowel, seed=seed + i) for i, nm in enumerate(names))
    out = np.zeros(N)
    place(out, s * e, t0, gain)
    return out


def choir():
    c = np.zeros(N)
    c += chord(["D3", "A3", "F4", "E5"], fr(425), fr(520), fade_in=2.5, gain=0.5, seed=10)
    c += chord(["Bb2", "F3", "D4", "A4"], fr(516), fr(570), fade_in=1.2, gain=0.55, seed=20)
    c += chord(["F3", "C4", "A4", "E5"], fr(566), fr(648), fade_in=1.0, gain=0.6, seed=30,
               vowel=(650, 1080, 2650))
    # after the catch: hushed "oo", then a Picardy D major as she looks up
    c += chord(["D3", "A3", "D4"], fr(660), fr(735), fade_in=2.0, gain=0.32, seed=40, vowel=(400, 800, 2400))
    c += chord(["D3", "A3", "F#4", "A4", "D5"], fr(738), fr(846), fade_in=2.2, fade_out=3.0, gain=0.5,
               seed=50)
    return fft_filter(c, lowpass(5200)) * 0.05


def footsteps(contacts):
    out = np.zeros(N)
    for c in contacts:
        f, scale = c["frame"], c["scale"]
        g = 0.35 + 0.65 * min(1.0, scale)
        r = np.random.default_rng(int(f * 10))
        # heel: hard click of a boot heel on stone
        n = int(0.05 * SR)
        t = np.arange(n) / SR
        click = fft_filter(r.standard_normal(n), bandpass(1800, 7000)) * np.exp(-t / 0.006)
        body = np.sin(2 * np.pi * r.uniform(95, 130) * t) * np.exp(-t / 0.02) * 0.7
        thud = fft_filter(r.standard_normal(n), lowpass(500)) * np.exp(-t / 0.015) * 0.6
        place(out, click * 1.0 + body + thud, fr(f), g)
        # sole slaps flat a few frames later, then a soft scuff
        n2 = int(0.09 * SR)
        t2 = np.arange(n2) / SR
        slap = fft_filter(r.standard_normal(n2), bandpass(400, 3000)) * np.exp(-t2 / 0.018) * 0.35
        place(out, slap, fr(f + 3.0), g)
    # louder in the boots close-up, distant in the wide
    level = env([(0, 0.7), (fr(130), 0.75), (fr(131), 1.25), (fr(200), 1.25), (fr(201), 0.85),
                 (fr(350), 0.85), (fr(351), 0.6), (39, 0.6)])
    return out * level * 0.16


def candles():
    """A faint crackle of wicks, closer in the quiet second half."""
    out = np.zeros(N)
    r = np.random.default_rng(5)
    for t0 in np.cumsum(r.exponential(0.18, 400)):
        if t0 > 39:
            break
        n = int(0.004 * SR)
        place(out, r.standard_normal(n) * np.exp(-np.arange(n) / (0.001 * SR)), t0, r.uniform(0.2, 1))
    out = fft_filter(out, bandpass(2000, 9000))
    return out * env([(0, 0.2), (fr(400), 0.5), (fr(840), 0.6), (fr(850), 0)]) * 0.02


def shimmer():
    """Glassy partials building as she reaches, a reverse swell into the catch."""
    out = np.zeros(N)
    t0, t1 = fr(560), fr(650)
    base = [note_hz(n) for n in ("D6", "A6", "E6", "F6", "C7", "A5")]
    seg = (T >= t0) & (T <= t1 + 0.05)
    tt = T[seg] - t0
    s = np.zeros(seg.sum())
    for i, hz in enumerate(base):
        trem = 0.5 + 0.5 * np.sin(2 * np.pi * (6 + i * 1.7) * tt + i)
        s += np.sin(2 * np.pi * hz * tt + i) * trem
    rise = (tt / (t1 - t0)) ** 3
    out[seg] = s * rise
    # reverse cymbal: noise swelling into the catch
    rev = fft_filter(noise(), highpass(3000)) * np.clip((T - fr(600)) / (fr(650) - fr(600)), 0, 1) ** 4
    rev[T > fr(650)] = 0
    return out * 0.012 + rev * 0.03


def catch_hit():
    """The light closes in her hand: soft low 'whump' + bright chime."""
    out = np.zeros(N)
    n = int(2.5 * SR)
    t = np.arange(n) / SR
    sweep = 2 * np.pi * np.cumsum(70 * np.exp(-t / 0.4) + 38) / SR
    whump = np.sin(sweep) * np.exp(-t / 0.5)
    air = fft_filter(noise(n), lowpass(900)) * np.exp(-t / 0.12) * 0.5
    place(out, whump + air, fr(651), 0.5)
    for hz, g, d in ((note_hz("D6"), 0.6, 2.4), (note_hz("A6"), 0.4, 1.9), (note_hz("F#7"), 0.25, 1.4),
                     (note_hz("D7") * 1.003, 0.3, 2.0)):
        place(out, np.sin(2 * np.pi * hz * t) * np.exp(-t / d) * np.clip(t / 0.004, 0, 1), fr(651), g * 0.12)
    return out


def glow_hum():
    """Warm, breathing tone of the light in her fist."""
    hz = note_hz("D4")
    s = (np.sin(2 * np.pi * hz * T) + 0.5 * np.sin(2 * np.pi * hz * 1.5 * T + 1)
         + 0.25 * np.sin(2 * np.pi * hz * 2.003 * T + 2))
    trem = 0.75 + 0.25 * np.sin(2 * np.pi * 0.42 * T)
    return s * trem * env([(fr(645), 0), (fr(680), 1), (fr(830), 0.8), (fr(845), 0)]) * 0.008


def heartbeat():
    out = np.zeros(N)
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    beat = np.sin(2 * np.pi * 48 * t) * np.exp(-t / 0.07)
    beat = fft_filter(beat, lowpass(120))
    t0 = fr(690)
    k = 0
    while t0 < fr(800):
        g = 0.7 if k < 2 else 0.5
        place(out, beat, t0, g)
        place(out, beat, t0 + 0.28, g * 0.6)
        t0 += 1.15
        k += 1
    return out * 0.09


def title_hit():
    out = np.zeros(N)
    n = int(6 * SR)
    t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(35 + 40 * np.exp(-t / 0.08)) / SR) * np.exp(-t / 1.6)
    boom += fft_filter(noise(n), lowpass(200)) * np.exp(-t / 0.4) * 0.6
    place(out, boom, fr(846), 0.55)
    bell = sum(np.sin(2 * np.pi * note_hz("D5") * m * t) * a * np.exp(-t / dd)
               for m, a, dd in ((1, 1.0, 3.5), (2.76, 0.4, 2.0), (5.4, 0.25, 1.2), (8.93, 0.12, 0.7)))
    place(out, bell * np.clip(t / 0.003, 0, 1), fr(862), 0.06)
    return out


# --------------------------------------------------------------------------- mix

def level(sig, db, kind="peak"):
    """Scale a layer so its peak (or RMS over its active part) sits at ``db`` dBFS."""
    a = np.abs(sig)
    if kind == "peak":
        ref = a.max()
    else:
        active = a > a.max() * 0.02
        ref = np.sqrt(np.mean(sig[active] ** 2))
    return sig * (10 ** (db / 20) / max(ref, 1e-9))


def main(contacts_path, out_path):
    contacts = json.load(open(contacts_path))
    ir = cathedral_ir()
    dry = np.zeros((2, N))
    wet_send = np.zeros(N)

    def add(sig, pan=0.0, wet=0.3, dry_gain=1.0):
        nonlocal wet_send
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        dry[0] += sig * l * dry_gain * 1.41
        dry[1] += sig * r * dry_gain * 1.41
        wet_send += sig * wet

    add(level(wind(), -38, "rms"), pan=0.0, wet=0.2)
    add(level(fft_filter(wind(), lowpass(700)), -42, "rms"), pan=-0.4, wet=0.1)
    add(level(drone(), -33, "rms"), wet=0.25)
    add(level(choir(), -15), wet=0.75, dry_gain=0.7)
    add(level(footsteps(contacts), -13), wet=0.45)
    add(level(candles(), -34), pan=0.3, wet=0.2)
    add(level(shimmer(), -20), wet=0.6)
    add(level(catch_hit(), -9), wet=0.55)
    add(level(glow_hum(), -32, "rms"), wet=0.35)
    add(level(heartbeat(), -17), wet=0.15)
    add(level(title_hit(), -6), wet=0.6)
    mix = dry + convolve(wet_send, ir)
    # gentle master: fade, soft clip, normalise
    master = env([(0, 0), (0.05, 1), (TOTAL_FRAMES / FPS - 0.6, 1), (TOTAL_FRAMES / FPS, 0)])
    mix *= master
    # master: bring the body of the piece up to ~-20 dBFS RMS, soft-limit the hits
    rms = np.sqrt(np.mean(mix ** 2))
    mix *= 10 ** (-20 / 20) / rms
    mix = np.tanh(mix * 1.1) / 1.1
    mix *= min(1.0, 0.94 / np.max(np.abs(mix)))
    pcm = (mix.T * 32767).astype(np.int16)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", out_path, f"{N / SR:.1f}s", "rms dBFS", 20 * np.log10(np.sqrt(np.mean(mix ** 2))))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
