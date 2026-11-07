"""Soundtrack for promo.py: game sounds, recorded effects and a few synthesized ones, synced to its timeline.

Called by promo.py after the frames are rendered; muxes the result into up_front_promo_16x9.mp4.
"""
import os, sys, subprocess
import numpy as np
import pyglet
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import synth as syn                     # snare, bass, filters
import promo as P                       # timeline, layout and paths
from trees import tree_growth

SR = syn.SR

def load(path):
    """Load a sound as stereo float at SR, with its leading silence trimmed so hits land on their event."""
    if path.endswith(".wav"):
        sr, x = wavfile.read(path); x = x.astype(np.float32) / 32768
    else:
        src = pyglet.media.load(path, streaming=False)
        f = src.audio_format; sr = f.sample_rate
        x = np.frombuffer(src._data, dtype=np.int16).astype(np.float32).reshape(-1, f.channels) / 32768
    if x.ndim == 1: x = np.stack([x, x], 1)
    env = np.abs(x).max(axis=1)
    start = max(int(np.argmax(env > 0.1 * env.max())) - int(0.002 * sr), 0)
    x = x[start:]
    if sr != SR:
        idx = np.arange(0, len(x), sr / SR)
        x = np.stack([np.interp(idx, np.arange(len(x)), x[:, c]) for c in (0, 1)], 1)
    return x

def mono(x): return np.stack([x, x], 1)
def pitch(x, factor):
    idx = np.arange(0, len(x) - 1, factor)
    return np.stack([np.interp(idx, np.arange(len(x)), x[:, c]) for c in (0, 1)], 1)

