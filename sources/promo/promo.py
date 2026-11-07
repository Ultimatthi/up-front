"""Short, snappy promo clip for the Up Front card game, rendered from game assets.

Usage (from anywhere):  python sources/promo/promo.py
Renders the frames with Arcade, then audio.py mixes the soundtrack and writes up_front_promo_16x9.mp4
next to this file. Needs ffmpeg: on PATH, via the FFMPEG environment variable, or Kdenlive's copy.
"""
import math, os, random, shutil, subprocess, sys, tempfile
import numpy as np
import arcade
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.environ.get("UPFRONT_ROOT", os.path.join(HERE, "..", "..")))
BUILD = os.path.join(tempfile.gettempdir(), "upfront_promo")          # intermediate files
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or r"C:\Program Files\kdenlive\bin\ffmpeg.exe"

W, H = 1920, 1080                                   # 16:9
FPS = 30
CX, CY = W / 2, H / 2
DUST = (130, 139, 144)

# ──[ Timeline (s), on an eighth-note grid at 100 BPM ]─────────────────────────

SLAM = 0.3
DEAL = 1.8
HAND_OUT = 3.9
SQUAD = 4.05
RULER = 5.25                       # distance line between the squads appears
MOVES_AT = [5.7, 6.3, 10.2]        # movement cards land, then the squad moves up
SNIPER = 6.9                       # American sniper card lands
SHOT = 7.2                         # sniper shot: one German unit KIA
CLOSE = 7.5                        # the remaining Germans close ranks
WOODS = 7.8
WALL = 8.7                         # Americans take cover behind a wall
SMOKE = 9.3
FIRE = 11.1
FLIPS = [FIRE + 0.1, FIRE + 0.6]   # on the shots in firing.mp3
SWEEP = 12.6
PILE = 13.5
LOGO = 14.4
DUR = 16.8

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
win = arcade.Window(W, H, "promo", visible=False, antialiasing=True)
win.background_color = (50, 59, 64, 255)
TEX = {}
def tex(path):
    if path not in TEX: TEX[path] = arcade.load_texture(path)
    return TEX[path]

BACK = tex("assets/cards/cardback.png")
def card(cid): return tex(f"assets/cards/{cid}.png")
def unit(uid, side=""): return tex(f"assets/units/{'german' if uid[:2] == 'ge' else 'american'}/{uid}{side}.jpg")
def chit(n): return tex(f"assets/chits/chit.range.{n}.png")
BOARD = tex("assets/boardelements/board.texture.png")

# Logo: crop from the lobby background, white pixels become opaque
lobby = Image.open("assets/menu/lobby.background.png").convert("RGB").crop((470, 0, 1450, 365))
lum = np.asarray(lobby.convert("L"), dtype=np.float32)
alpha = np.clip((lum - 90) / (230 - 90), 0, 1) * 255
LOGO_TEX = arcade.Texture(Image.fromarray(np.dstack([np.full_like(lum, 255)] * 3 + [alpha]).astype(np.uint8), "RGBA"),
                          hash="promo_logo")

# Soft round puff for smoke clouds
yy, xx = np.mgrid[-1:1:256j, -1:1:256j]
d = np.clip(np.sqrt(xx ** 2 + yy ** 2), 0, 1)
noise = np.asarray(Image.effect_noise((256, 256), 60).filter(__import__("PIL.ImageFilter").ImageFilter.GaussianBlur(6)),
                   dtype=np.float32) / 255
puff_a = np.clip((1 - d) ** 1.6 * (0.75 + 0.5 * noise), 0, 1) * 255
PUFF = arcade.Texture(Image.fromarray(np.dstack([np.full_like(d, 255)] * 3 + [puff_a]).astype(np.uint8), "RGBA"),
                      hash="promo_puff")

CARD_W, CARD_H = 170, 170 * 1050 / 675
UNIT_W, UNIT_H = 190, 190 * 775 / 600
SPACING = 215

