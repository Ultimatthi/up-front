"""Second promo clip for Up Front: the seven nations with their iconic weapons and vehicles, then the numbers.

Usage (from anywhere):  python sources/promo/nations/nations.py            renders the video
                        python sources/promo/nations/nations.py 3.0 4.2    saves preview frames at these times
Renders the frames with Arcade, then nations_audio.py mixes the soundtrack and writes up_front_nations_16x9.mp4
next to this file. Needs ffmpeg: on PATH, via the FFMPEG environment variable, or Kdenlive's copy.
"""
import math, os, random, shutil, subprocess, sys, tempfile
import numpy as np
import arcade
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.environ.get("UPFRONT_ROOT", os.path.join(HERE, "..", "..", "..")))
CARDS = os.path.join(HERE, "cards")                     # the picked nation cards
MAPS = os.path.join(HERE, "maps")                       # terrain maps of the theatres

W, H = 1920, 1080
FPS = 30
CX, CY = W / 2, H / 2
DUST = (130, 139, 144)

from timeline import *                  # nations, timeline (s)

# ──[ Easing ]──────────────────────────────────────────────────────────────────

def clamp(x): return min(max(x, 0.0), 1.0)
def prog(t, a, b): return clamp((t - a) / (b - a))
def ease_out_back(x, s=1.9):
    x = clamp(x) - 1; return 1 + x * x * ((s + 1) * x + s)
def ease_out_cubic(x): return 1 - (1 - clamp(x)) ** 3
def ease_in_cubic(x): return clamp(x) ** 3
def ease_in_out(x):
    x = clamp(x); return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2
def lerp(a, b, k): return a + (b - a) * k

# ──[ Assets ]──────────────────────────────────────────────────────────────────

os.chdir(PROJECT)
win = arcade.Window(W, H, "nations", visible=False, antialiasing=True)
win.background_color = (50, 59, 64, 255)
FONT = "Arial"

def pil_tex(img, key): return arcade.Texture(img, hash=key)

def rounded(img, r):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), r, fill=255)
    img = img.convert("RGBA"); img.putalpha(m); return img

def nation_card(folder, idx):
    path = os.path.join(CARDS, f"{folder.lower()}_{idx:03d}.jpg")
    img = Image.open(path).convert("RGB").resize((600, 775), Image.LANCZOS)
    return pil_tex(rounded(img, 26), f"card_{folder}_{idx}")

ICON_DIR = os.path.join(HERE, "icons")
def icon_img(key): return Image.open(os.path.join(ICON_DIR, f"{key}.png")).convert("RGB")

def make_badge(key):
    """Square insignia badge like the lobby buttons, without the yellow frame."""
    ic = icon_img(key).resize((300, 300), Image.LANCZOS)
    img = Image.new("RGB", (340, 340), (255, 255, 255)); img.paste(ic, (20, 20))
    return pil_tex(rounded(img, 24), f"badge_{key}")

BOARD = arcade.load_texture("assets/boardelements/board.texture.png")
MAP_TEX = {m: arcade.load_texture(os.path.join(MAPS, f"{m}.jpg")) for m in ("normal", "winter", "desert", "jungle")}
BADGES = [make_badge(key) for _, key, *_ in NATIONS]
NCARDS = [[nation_card(folder, idx) for idx, _ in picks] for _, _, _, folder, picks in NATIONS]

lobby = Image.open("assets/menu/lobby.background.png").convert("RGB").crop((470, 0, 1450, 365))
lum = np.asarray(lobby.convert("L"), dtype=np.float32)
alpha = np.clip((lum - 90) / (230 - 90), 0, 1) * 255
LOGO_TEX = pil_tex(Image.fromarray(np.dstack([np.full_like(lum, 255)] * 3 + [alpha]).astype(np.uint8), "RGBA"), "logo")