def segment(x, start, dur, fade_in=0.01, fade_out=0.2, peak=None):
    """Cut a piece out of a recording with short fades; optionally normalize its peak."""
    y = x[int(start * SR):int((start + dur) * SR)].copy()
    fi, fo = int(fade_in * SR), int(fade_out * SR)
    y[:fi] *= np.linspace(0, 1, fi)[:, None]; y[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return y / np.max(np.abs(y)) * peak if peak else y

# Game sounds from the client, recorded effects from sounds/
game = lambda n: load(os.path.join(P.PROJECT, "assets", "sounds", n))
KNOCK, PLAY, SELECT, SWITCH = game("knock.mp3"), game("play_card.mp3"), game("select.mp3"), game("switch.mp3")
LOOP, READY = game("waiting.wav"), game("ready.wav")
fx = lambda n: load(os.path.join(HERE, "sounds", n))
FIRING, SMOKEBOMB, MOVING = fx("firing.mp3"), fx("smokebomb.mp3"), fx("moving.mp3")
SNIPER_SHOT, SLIDE = fx("sniper.mp3"), fx("slide.mp3")

track = np.zeros((int(P.DUR * SR) + SR, 2), dtype=np.float32)
def add(x, t, g=1.0):
    i = int(t * SR); j = min(len(track), i + len(x)); track[i:j] += x[:j - i] * g

def noise(d): return syn.rng.standard_normal(int(d * SR))

def whoosh(d=0.35, lo=600, hi=5000):
    t = syn.ta(d); env = np.sin(np.pi * t / d) ** 2
    return mono(syn.bp(noise(d), lo, hi) * env)

def stone(seed):
    """A stone thudding into place."""
    r = np.random.default_rng(seed); t = syn.ta(0.12)
    knock = syn.bp(r.standard_normal(len(t)), 500, 3500) * np.exp(-t * 70)
    ring = np.sin(2 * np.pi * r.uniform(900, 1500) * t) * np.exp(-t * 90) * 0.4
    thud = syn.lp(r.standard_normal(len(t)), 160) * np.exp(-t * 40) * 1.2
    x = knock + ring + thud
    return mono(x / np.max(np.abs(x)))

# Drum bed: the waiting loop from the game, until the pile vanishes
bed = np.concatenate([LOOP] * 3)[:int((P.PILE - P.SLAM) * SR)]
fade = int(0.04 * SR); bed[-fade:] *= np.linspace(1, 0, fade)[:, None]
add(bed, P.SLAM, 0.42)

# Intro: slam, riffle, snap back, deal
add(mono(syn.bass(1.4)), P.SLAM, 0.9); add(mono(syn.snare(1.2)), P.SLAM, 0.6); add(KNOCK, P.SLAM, 1.0)
for i in range(12): add(PLAY, 0.6 + 0.02 * i, 0.3)
add(whoosh(0.3), 1.5, 0.25)
add(KNOCK, P.DEAL - 0.02, 0.9); add(mono(syn.snare(0.8)), P.DEAL, 0.4)
for i in range(5):
    add(whoosh(0.2, 1500, 7000), P.DEAL + 0.1 + 0.3 * i, 0.12)
    add(pitch(PLAY, 1 + 0.05 * i), P.DEAL + 0.25 + 0.3 * i, 0.9)
add(whoosh(0.3, 400, 3000), P.HAND_OUT, 0.35)

# Squads slide in, distance line appears
for j in range(8): add(pitch(SELECT, 0.9 + 0.04 * j), P.SQUAD + 0.25 + 0.15 * j, 0.7)
add(SWITCH, P.RULER + 0.1, 0.8)

# Every played card: thrown in, slams, slides to its player's discard pile
for cid, land in P.PLAYS + P.US_PLAYS:
    add(whoosh(0.3, 900, 6000), land - 0.3, 0.2)
    add(PLAY, land - 0.02, 1.0); add(mono(syn.snare(0.7)), land, 0.35)
    add(whoosh(0.25, 1500, 7000), land + 0.3, 0.12)

# Movement: running squad and a rising cue as the squads close in
for k, a in enumerate(P.MOVES_AT):
    add(segment(MOVING, (0.4, 1.7, 3.0)[k], 0.8, 0.04, 0.2, peak=0.9), a + 0.05, 1.0)
    add(pitch(SELECT, 1.1 + 0.18 * k), a + 0.2, 0.5)

# Sniper: scope locks on, single shot with its echo, the hit unit falls, the others close ranks
add(pitch(SELECT, 1.7), P.SNIPER + 0.05, 0.45)
add(pitch(SELECT, 2.1), P.SHOT - 0.12, 0.35)
add(segment(SNIPER_SHOT, 0.0, 1.8, 0.002, 0.6, peak=1.0), P.SHOT, 0.95)
add(pitch(PLAY, 0.7), P.SHOT + 0.55, 0.6)
slide_peak = int(np.argmax(np.abs(SLIDE).max(axis=1))) / SR
add(SLIDE, P.CLOSE + 0.15 - slide_peak, 0.8)

# Woods: card slam (the trees themselves are mixed in at the end)
add(mono(syn.bass(0.9)), P.WOODS, 0.6)

# Wall: stones thud into place from left to right
for k, st in enumerate(P.STONES[::2]):
    add(stone(k), P.WALL + 0.03 + P.stone_delay(st[0]) + 0.1, 0.28)
add(mono(syn.bass(0.8)), P.WALL, 0.5)

# Smoke grenade
add(segment(SMOKEBOMB, 0.0, 1.35, 0.002, 0.3, peak=0.95), P.SMOKE - 0.035, 1.0)

# Fire: swoosh, impact, rifle and LMG (cut after the second burst), units flip to pinned on the shots
add(whoosh(0.35, 800, 6000), P.FIRE - 0.35, 0.4)
add(KNOCK, P.FIRE, 0.5)
add(segment(FIRING, 0.0, 1.3, 0.002, 0.2, peak=1.0), P.FIRE, 1.0)
for f in P.FLIPS: add(SWITCH, f, 0.9)

# Sweep into a pile, then the logo with the game's ready sound
for j in range(16): add(pitch(PLAY, 1.25 - 0.025 * j), P.SWEEP + 0.2 + 0.035 * j, 0.4)
add(whoosh(0.5, 300, 4000), P.PILE - 0.1, 0.4)
add(READY, P.LOGO - 0.5, 1.0)           # its accent hit lands with the logo

# Woods: groaning trunk, snapping twigs, unfurling leaves (relative to the loudest moment)
trees = tree_growth(); trees = trees / np.max(np.abs(trees))
i = int(P.WOODS * SR); track[i:i + len(trees)] += trees[:, None] * np.max(np.abs(track)) * 0.36

track = track[:int(P.DUR * SR)]
fo = int(0.6 * SR); track[-fo:] *= np.linspace(1, 0, fo)[:, None]
track = track / np.max(np.abs(track)) * 0.89
wav = os.path.join(P.BUILD, "soundtrack.wav")
wavfile.write(wav, SR, (track * 32767).astype(np.int16))

out = os.path.join(HERE, "up_front_promo_16x9.mp4")
subprocess.run([P.FFMPEG, "-y", "-loglevel", "error", "-i", os.path.join(P.BUILD, "video_silent.mp4"), "-i", wav,
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
print("done", out)