HAND = ["ac97", "ac54", "ac128", "ac01", "ac04"]   # fire 5, concealed, smoke, movement, woods
MOVES = ["ac01", "ac02", "ac03"]
WOODS_CARD, FIRE_CARD, SMOKE_CARD = "ac04", "ac97", "ac128"
GERMANS = ["ge01", "ge02", "ge03", "ge04"]
AMERICANS = ["us01", "us02", "us03", "us04"]

GE_Y, US_Y = 150, 930
DISCARD = (100, 112)                                # small discard pile, bottom left corner
US_DISCARD = (W - 100, H - 112)                     # the Americans' pile, top right corner
SNIPER_CARD, WALL_CARD = "ac144", "ac119"
KIA_UNIT = 1                                        # ge02 is hit by the sniper
WALL_Y = US_Y - UNIT_H / 2 - 30                     # wall runs along the front of the Americans
STEP = 110                                          # px the squad moves per movement card

def advance(t):
    return sum(STEP * ease_out_back(prog(t, a + 0.15, a + 0.45), 1.6) for a in MOVES_AT)

def gap_center(t):
    return (GE_Y + advance(t) + UNIT_H / 2 + US_Y - UNIT_H / 2) / 2

PLAYS = sorted([(c, a) for c, a in zip(["ac01", "ac02", "ac03"], MOVES_AT)] + [("ac04", WOODS), ("ac128", SMOKE)],
               key=lambda p: p[1])
US_PLAYS = [(SNIPER_CARD, SNIPER), (WALL_CARD, WALL)]

def ge_x(i, t):
    """German unit x: after the sniper hit, the survivors close ranks around the centre."""
    x0 = CX + (i - 1.5) * SPACING
    if i == KIA_UNIT: return x0
    j = i if i < KIA_UNIT else i - 1
    return lerp(x0, CX + (j - 1) * SPACING, ease_in_out(prog(t, CLOSE, CLOSE + 0.3)))

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
                             angle=angle, alpha=int(alpha * (0.35 - 0.15 * lift)))
    arcade.draw_texture_rect(texture, arcade.XYWH(x, y, ww, hh), angle=angle, alpha=int(alpha))

def make_bursts():
    rng = random.Random(4)
    spec = [(SLAM, CX, CY, 40, 1.0), (DEAL, CX, CY, 18, 0.6), (FIRE, CX, US_Y - 30, 50, 1.3), (LOGO, CX, 600, 60, 1.6)]
    spec += [(land, CX, gap_center(land), 22, 0.6) for _, land in PLAYS + US_PLAYS]
    spec += [(SHOT, CX + (KIA_UNIT - 1.5) * SPACING, GE_Y + 2 * STEP, 34, 0.8), (WALL + 0.3, CX, WALL_Y, 30, 0.9)]
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
            dd = 1 - (1 - k) ** 2
            c = (DUST[0] + o, DUST[1] + o, DUST[2] + o, int(220 * (1 - k)))
            arcade.draw_circle_filled(x + vx * dd * 0.9 + shake[0], y + vy * dd * 0.9 + shake[1],
                                      r * (0.5 + 0.5 * (1 - k)), c)

# ──[ Woods: trees seen from above ]────────────────────────────────────────────

def make_trees():
    rng = random.Random(11)
    trees = []
    gaps = [CX + g * SPACING for g in (-2.2, -1.5, -0.5, 0.5, 1.5, 2.2)]   # between and beside the three units
    for gx in gaps:
        for _ in range(3):
            trees.append((gx + rng.uniform(-30, 30), rng.uniform(-170, 170), rng.uniform(42, 62)))
    for _ in range(18):                                     # along the front edge of the squad
        trees.append((rng.uniform(CX - 760, CX + 760), rng.uniform(150, 200), rng.uniform(36, 54)))
    for _ in range(15):                                     # behind the squad
        trees.append((rng.uniform(CX - 760, CX + 760), rng.uniform(-215, -160), rng.uniform(46, 66)))
    out = []
    for x, dy, r in trees:
        blobs = [(0, 0, r * 0.7)]
        n = rng.randint(6, 8)
        for b in range(n):
            a = 2 * math.pi * b / n + rng.uniform(-0.3, 0.3)
            blobs.append((math.cos(a) * r * 0.48, math.sin(a) * r * 0.48, r * rng.uniform(0.48, 0.6)))
        out.append((x, dy, r, blobs, rng.uniform(0, 0.55)))
    out.sort(key=lambda tr: -tr[1])                          # far trees first
    return out