# Soft round puff for the vehicles' dust trail
yy, xx = np.mgrid[-1:1:128j, -1:1:128j]
dd = np.clip(np.sqrt(xx ** 2 + yy ** 2), 0, 1)
PUFF = pil_tex(Image.fromarray(np.dstack([np.full_like(dd, 255)] * 3 + [(1 - dd) ** 1.8 * 255]).astype(np.uint8),
                               "RGBA"), "puff")

NC_W, NC_H = 345, 345 * 775 / 600       # nation cards
CARD_X = [880, 1255, 1630]
CARD_Y = 590
HEAD_X, HEAD_Y = 380, 640
LABEL_Y = CARD_Y - NC_H / 2 - 48
STAT_X = [CX - 540, CX, CX + 540]
STAT_Y = 330
LOGO_Y = 760

# ──[ Drawing helpers ]─────────────────────────────────────────────────────────

shake = [0.0, 0.0]

def draw_obj(front, x, y, w, h, angle=0.0, scale=1.0, alpha=255, back=None, flip=0.0, lift=0.0):
    """flip: 0 = front, 1 = back (horizontal card flip). lift raises the shadow."""
    if alpha <= 0 or scale <= 0: return
    x += shake[0]; y += shake[1]
    wf = abs(math.cos(math.pi * flip))
    texture = back if flip >= 0.5 and back is not None else front
    ww, hh = max(w * scale * wf, 1), h * scale
    off = (8 + 30 * lift) * scale
    arcade.draw_texture_rect(texture, arcade.XYWH(x + off, y - off, ww, hh), color=arcade.color.BLACK,
                             angle=angle, alpha=int(alpha * (0.4 - 0.15 * lift)))
    arcade.draw_texture_rect(texture, arcade.XYWH(x, y, ww, hh), angle=angle, alpha=int(alpha))

def stamp(text, x, y, size, t0, t, color=(250, 246, 232), alpha=1.0, shadow=True):
    """Text that stamps in: big and transparent, then snaps to size."""
    if t < t0 or alpha <= 0: return
    k = ease_out_back(prog(t, t0, t0 + 0.18), 2.5)
    a = int(255 * prog(t, t0, t0 + 0.06) * alpha)
    fs = size * (2 - k) if k < 1 else size * (1 + (k - 1) * 0.3)
    x += shake[0]; y += shake[1]
    if shadow:
        arcade.Text(text, x + 5, y - 5, (0, 0, 0, int(a * 0.6)), font_size=fs, font_name=FONT, bold=True,
                    anchor_x="center", anchor_y="center").draw()
    arcade.Text(text, x, y, tuple(color) + (a,), font_size=fs, font_name=FONT, bold=True,
                anchor_x="center", anchor_y="center").draw()

def make_bursts():
    rng = random.Random(4)
    spec = [(LOGO, CX, LOGO_Y, 60, 1.6)] + [(a, STAT_X[i], STAT_Y, 34, 1.0) for i, a in enumerate(STAT_AT)]
    for s in SEGS:
        L = lands(s)
        spec += [(L[0], HEAD_X, HEAD_Y, 26, 0.8), (L[1], CARD_X[0], CARD_Y, 22, 0.7), (L[2], CARD_X[1], CARD_Y, 22, 0.7),
                 (L[3], CARD_X[2], CARD_Y - NC_H / 2, 40, 1.1)]
    bursts = []
    for t0, x, y, n, spread in spec:
        parts = []
        for _ in range(n):
            a = rng.uniform(0, 2 * math.pi); v = rng.uniform(120, 420) * spread
            parts.append((math.cos(a) * v, math.sin(a) * v, rng.uniform(4, 11), rng.randint(0, 40)))
        bursts.append((t0, x, y, parts))
    return bursts
BURSTS = make_bursts()

def draw_dust(t):
    for t0, x, y, parts in BURSTS:
        age = t - t0
        if not 0 <= age < 0.9: continue
        k = age / 0.9
        for vx, vy, r, o in parts:
            d = 1 - (1 - k) ** 2
            c = (DUST[0] + o, DUST[1] + o, DUST[2] + o, int(220 * (1 - k)))
            arcade.draw_circle_filled(x + vx * d * 0.9 + shake[0], y + vy * d * 0.9 + shake[1],
                                      r * (0.5 + 0.5 * (1 - k)), c)

