"""Gnarly tree-growth sound for the woods scene: a groaning trunk, snapping twigs, unfurling leaves."""
import os, sys
import numpy as np
from scipy.signal import butter, sosfilt, lfilter, iirpeak

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import promo as P                                       # tree delays

SR = 44100

def ta(d): return np.arange(int(d * SR)) / SR
def bp(x, lo, hi, o=2): return sosfilt(butter(o, [lo, hi], "bandpass", fs=SR, output="sos"), x)
def lp(x, fc, o=2): return sosfilt(butter(o, fc, "lowpass", fs=SR, output="sos"), x)
def put(buf, x, at, g=1.0):
    i = int(at * SR); j = min(len(buf), i + len(x)); buf[i:j] += x[:j - i] * g

# Moments when single trees spring up (peak of their growth animation), relative to the woods card
TREE_TIMES = sorted(0.1 + tr[4] + 0.2 for tr in P.TREES)

WOOD = [(330, 12, 1.0), (740, 14, 0.7), (1520, 18, 0.45), (2600, 20, 0.25)]   # (Hz, Q, gain)

def resonate(x, modes):
    """Wooden body: a few resonant peaks."""
    return sum(lfilter(*iirpeak(f, q, fs=SR), x) * g for f, q, g in modes)

def creak(d, rate, modes, seed=0, jitter=0.25):
    """Stick-slip friction: an impulse train whose rate follows `rate(t)`, through wood resonances."""
    r = np.random.default_rng(seed); t = ta(d)
    phase = np.cumsum(rate(t) * (1 + jitter * lp(r.standard_normal(len(t)), 30) * 3)) / SR
    ticks = np.diff(np.floor(phase), prepend=0) > 0
    exc = ticks * r.uniform(0.5, 1.0, len(t))
    y = lp(resonate(exc, modes), 2800, 4)              # keep it woody, no fizz
    return y / (np.max(np.abs(y)) + 1e-9)

def crack(seed, bright=1.0):
    """Twig snapping: a sharp, short splintering click."""
    r = np.random.default_rng(seed); t = ta(0.06)
    x = bp(r.standard_normal(len(t)), 900 * bright, 6000 * bright) * np.exp(-t * 120)
    x += bp(r.standard_normal(len(t)), 2500, 9000) * np.exp(-t * 400) * 0.6
    return x / np.max(np.abs(x))

def rustle(d, seed=0):
    r = np.random.default_rng(seed); t = ta(d)
    x = bp(r.standard_normal(len(t)), 2500, 9000) * np.sin(np.pi * t / d) ** 2
    x *= 0.6 + 0.4 * np.clip(lp(r.standard_normal(len(t)), 40) * 6, -1, 1)
    return x / np.max(np.abs(x))

def tree_growth():
    """One long groan rising in pitch like a stretching trunk, a twig snapping on each tree, leaves unfurl."""
    out = np.zeros(int(1.6 * SR))
    d = 1.0
    groan = creak(d, lambda t: 12 * (70 / 12) ** (t / d), WOOD + [(180, 8, 0.6)], seed=21, jitter=0.18)
    env = np.clip(ta(d) / 0.08, 0, 1) * np.clip((d - ta(d)) / 0.25, 0, 1)
    put(out, groan * env, 0.05, 0.6)
    for i, tt in enumerate(TREE_TIMES):
        put(out, crack(300 + i, bright=1.2), tt, 0.16 if i % 3 else 0.25)
    put(out, rustle(0.55, 5), 0.75, 0.2)
    return out
