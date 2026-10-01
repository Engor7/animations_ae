"""Cheap visual checks: one contact sheet instead of many image reads; coordinate grids for measuring by eye;
an HTML page to look at real browser playback (via Playwright MCP) on light/dark/checker backgrounds."""
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BGS = {'checker': None, 'white': (255, 255, 255), 'dark': (22, 22, 30), 'gray': (128, 128, 128)}


def _font(size):
    for p in ('/System/Library/Fonts/Supplemental/Arial.ttf', '/System/Library/Fonts/Helvetica.ttc'):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _bg(size, kind, cell=12):
    w, h = size
    if kind == 'checker':
        yy, xx = np.mgrid[0:h, 0:w]
        v = np.where(((xx // cell) + (yy // cell)) % 2 == 0, 205, 245).astype(np.uint8)
        return Image.fromarray(np.dstack([v, v, v, np.full_like(v, 255)]), 'RGBA')
    return Image.new('RGBA', size, BGS[kind] + (255,))


def contact_sheet(frames_dir, out, times=None, count=8, cols=2, width=540, bg='checker', crop=None):
    """Tile frames at given times (ms) — default: evenly spaced + the most-different frames.
    crop=(x0,y0,x1,y1) in source pixels to zoom on a detail. One Read of this replaces many."""
    meta = json.load(open(os.path.join(frames_dir, 'meta.json')))
    starts = np.cumsum([0] + [m['duration'] for m in meta])
    if times is None:
        idx = list(np.linspace(0, len(meta) - 1, count).astype(int))
    else:
        idx = [int(np.searchsorted(starts, t, side='right') - 1) for t in times]
    tiles = []
    for i in idx:
        im = Image.open(os.path.join(frames_dir, f'f{i:04d}.png')).convert('RGBA')
        if crop:
            im = im.crop(crop)
        h = round(im.height * width / im.width)
        im = im.resize((width, h), Image.LANCZOS)
        tile = _bg(im.size, bg); tile.alpha_composite(im)
        d = ImageDraw.Draw(tile)
        st = meta[i].get('state', {})
        label = f"#{i} t={int(starts[i])}ms " + ' '.join(f'{k}={v:g}' for k, v in list(st.items())[:5])
        d.rectangle([0, 0, width, 16], fill=(0, 0, 0, 160)); d.text((4, 1), label, fill='white', font=_font(12))
        tiles.append(tile)
    rows = (len(tiles) + cols - 1) // cols
    th = tiles[0].height
    sheet = Image.new('RGBA', (cols * width + (cols - 1) * 4, rows * th + (rows - 1) * 4), (60, 60, 60, 255))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * (width + 4), (k // cols) * (th + 4)))
    sheet.save(out)
    print('sheet ->', out, sheet.size)
    return out


def grid(image_path, out, box=None, step=25, zoom=2):
    """Crop + zoom with labeled pixel-coordinate grid lines, to read positions (pivots, centers, contours)
    straight from one image instead of scanning pixels in code."""
    im = Image.open(image_path).convert('RGBA')
    x0, y0, x1, y1 = box or (0, 0, im.width, im.height)
    c = im.crop((x0, y0, x1, y1))
    c = c.resize((c.width * zoom, c.height * zoom), Image.NEAREST if zoom >= 3 else Image.LANCZOS)
    base = _bg(c.size, 'checker'); base.alpha_composite(c)
    d = ImageDraw.Draw(base); f = _font(11)
    for gx in range((x0 // step + 1) * step, x1, step):
        X = (gx - x0) * zoom
        major = gx % (step * 4) == 0
        d.line([(X, 0), (X, base.height)], fill=(0, 200, 255, 230 if major else 110), width=1)
        if major:
            d.text((X + 2, 2), str(gx), fill=(0, 90, 255, 255), font=f)
    for gy in range((y0 // step + 1) * step, y1, step):
        Y = (gy - y0) * zoom
        major = gy % (step * 4) == 0
        d.line([(0, Y), (base.width, Y)], fill=(255, 60, 160, 230 if major else 110), width=1)
        if major:
            d.text((2, Y + 2), str(gy), fill=(220, 0, 120, 255), font=f)
    base.save(out)
    print('grid ->', out, base.size, f'(1 source px = {zoom} px, lines every {step}px, labels every {step * 4}px)')
    return out


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>preview</title>
<style>body{margin:0;font:13px system-ui;background:#444;color:#eee}
.row{display:flex;flex-wrap:wrap;gap:8px;padding:8px}.cell{flex:1 1 30%;min-width:320px}
.bg{padding:12px;display:flex;align-items:center;justify-content:center}
.checker{background:repeating-conic-gradient(#ccc 0 25%,#f5f5f5 0 50%) 0 0/24px 24px}
.white{background:#fff}.dark{background:#16161e}
img,video{max-width:100%;height:auto;display:block}h3{margin:6px 8px}</style></head><body>
__ITEMS__
</body></html>"""


def html(out_html, files, width=None):
    """Page showing each output on checker/white/dark. Open via Playwright:
    python3 -m http.server 8765 --directory <dir>  ->  http://localhost:8765/<page>"""
    base = os.path.dirname(os.path.abspath(out_html))
    items = []
    for f in files:
        rel = os.path.relpath(os.path.abspath(f), base)
        is_video = rel.lower().endswith(('.webm', '.mov', '.mp4'))
        style = f' style="width:{width}px"' if width else ''
        tag = (f'<video src="{rel}" autoplay loop muted playsinline{style}></video>' if is_video
               else f'<img src="{rel}"{style}>')
        cells = ''.join(f'<div class="cell bg {k}">{tag}</div>' for k in ('checker', 'white', 'dark'))
        items.append(f'<h3>{rel} ({os.path.getsize(f) / 1e6:.2f} MB)</h3><div class="row">{cells}</div>')
    open(out_html, 'w').write(PAGE.replace('__ITEMS__', '\n'.join(items)))
    print('html ->', out_html)
    return out_html