# ──[ Backgrounds ]─────────────────────────────────────────────────────────────

def draw_bg(tex, x0, t_rel, board=False):
    """Full-screen background, its left edge at x0, slowly zooming (Ken Burns)."""
    if board:
        arcade.draw_lrbt_rectangle_filled(x0, x0 + W, 0, H, (50, 59, 64, 255))
        arcade.draw_texture_rect(tex, arcade.XYWH(x0 + CX + shake[0], CY + shake[1], H * 1920 / 1080, H))
        arcade.draw_lrbt_rectangle_filled(x0, x0 + W, 0, H, (30, 36, 40, 90))
        return
    z = 1.08 - 0.06 * clamp(t_rel / (SEG + WIPE))
    w = W * z; h = w * tex.height / tex.width
    arcade.draw_texture_rect(tex, arcade.XYWH(x0 + CX + shake[0] - 25 * t_rel, CY + shake[1], w, max(h, H * z)))
    arcade.draw_lrbt_rectangle_filled(x0, x0 + W, 0, H, (18, 22, 24, 105))
    for i in range(8):                                   # darker on the left, behind the nation's name
        a = int(70 * (1 - i / 8))
        arcade.draw_lrbt_rectangle_filled(x0 + i * 90, x0 + (i + 1) * 90, 0, H, (10, 12, 14, a))

def wipe_x(t, start):
    """Left edge of a background that slides in, landing on `start`."""
    return W * (1 - ease_in_out(prog(t, start - WIPE, start)))

def draw_wipe_shadow(x):
    if 0 < x < W:
        for i in range(10):
            arcade.draw_lrbt_rectangle_filled(x - (i + 1) * 6, x - i * 6, 0, H, (0, 0, 0, int(90 * (1 - i / 10))))

def sweep_dx(t, end):
    """Content slides off to the left while the next background comes in."""
    return -1.25 * W * ease_in_cubic(prog(t, end - WIPE, end))

# ──[ Scenes ]──────────────────────────────────────────────────────────────────

def label_plate(text, x, y, t0, t, alpha=1.0):
    if t < t0: return
    k = ease_out_back(prog(t, t0, t0 + 0.2), 2.2)
    if k <= 0: return
    fs = 27
    tw = len(text) * fs * 0.78 + 40
    x += shake[0]; y += shake[1]
    a = int(255 * alpha * prog(t, t0, t0 + 0.05))
    arcade.draw_lbwh_rectangle_filled(x - tw / 2 * k + 5, y - 26 * k - 5, tw * k, 52 * k, (0, 0, 0, int(a * 0.45)))
    arcade.draw_lbwh_rectangle_filled(x - tw / 2 * k, y - 26 * k, tw * k, 52 * k, (28, 32, 34, a))
    arcade.draw_lbwh_rectangle_filled(x - tw / 2 * k, y + 20 * k, tw * k, 6 * k, (196, 40, 36, a))
    if k > 0.6:
        arcade.Text(text, x, y - 3, (246, 242, 228, a), font_size=fs * k, font_name=FONT, bold=True,
                    anchor_x="center", anchor_y="center").draw()

def draw_trail(t, n, x, y):
    """Dust kicked up behind the vehicle as it drives in."""
    rng = random.Random(100 + n)
    for p in range(26):
        born = SEGS[n] + 0.9 + p * 0.012
        age = t - born
        if not 0 <= age < 0.8: continue
        k = age / 0.8
        px = x + NC_W * 0.35 + rng.uniform(-20, 40) + age * 120
        py = y - NC_H * 0.45 + rng.uniform(-30, 50) + k * 50
        sz = rng.uniform(90, 160) * (0.5 + k)
        arcade.draw_texture_rect(PUFF, arcade.XYWH(px + shake[0], py + shake[1], sz, sz),
                                 color=arcade.types.Color(196, 186, 160), alpha=int(150 * (1 - k)))

