"""Timeline and nation picks of the nations promo, shared by nations.py and nations_audio.py."""
import os, shutil, tempfile

FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or r"C:\Program Files\kdenlive\bin\ffmpeg.exe"
BUILD = os.path.join(tempfile.gettempdir(), "upfront_nations")          # intermediate files

# ──[ Nations: (name, insignia, map, folder, [(card index, label) x3]) ]────────
# Folder and index name the card scans in cards/ (<folder>_<index>.jpg); the Soviet cards belong to the British set.

NATIONS = [
    ("GERMANY", "german", "normal", "Germans", [(28, "STG 44"), (20, "PANZERSCHRECK"), (70, "TIGER")]),
    ("SOVIET UNION", "russian", "winter", "British", [(116, "PPSH-41"), (82, "DP 28"), (148, "T-34/85")]),
    ("GREAT BRITAIN", "british", "desert", "British", [(4, "BREN"), (20, "PIAT"), (72, "CHURCHILL")]),
    ("UNITED STATES", "american", "normal", "Americans", [(0, "THOMPSON"), (24, "BAZOOKA"), (70, "SHERMAN")]),
    ("JAPAN", "japanese", "jungle", "Japanese", [(2, "NAMBU"), (40, "KNEE MORTAR"), (58, "CHI-HA")]),
    ("ITALY", "italian", "desert", "Italians", [(0, "BERETTA M38"), (4, "BREDA 30"), (64, "M13/40")]),
    ("FRANCE", "french", "normal", "French", [(4, "FM 24/29"), (24, "HOTCHKISS"), (60, "CHAR B1")]),
]

# ──[ Timeline (s), on an eighth-note grid at 100 BPM ]─────────────────────────

SEG = 2.4                           # one nation: a full bar, the last card stays a little longer
SEGS = [round(0.3 + SEG * k, 2) for k in range(len(NATIONS))]
OUTRO = round(SEGS[-1] + SEG, 2)    # back to the table
STATS = [(7, "NATIONS"), (70, "WEAPON TYPES"), (68, "AFV")]
STAT_AT = [round(OUTRO + 0.3 + 0.6 * i, 2) for i in range(len(STATS))]   # each count slams on a quarter note
COUNT = 0.36                        # numbers count up before they slam
LOGO = round(STAT_AT[-1] + 0.9, 2)
DUR = LOGO + 2.4
BED_OFFSET = 2.4                    # drum loop phase (s) at t = 0, as in the first version
WIPE = 0.3                          # map slides in, the previous nation is swept off

def lands(s):
    """Beats inside a nation: header, weapon, weapon, vehicle."""
    return [s, s + 0.3, s + 0.6, s + 1.2]

def echoes(s):
    """The vehicle's heavy beat repeats twice while the cards stay, leading into the next bar."""
    return [round(s + 1.8, 2), round(s + 2.1, 2)]