TREES = make_trees()
LEAF = [(24, 44, 26), (36, 70, 34), (56, 100, 46), (92, 140, 66), (140, 180, 98)]
LAYER = [(1.0, 0.0), (0.86, 0.07), (0.66, 0.15), (0.42, 0.24), (0.18, 0.32)]   # (scale, offset to upper left)

def draw_forest_floor(t, base_y):
    if t < WOODS: return
    k = ease_out_cubic(prog(t, WOODS, WOODS + 0.5)) * (1 - ease_in_cubic(prog(t, SWEEP, SWEEP + 0.35)))
    if k <= 0: return
    for i in range(13):
        x = CX - 720 + i * 120
        arcade.draw_texture_rect(PUFF, arcade.XYWH(x, base_y + (20 if i % 2 else -25), 420 * k, 560 * k),
                                 color=arcade.types.Color(22, 40, 24), alpha=int(150 * k))

def draw_trees(t, base_y):
    if t < WOODS: return
    shrink = ease_in_cubic(prog(t, SWEEP, SWEEP + 0.35))
    for x, dy, r, blobs, delay in TREES:
        s = ease_out_back(prog(t, WOODS + 0.1 + delay, WOODS + 0.45 + delay), 2.2) * (1 - shrink)
        if s <= 0: continue
        cx, cy = x + shake[0], base_y + dy + shake[1]
        for bx, by, br in blobs:                                    # cast shadow, lower right
            arcade.draw_circle_filled(cx + (bx + 0.4 * r) * s, cy + (by - 0.4 * r) * s, br * s, (10, 16, 14, 70))
        for col, (k, off) in zip(LEAF, LAYER):
            for bx, by, br in blobs:
                arcade.draw_circle_filled(cx + (bx * k - off * r) * s, cy + (by * k + off * r) * s, br * k * s, col)

# ──[ Smoke: clouds seen from above ]───────────────────────────────────────────

SMOKE_Y = 650                                       # no man's land between the squads

def make_puffs():
    rng = random.Random(23)
    puffs = []
    for i in range(60):
        src = (rng.uniform(CX - 600, CX + 600), SMOKE_Y + rng.uniform(-95, 95))
        a = rng.uniform(0, 2 * math.pi); dist = rng.uniform(20, 130)
        puffs.append((src, (math.cos(a) * dist, math.sin(a) * dist), rng.uniform(200, 340),
                      rng.uniform(0, 0.6), rng.uniform(-40, 40), rng.randint(0, 30)))
    return puffs
PUFFS = make_puffs()

def draw_smoke(t):
    if t < SMOKE: return
    fade = 1 - ease_in_out(prog(t, SWEEP, SWEEP + 0.4))
    for shade in (True, False):                     # soft shadow pass, then the cloud itself
        for (sx, sy), (dx, dy), size, delay, spin, o in PUFFS:
            k = ease_out_cubic(prog(t, SMOKE + 0.1 + delay, SMOKE + 1.0 + delay))
            if k <= 0: continue
            drift = (t - SMOKE) * 5
            x = sx + dx * k + drift + shake[0]; y = sy + dy * k + math.sin(t * 1.3 + o) * 6 + shake[1]
            sz = size * (0.25 + 0.75 * k)
            a = min(1, k * 1.8) * fade
            if shade:
                arcade.draw_texture_rect(PUFF, arcade.XYWH(x + 14, y - 16, sz, sz), color=arcade.types.Color(40, 46, 50),
                                         angle=spin * t, alpha=int(90 * a))
            else:
                c = arcade.types.Color(168 + o, 174 + o, 180 + o)
                arcade.draw_texture_rect(PUFF, arcade.XYWH(x, y, sz, sz), color=c, angle=spin * t, alpha=int(235 * a))