def draw_nation(t, n, dx):
    name, key, _, _, picks = NATIONS[n]
    L = lands(SEGS[n])
    # Header: insignia badge and name
    k = ease_out_back(prog(t, L[0] - 0.12, L[0] + 0.1), 2.6)
    if t >= L[0] - 0.12:
        draw_obj(BADGES[n], HEAD_X + dx, HEAD_Y + lerp(80, 0, k), 300, 300, lerp(-14, -3, k), lerp(1.7, 1.0, k),
                 255 * prog(t, L[0] - 0.12, L[0] - 0.06), lift=0.4 * (1 - k))
    stamp(name, HEAD_X + dx, HEAD_Y - 240, 58 if len(name) < 10 else 44, L[0] + 0.08, t)
    # Weapons slam in
    for j in range(2):
        land = L[1 + j]
        if t < land - 0.2: continue
        k = ease_out_cubic(prog(t, land - 0.2, land))
        sc = lerp(1.5, 1.0, ease_out_back(prog(t, land - 0.04, land + 0.14), 3)) if t > land - 0.04 else 1.5
        x = CARD_X[j] + dx; y = lerp(CARD_Y + 260, CARD_Y, k)
        draw_obj(NCARDS[n][j], x, y, NC_W, NC_H, lerp(-25 if j else 22, (-3, 2)[j], k), sc,
                 255 * prog(t, land - 0.2, land - 0.12), lift=1 - k)
        label_plate(picks[j][1], x, LABEL_Y, land + 0.06, t)
    # Vehicle drives in from the right, rocks on its suspension when it stops
    land = L[3]
    if t >= land - 0.3:
        k = ease_out_cubic(prog(t, land - 0.3, land))
        x = lerp(W + 260, CARD_X[2], k) + dx
        rock = math.sin(prog(t, land, land + 0.45) * math.pi * 3) * 4 * (1 - prog(t, land, land + 0.45))
        bob = math.sin(t * 60) * 4 * (1 - k)
        draw_trail(t, n, x, CARD_Y)
        for g in (2, 1):                                  # motion ghosts
            ga = 70 * (1 - k) / g
            if ga > 3: draw_obj(NCARDS[n][2], x + 70 * g * (1 - k) * 2, CARD_Y + bob, NC_W, NC_H, 0, 1, ga)
        bump = max([1 - prog(t, e, e + 0.15) for e in echoes(SEGS[n]) if t >= e] or [0])
        draw_obj(NCARDS[n][2], x, CARD_Y + bob, NC_W, NC_H, rock - 2 * (1 - k), 1.0 + 0.04 * bump)
        label_plate(picks[2][1], x, LABEL_Y, land + 0.1, t)

def draw_stat(t, i):
    """A number counts up, then slams with its word underneath."""
    num, word = STATS[i]
    at = STAT_AT[i]
    if t < at - COUNT: return
    x, y = STAT_X[i] + shake[0], STAT_Y + shake[1]
    k = ease_in_cubic(prog(t, at - COUNT, at)) if t < at else 1.0
    value = str(round(num * (0.15 + 0.85 * k)) if t < at else num)
    pop = ease_out_back(prog(t, at, at + 0.18), 2.6) if t >= at else 0.0
    fs = 150 * (0.8 + 0.2 * pop) if t >= at else 120
    a = int(255 * prog(t, at - COUNT, at - COUNT + 0.06) * (1.0 if t >= at else 0.75))
    arcade.Text(value, x + 6, y - 6, (0, 0, 0, int(a * 0.6)), font_size=fs, font_name=FONT, bold=True,
                anchor_x="center", anchor_y="center").draw()
    arcade.Text(value, x, y, (250, 246, 232, a), font_size=fs, font_name=FONT, bold=True,
                anchor_x="center", anchor_y="center").draw()
    if t >= at:
        w_ = 300 * ease_out_cubic(prog(t, at, at + 0.2))
        arcade.draw_lbwh_rectangle_filled(x - w_ / 2, y - 115, w_, 7, (196, 40, 36, 255))
    stamp(word, STAT_X[i], STAT_Y - 170, 46, at + 0.06, t)

