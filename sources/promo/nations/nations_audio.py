"""Soundtrack for nations.py: game sounds, recorded effects and a few synthesized ones, synced to its timeline."""
import os, sys, subprocess
import numpy as np
import pyglet
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import synth as syn                                     # snare, bass, filters
import timeline as P                       # nations and timeline

SR = syn.SR
PROJECT = os.path.abspath(os.environ.get("UPFRONT_ROOT", os.path.join(HERE, "..", "..", "..")))

def load(path, trim=True):
    """Load a sound as stereo float at SR, optionally with its leading silence trimmed."""
    if path.endswith(".wav"):
        sr, x = wavfile.read(path); x = x.astype(np.float32) / 32768
    else:
        src = pyglet.media.load(path, streaming=False)
        f = src.audio_format; sr = f.sample_rate
        x = np.frombuffer(src._data, dtype=np.int16).astype(np.float32).reshape(-1, f.channels) / 32768
    if x.ndim == 1: x = np.stack([x, x], 1)
    if trim:
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

def segment(x, start, dur, fade_in=0.005, fade_out=0.1, peak=None):
    y = x[int(start * SR):int((start + dur) * SR)].copy()
    fi, fo = int(fade_in * SR), int(fade_out * SR)
    y[:fi] *= np.linspace(0, 1, fi)[:, None]; y[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return y / np.max(np.abs(y)) * peak if peak else y

game = lambda n: load(os.path.join(PROJECT, "assets", "sounds", n))
KNOCK, PLAY, SELECT, SWITCH = game("knock.mp3"), game("play_card.mp3"), game("select.mp3"), game("switch.mp3")
LOOP = game("waiting.wav")
LMG = load(os.path.join(HERE, "sounds", "firing_lmg.mp3"), trim=False)
HIT = load(os.path.join(HERE, "sounds", "hit.mp3"))

BURSTS = [segment(LMG, 1.30, 0.42, fade_out=0.12, peak=0.9), segment(LMG, 10.90, 0.40, fade_out=0.12, peak=0.9)]
BOOM = segment(HIT, 0.0, 1.1, fade_out=0.5, peak=1.0)
AT = {"PANZERSCHRECK", "BAZOOKA", "PIAT", "KNEE MORTAR"}

track = np.zeros((int(P.DUR * SR) + SR, 2), dtype=np.float32)
def add(x, t, g=1.0):
    i = int(t * SR); j = min(len(track), i + len(x)); track[i:j] += x[:j - i] * g

def noise(d): return syn.rng.standard_normal(int(d * SR))
def whoosh(d=0.35, lo=600, hi=5000):
    t = syn.ta(d); env = np.sin(np.pi * t / d) ** 2
    return mono(syn.bp(noise(d), lo, hi) * env)

def vehicle(d=0.75, stop=0.3):
    """Engine growl and clanking tracks; the engine drops when the vehicle stops at `stop`."""
    t = syn.ta(d)
    f = np.where(t < stop, 48 + 30 * t / stop, 78 - 30 * np.clip((t - stop) / 0.2, 0, 1))
    ph = np.cumsum(f) / SR
    saw = 2 * (ph % 1) - 1
    eng = syn.lp(saw + 0.4 * np.sign(np.sin(2 * np.pi * ph * 0.5)), 420) * (0.8 + 0.2 * np.sin(2 * np.pi * 9 * t))
    clank_rate = np.where(t < stop, 20, 20 * np.clip(1 - (t - stop) / 0.12, 0, 1))
    cph = np.cumsum(clank_rate) / SR
    ticks = (np.diff(np.floor(cph), prepend=0) > 0).astype(float) * syn.rng.uniform(0.5, 1, len(t))
    clank = syn.bp(np.convolve(ticks, np.exp(-np.arange(400) / 60))[:len(t)] * noise(d), 1800, 6000) * 2.5
    env = np.clip(t / 0.08, 0, 1) * np.clip((d - t) / 0.3, 0, 1)
    x = (eng * 0.9 + clank * 0.6) * env
    return mono(x / np.max(np.abs(x)))

# Drum bed: the game's waiting loop, running through to the end
bed = np.concatenate([LOOP] * 6)[int(P.BED_OFFSET * SR):][:int(P.DUR * SR)]
add(bed, 0.0, 0.4)

# Every nation: the map slides in, badge slams, two weapons, a vehicle rolls in
for n, s in enumerate(P.SEGS):
    L = P.lands(s); picks = P.NATIONS[n][4]
    add(whoosh(0.32, 300, 3500), s - P.WIPE, 0.4)
    add(KNOCK, L[0] - 0.01, 1.0); add(mono(syn.bass(1.2)), L[0], 0.8); add(mono(syn.snare(0.9)), L[0], 0.45)
    for j in range(2):
        add(PLAY, L[1 + j] - 0.02, 0.9); add(mono(syn.snare(0.6)), L[1 + j], 0.3)
        if picks[j][1] in AT: add(BOOM, L[1 + j] + 0.02, 0.75); add(mono(syn.bass(1.0)), L[1 + j], 0.6)
        else: add(BURSTS[(n + j) % 2], L[1 + j] + 0.02, 0.7)
    add(vehicle(), L[3] - 0.3, 0.55)
    for at in [L[3]] + P.echoes(s):
        add(mono(syn.bass(1.5)), at, 0.9); add(KNOCK, at - 0.01, 0.8); add(pitch(PLAY, 0.75), at, 0.7)

# Outro: back to the table, the numbers count up and slam, then the logo
def crash(d=1.4):
    t = syn.ta(d)
    return mono(syn.bp(noise(d), 3000, 12000) * np.exp(-t * 3.2) + syn.bp(noise(d), 600, 3000) * np.exp(-t * 9) * 0.5)

add(whoosh(0.32, 300, 3500), P.OUTRO - P.WIPE, 0.4)
for i, at in enumerate(P.STAT_AT):
    for q in range(6): add(pitch(SELECT, 1.0 + 0.1 * q + 0.15 * i), at - P.COUNT + q * P.COUNT / 6, 0.35)
    add(KNOCK, at - 0.01, 1.0); add(mono(syn.bass(1.3)), at, 0.85); add(mono(syn.snare(1.0)), at, 0.5)
add(whoosh(0.4, 400, 5000), P.LOGO - 0.4, 0.35)
add(KNOCK, P.LOGO - 0.01, 1.0); add(mono(syn.bass(1.6)), P.LOGO, 1.0); add(mono(syn.snare(1.3)), P.LOGO, 0.6)
add(crash(), P.LOGO, 0.35)

track = track[:int(P.DUR * SR)]
fo = int(0.6 * SR); track[-fo:] *= np.linspace(1, 0, fo)[:, None]
mid = track[int(P.SEGS[0] * SR):int(P.OUTRO * SR)]
track = track / np.max(np.abs(mid)) * 0.58                # the nations keep the level of the first version
track = np.tanh(track / 0.95) * 0.95                       # soft limit for the louder hits at the end
print("peak", round(float(np.max(np.abs(track))), 3))
os.makedirs(P.BUILD, exist_ok=True)
wav = os.path.join(P.BUILD, "soundtrack.wav")
wavfile.write(wav, SR, (track * 32767).astype(np.int16))

out = os.path.join(HERE, "up_front_nations_16x9.mp4")
subprocess.run([P.FFMPEG, "-y", "-loglevel", "error", "-i", os.path.join(P.BUILD, "video_silent.mp4"), "-i", wav,
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
print("done", out)