# ──[ Frame ]───────────────────────────────────────────────────────────────────

FAN_N = 12
HAND_ANGLES = [-16, -8, 0, 8, 16]
DECK_TOP = (CX, 800)

def hand_pose(i):
    a = math.radians(HAND_ANGLES[i])
    return CX + 900 * math.sin(a), -560 + 900 * math.cos(a), HAND_ANGLES[i]

def played_card(t, land, j, side="ge"):
    """Thrown in from the player's side, slams in no man's land, then slides to that player's discard pile."""
    k = ease_out_cubic(prog(t, land - 0.3, land))
    mid = (CX, gap_center(land))
    start = (CX - 160, -220) if side == "ge" else (CX + 160, H + 220)
    pile, rots = (DISCARD, (-8, 5, -3, 7, -5)) if side == "ge" else (US_DISCARD, (6, -4))
    x = lerp(start[0], mid[0], k); y = lerp(start[1], mid[1], k)
    ang = lerp(40 if side == "ge" else -40, 0, k)
    sc = lerp(1.35, 1.0, ease_out_back(prog(t, land - 0.05, land + 0.15), 3)) if t > land - 0.05 else 1.35
    k2 = ease_in_out(prog(t, land + 0.3, land + 0.55))
    py_ = pile[1] - j * 3 if side == "us" else pile[1] + j * 3
    x = lerp(x, pile[0] + j * 3, k2); y = lerp(y, py_, k2)
    ang = lerp(ang, rots[j], k2); sc = lerp(sc, 0.42, k2)
    return x, y, ang, sc

RED = (214, 40, 36)

def draw_crosshair(t, x, y):
    """Sniper scope locks onto the target, then flashes on the shot."""
    if not SNIPER + 0.05 <= t < SHOT + 0.2: return
    k = ease_out_cubic(prog(t, SNIPER + 0.05, SHOT - 0.05))
    r = lerp(170, 70, k); rot = lerp(90, 0, k)
    after = prog(t, SHOT, SHOT + 0.2)
    if after > 0: r *= 1 + 0.6 * after
    a = int(255 * min(1, k * 3) * (1 - after))
    col = (255, 255, 255, a) if after > 0 else RED + (a,)
    x += shake[0]; y += shake[1]
    arcade.draw_circle_outline(x, y, r, col, 6)
    arcade.draw_circle_outline(x, y, r * 0.18, col, 4)
    for q in range(4):
        ang = math.radians(rot + 90 * q)
        c, s_ = math.cos(ang), math.sin(ang)
        arcade.draw_line(x + c * r * 0.35, y + s_ * r * 0.35, x + c * r * 1.25, y + s_ * r * 1.25, col, 5)

def draw_kia(t, x, y):
    """Hit unit: red flash, KIA stamp, then it topples off the table."""
    if not SHOT <= t < SHOT + 0.75: return
    fall = ease_in_cubic(prog(t, SHOT + 0.3, SHOT + 0.75))
    tex_ = unit(GERMANS[KIA_UNIT])
    ang = -22 * fall; sc = 1 - 0.3 * fall; alpha = 255 * (1 - fall)
    yy_ = y - 40 * fall
    draw_obj(tex_, x, yy_, UNIT_W, UNIT_H, ang, sc, alpha)
    flash = 1 - prog(t, SHOT, SHOT + 0.35)
    rect = arcade.XYWH(x + shake[0], yy_ + shake[1], UNIT_W * sc, UNIT_H * sc)
    arcade.draw_texture_rect(tex_, rect, color=arcade.types.Color(*RED), angle=ang, alpha=int(150 * flash * (1 - fall)))
    st = ease_out_back(prog(t, SHOT, SHOT + 0.18), 2.5)
    if st > 0 and alpha > 0:
        arcade.Text("KIA", x + shake[0], yy_ + shake[1], RED + (int(alpha),), font_size=54 * (2 - st) * sc,
                    font_name="Arial", bold=True, anchor_x="center", anchor_y="center", rotation=14 - ang).draw()

