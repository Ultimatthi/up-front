"""Small synthesized drum sounds and filters used by the promo soundtrack."""
import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100
rng = np.random.default_rng(21)

def ta(d): return np.arange(int(d * SR)) / SR
def bp(x, lo, hi, o=4): return sosfilt(butter(o, [lo, hi], "bandpass", fs=SR, output="sos"), x)
def lp(x, fc, o=4): return sosfilt(butter(o, fc, "lowpass", fs=SR, output="sos"), x)

def snare(v=1.0):
    t = ta(0.22)
    body = (np.sin(2 * np.pi * 190 * t) + 0.5 * np.sin(2 * np.pi * 330 * t)) * np.exp(-t * 38)
    wires = bp(rng.standard_normal(len(t)), 2000, 9000) * np.exp(-t * 26)
    click = bp(rng.standard_normal(len(t)), 3000, 12000) * np.exp(-t * 400)
    return (0.55 * body + 0.9 * wires + 0.6 * click) * v

def bass(v=1.0):
    t = ta(0.5)
    f = 55 + 40 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * v