def draw_outro(t, dx):
    for i in range(len(STATS)): draw_stat(t, i)
    if t > LOGO:
        k = ease_out_back(prog(t, LOGO, LOGO + 0.35), 2.2)
        lw = 1000 * lerp(0.5, 1.0, k)
        arcade.draw_texture_rect(LOGO_TEX, arcade.XYWH(CX, LOGO_Y, lw, lw * LOGO_TEX.height / LOGO_TEX.width),
                                 alpha=int(255 * prog(t, LOGO, LOGO + 0.1)))

# ──[ Frame ]───────────────────────────────────────────────────────────────────

def draw_frame(t):
    amp = 0.0
    for s in SEGS:
        p = prog(t, lands(s)[3], lands(s)[3] + 0.25)
        if 0 < p < 1: amp = max(amp, 9 * (1 - p))
        for e in echoes(s):
            p = prog(t, e, e + 0.2)
            if 0 < p < 1: amp = max(amp, 5 * (1 - p))
    for a in STAT_AT + [LOGO]:
        p = prog(t, a, a + 0.2)
        if 0 < p < 1: amp = max(amp, 7 * (1 - p))
    shake[0] = amp * math.sin(t * 95); shake[1] = amp * math.cos(t * 77)

    win.clear()
    # Which scene is on screen, and which one slides in over it
    scenes = [(n, s) for n, s in enumerate(SEGS)] + [("outro", OUTRO)]
    cur = 0
    for i, (_, s) in enumerate(scenes):
        if t >= s - WIPE: cur = i
    prev_i = cur - 1 if cur > 0 and t < scenes[cur][1] else None

    def draw_scene(i, x0, content_dx):
        sid, s = scenes[i]
        if sid == "outro": draw_bg(BOARD, x0, 0, board=True)
        else: draw_bg(MAP_TEX[NATIONS[sid][2]], x0, t - (s - WIPE))
        if sid == "outro": draw_outro(t, content_dx)
        else: draw_nation(t, sid, content_dx)

    if prev_i is not None:
        draw_scene(prev_i, 0, sweep_dx(t, scenes[cur][1]))
        x0 = wipe_x(t, scenes[cur][1])
        draw_wipe_shadow(x0)
        draw_scene(cur, x0, x0)
    else:
        draw_scene(cur, 0, 0)
    draw_dust(t)

    f = prog(t, LOGO, LOGO + 0.18)
    if 0 < f < 1: arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (255, 255, 255, int(160 * (1 - f))))
    for a in (1 - prog(t, 0.0, 0.08), prog(t, DUR - 0.6, DUR)):
        if a > 0: arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (0, 0, 0, int(255 * a)))

# ──[ Render ]──────────────────────────────────────────────────────────────────

def render_video(path):
    n = int(DUR * FPS)
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17",
           "-preset", "slow", path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        draw_frame(i / FPS)
        proc.stdin.write(arcade.get_image(0, 0, W, H).convert("RGB").tobytes())
    proc.stdin.close(); proc.wait()

if __name__ == "__main__":
    os.makedirs(BUILD, exist_ok=True)
    if len(sys.argv) > 1:
        ims = []
        for a in sys.argv[1:]:
            draw_frame(float(a)); ims.append(arcade.get_image(0, 0, W, H).convert("RGB").resize((640, 360)))
        sheet = Image.new("RGB", (640 * min(3, len(ims)), 360 * ((len(ims) + 2) // 3)))
        for i, im in enumerate(ims): sheet.paste(im, ((i % 3) * 640, (i // 3) * 360))
        sheet.save(os.path.join(BUILD, "preview.png")); print("preview saved")
    else:
        render_video(os.path.join(BUILD, "video_silent.mp4"))
        print("video done", DUR)
        subprocess.run([sys.executable, os.path.join(HERE, "nations_audio.py")], check=True)