def make_stones():
    rng = random.Random(31)
    stones = []
    for row, dy in enumerate((-13, 13)):
        x = CX - 470 + (0 if row == 0 else 34)
        while x < CX + 470:
            ln = rng.uniform(50, 78); wd = rng.uniform(21, 26)
            c_ = 7                                               # chamfer
            base = [(-ln / 2 + c_, -wd / 2), (ln / 2 - c_, -wd / 2), (ln / 2, -wd / 2 + c_), (ln / 2, wd / 2 - c_),
                    (ln / 2 - c_, wd / 2), (-ln / 2 + c_, wd / 2), (-ln / 2, wd / 2 - c_), (-ln / 2, -wd / 2 + c_)]
            pts = [(px + rng.uniform(-2.5, 2.5), py + rng.uniform(-2, 2)) for px, py in base]
            g = rng.randint(112, 152)
            stones.append((x + ln / 2, dy + rng.uniform(-2, 2), pts, (g, g + 3, g + 6), rng.uniform(-6, 6)))
            x += ln + rng.uniform(3, 6)
    return stones
STONES = make_stones()

def stone_delay(x): return (x - (CX - 470)) / 940 * 0.28

def draw_wall(t):
    if t < WALL: return
    shrink = ease_in_cubic(prog(t, SWEEP, SWEEP + 0.35))
    for sx, sy, pts, col, rot in STONES:
        d = WALL + 0.03 + stone_delay(sx)
        k = ease_out_back(prog(t, d, d + 0.15), 2.0) * (1 - shrink)
        if k <= 0: continue
        drop = (1 - ease_out_cubic(prog(t, d, d + 0.12))) * 45
        cx_, cy_ = sx + shake[0], WALL_Y + sy + drop + shake[1]
        ca, sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        poly = [(cx_ + (px * ca - py * sa) * k, cy_ + (px * sa + py * ca) * k) for px, py in pts]
        arcade.draw_polygon_filled([(px + 7, py - 8) for px, py in poly], (14, 18, 20, 120))     # shadow
        arcade.draw_polygon_filled(poly, col)
        light = (min(col[0] + 55, 255), min(col[1] + 55, 255), min(col[2] + 55, 255))
        arcade.draw_line_strip([(px - 1.5, py + 1.5) for px, py in poly[4:8]], light, 2.5)       # lit upper edge
        arcade.draw_polygon_outline(poly, (70, 74, 78), 1.5)

def draw_ruler(t, ge_y):
    """Dashed distance line with arrowheads: shrinks as the squads close in."""
    if t < RULER: return
    k = ease_out_back(prog(t, RULER, RULER + 0.3), 1.6)
    fade = 1 - prog(t, SWEEP, SWEEP + 0.3)
    if k <= 0 or fade <= 0: return
    pulse = max([1 - prog(t, a + 0.15, a + 0.6) for a in MOVES_AT if t >= a + 0.15] or [0])
    y0 = ge_y + UNIT_H / 2 + 22; y1 = US_Y - UNIT_H / 2 - 22
    mid = (y0 + y1) / 2; half = (y1 - y0) / 2 * k
    y0, y1 = mid - half, mid + half
    x = CX + shake[0]; y0 += shake[1]; y1 += shake[1]
    col = (255, int(lerp(236, 200, pulse)), int(lerp(200, 90, pulse)), int(235 * fade))
    width = 5 + 4 * pulse
    y = y0 + 26
    while y < y1 - 26:                                   # dashes
        arcade.draw_line(x, y, x, min(y + 16, y1 - 26), col, width)
        y += 28
    for yy_, d in ((y0, -1), (y1, 1)):                   # arrowheads and end caps
        arcade.draw_triangle_filled(x - 17, yy_ - d * 24, x + 17, yy_ - d * 24, x, yy_, col)
        arcade.draw_line(x - 34, yy_ + d * 4, x + 34, yy_ + d * 4, col, width)

