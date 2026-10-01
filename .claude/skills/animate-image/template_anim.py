"""Template: copy this folder to projects/<name>/, put the image as source.png, edit LAYERS / STATE / RENDER.

Run:  cd ~/animations && .venv/bin/python projects/<name>/anim.py [--preview]
      --preview renders at half size for a fast look (sheet only, no encoding)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from animkit import core, timeline as tl, render, encode, preview  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')

# ---------------- LAYERS (built once per process; keep cheap or cache to .npz) ----------------
SRC = core.load(os.path.join(HERE, 'source.png'))      # premultiplied float32 RGBA
H, W = SRC.shape[:2]
XS, YS = core.grid(H, W)

# Example: a body disk stays static, everything outside it flexes around the disk center.
BODY_C, BODY_R = (W / 2, H / 2), min(W, H) * 0.3       # <- measure real values (animkit grid / OpenCV)
BODY_MASK = core.disk(XS, YS, *BODY_C, BODY_R + 1.5)
DIST = np.hypot(XS - BODY_C[0], YS - BODY_C[1])
BEND_W = (0.15 + 0.85 * core.smoothstep(BODY_R, max(W, H) / 2, DIST)).astype(np.float32)
SIDE = np.where(XS < BODY_C[0], 1.0, -1.0).astype(np.float32)

# ---------------- MOTION ----------------
LOOP_MS = 6000
FLAP = [(0, 0), (400, 4.5), (720, -1.8), (1080, 3.2), (1360, -0.9), (1640, 0)]


def state(t):
    return {
        'flap': tl.oscillation(t, FLAP, start=2000),
        'float': tl.breathe(t, LOOP_MS / 2, 3.0),          # period divides loop -> seamless
    }


# ---------------- RENDER ----------------
def render_frame(s):
    wings = core.bend(SRC, BODY_C, s['flap'], BEND_W, SIDE) if abs(s['flap']) > 1e-3 else SRC
    frame = core.over(core.with_mask(SRC, BODY_MASK), wings)
    if abs(s['float']) > 1e-3:
        frame = core.transform(frame, translate=(0, s['float']))
    return frame


if __name__ == '__main__':
    frames = tl.schedule(state, LOOP_MS, step_ms=40)
    fdir = render.render_frames(frames, render_frame, os.path.join(OUT, 'frames'))
    preview.contact_sheet(fdir, os.path.join(OUT, 'sheet.png'), count=6)
    if '--preview' not in sys.argv:
        os.makedirs(OUT, exist_ok=True)
        encode.apng(fdir, os.path.join(OUT, 'anim.png'))
        encode.webp(fdir, os.path.join(OUT, 'anim.webp'))
        preview.html(os.path.join(OUT, 'preview.html'),
                     [os.path.join(OUT, 'anim.png'), os.path.join(OUT, 'anim.webp')], width=720)