def draw_frame(t):
    s = prog(t, FIRE, FIRE + 0.35)
    amp = 18 * (1 - s) if 0 < s < 1 else 0
    shake[0] = amp * math.sin(t * 95); shake[1] = amp * math.cos(t * 77)

    win.clear()
    arcade.draw_texture_rect(BOARD, arcade.XYWH(CX + shake[0], CY + shake[1], H * 1920 / 1080, H))
    arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (30, 36, 40, 90))

    # 1) Deck slams in, fans out, snaps back; 2) a hand is dealt
    if t < 4.2:
        if t < DEAL:
            k = ease_out_back(prog(t, 0.05, SLAM), 2.5)
            dx, dy, ds = CX, CY, lerp(2.2, 1.25, k)
            da = 255 * prog(t, 0.05, 0.15)
        else:
            k = ease_in_out(prog(t, DEAL, DEAL + 0.3))
            dx, dy, ds, da = lerp(CX, DECK_TOP[0], k), lerp(CY, DECK_TOP[1], k), lerp(1.25, 0.75, k), 255
            dy += ease_in_cubic(prog(t, HAND_OUT, HAND_OUT + 0.3)) * 500
        for i in range(FAN_N):
            a = math.radians(-55 + 110 * i / (FAN_N - 1))
            fx, fy, fa = CX + 330 * math.sin(a), 230 + 330 * math.cos(a), math.degrees(a)
            k_out = ease_out_cubic(prog(t, 0.6, 1.0))
            k_in = ease_in_cubic(prog(t, 1.5, 1.78))
            k = k_out * (1 - k_in)
            draw_obj(BACK, lerp(dx, fx, k), lerp(dy + i * 1.2, fy, k), CARD_W * 1.15, CARD_H * 1.15,
                     lerp(0, fa, k), ds, da, lift=0.3 * k)
        for i, cid in enumerate(HAND):
            land = DEAL + 0.3 + 0.3 * i                 # quick flight with a clear landing on the beat
            l0 = land - 0.2
            if t < l0: continue
            k = 1 - (1 - prog(t, l0, land)) ** 2
            hx, hy, ha = hand_pose(i)
            x = lerp(DECK_TOP[0], hx, k); y = lerp(DECK_TOP[1], hy, k) + math.sin(math.pi * k) * 140
            y -= ease_in_cubic(prog(t, HAND_OUT + 0.03 * i, HAND_OUT + 0.25 + 0.03 * i)) * 800
            ang = lerp(0, ha, k) + math.sin(math.pi * k) * 25
            pop = 1 + 0.07 * (1 - ease_out_cubic(prog(t, land, land + 0.12))) if t >= land else 1
            draw_obj(card(cid), x, y, CARD_W, CARD_H, ang, lerp(0.75, 1.25, k) * pop, back=BACK, flip=1 - k,
                     lift=math.sin(math.pi * k))

    objs = []   # (texture, x, y, w, h, angle, scale, back, flip)
    ge_y = GE_Y + advance(t)

    # 3) Squads slide in from both sides
    if t > 4.0:
        for side, ids in (("ge", GERMANS), ("us", AMERICANS)):
            for i, uid in enumerate(ids):
                l0 = SQUAD + 0.15 * (i if side == "ge" else i + 4)
                k = ease_out_back(prog(t, l0, l0 + 0.3), 1.4)
                if side == "ge" and i == KIA_UNIT and t >= SHOT: continue     # drawn by draw_kia
                ux = ge_x(i, t) if side == "ge" else CX + (i - 1.5) * SPACING
                x = lerp(-300 if side == "ge" else W + 300, ux, k)
                flip = 0.0
                if side == "us" and i in (1, 2):
                    f0 = FLIPS[i - 1]
                    flip = ease_in_out(prog(t, f0, f0 + 0.22))
                objs.append((unit(uid), x, ge_y if side == "ge" else US_Y, UNIT_W, UNIT_H, 0.0, 1.0, unit(uid, "b"), flip))

    # Cards played by the Germans: movement, movement, woods, smoke, movement
    plays = []
    for j, (cid, land) in enumerate(PLAYS):
        if t < land - 0.3: continue
        x, y, ang, sc = played_card(t, land, j)
        plays.append((card(cid), x, y, CARD_W, CARD_H, ang, sc, None, 0.0))
    for j, (cid, land) in enumerate(US_PLAYS):
        if t < land - 0.3: continue
        x, y, ang, sc = played_card(t, land, j, "us")
        plays.append((card(cid), x, y, CARD_W, CARD_H, ang, sc, None, 0.0))
    objs += plays

    # Fire card onto the Americans
    if t > FIRE - 0.35:
        k = ease_out_cubic(prog(t, FIRE - 0.35, FIRE))
        x = lerp(CX + 200, CX, k); y = lerp(-250, US_Y - 30, k)
        sc = lerp(1.3, 1.0, ease_out_back(prog(t, FIRE - 0.05, FIRE + 0.15), 3)) if t > FIRE - 0.05 else 1.3
        objs.append((card(FIRE_CARD), x, y, CARD_W * 1.2, CARD_H * 1.2, lerp(35, -6, k), sc, None, 0.0))

    # 5) Sweep everything into one pile
    pile_k = ease_in_cubic(prog(t, PILE, PILE + 0.45))
    swept = []
    for j, (tx, x, y, w, h, ang, sc, back, flip) in enumerate(objs):
        if t > SWEEP:
            k = ease_in_out(prog(t, SWEEP + 0.035 * j, SWEEP + 0.45 + 0.035 * j))
            x, y = lerp(x, CX, k), lerp(y, CY + j * 2, k)
            ang = lerp(ang, (j * 37 % 30) - 15, k)
            sc = lerp(sc, 1.0, k) * (1 - pile_k)
            ang += pile_k * 220
        swept.append((tx, x, y, w, h, ang, sc, back, flip))

    # Draw order: units, trees around the Germans, cards, smoke on top
    n_units = (7 if t >= SHOT else 8) if t > 4.0 else 0
    woods_y = GE_Y + advance(WOODS)
    draw_forest_floor(t, woods_y)
    for o in swept[:n_units]:
        draw_obj(o[0], o[1], o[2], o[3], o[4], o[5], o[6], back=o[7], flip=o[8])
    kia_x, kia_y = ge_x(KIA_UNIT, t), ge_y
    draw_kia(t, kia_x, kia_y)
    draw_trees(t, woods_y)
    draw_wall(t)
    draw_ruler(t, ge_y)
    draw_crosshair(t, kia_x, kia_y)
    draw_smoke(t)
    for o in swept[n_units:]:
        draw_obj(o[0], o[1], o[2], o[3], o[4], o[5], o[6], back=o[7], flip=o[8])
    draw_dust(t)

    for t0, strength in ((FIRE, 120), (LOGO, 160)):
        f = prog(t, t0, t0 + 0.18)
        if 0 < f < 1:
            arcade.draw_lrbt_rectangle_filled(0, W, 0, H, (255, 255, 255, int(strength * (1 - f))))

    if t > LOGO:
        k = ease_out_back(prog(t, LOGO, LOGO + 0.35), 2.2)
        lw = 1000 * lerp(0.5, 1.0, k)
        arcade.draw_texture_rect(LOGO_TEX, arcade.XYWH(CX, 590, lw, lw * LOGO_TEX.height / LOGO_TEX.width),
                                 alpha=int(255 * prog(t, LOGO, LOGO + 0.1)))

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
    render_video(os.path.join(BUILD, "video_silent.mp4"))
    print("video done")
    subprocess.run([sys.executable, os.path.join(HERE, "audio.py")], check=True)
