"""Encoders with built-in verification. Input: frames_dir with f0000.png.. + meta.json.

Quality notes (edges!):
- APNG / WebP / WebM / MOV keep 8-bit alpha -> smooth anti-aliased edges. Prefer these.
- GIF has 1-bit alpha -> jagged edges on any background. Fallback only.
- MP4 has no alpha: flatten onto the exact page background color.
"""
import json
import os
import re
import subprocess

import numpy as np
from PIL import Image

from . import core


def _frames(frames_dir):
    meta = json.load(open(os.path.join(frames_dir, 'meta.json')))
    files = [os.path.join(frames_dir, f'f{i:04d}.png') for i in range(len(meta))]
    return files, [m['duration'] for m in meta]


def scaled(frames_dir, width=None):
    """Premultiplied Lanczos/area downscale of a frame set (cached next to it)."""
    if not width:
        return frames_dir
    files, _ = _frames(frames_dir)
    w0, h0 = Image.open(files[0]).size
    if width == w0:
        return frames_dir
    size = (int(width), round(h0 * width / w0))
    out = f'{frames_dir.rstrip("/")}_{size[0]}w'
    os.makedirs(out, exist_ok=True)
    for i, f in enumerate(files):
        dst = os.path.join(out, os.path.basename(f))
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(f):
            core.save(dst, core.resize(core.load(f), size))
    json.dump(json.load(open(os.path.join(frames_dir, 'meta.json'))), open(os.path.join(out, 'meta.json'), 'w'))
    return out


def _concat_list(frames_dir):
    files, durs = _frames(frames_dir)
    path = os.path.join(frames_dir, 'concat.txt')
    with open(path, 'w') as fh:
        for f, d in zip(files, durs):
            fh.write(f"file '{os.path.abspath(f)}'\nduration {d / 1000:.3f}\n")
        fh.write(f"file '{os.path.abspath(files[-1])}'\n")
    return path


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'{cmd[0]} failed:\n{r.stderr[-2000:]}')
    return r


def _size(path):
    return f'{os.path.getsize(path) / 1e6:.2f} MB'


# ---------------- encoders ----------------
def apng(frames_dir, out, width=None, compress_level=9):
    """Lossless animated PNG, full 8-bit alpha. Largest files, best edges, plays in all modern browsers as <img>."""
    d = scaled(frames_dir, width)
    files, durs = _frames(d)
    first = Image.open(files[0]).convert('RGBA')
    rest = [Image.open(f).convert('RGBA') for f in files[1:]]  # must be a list (generator -> 1 frame)
    first.save(out, save_all=True, append_images=rest, duration=durs, loop=0,
               disposal=0, blend=0, compress_level=compress_level)
    return verify(out, d)


def webp(frames_dir, out, width=None, quality=90, lossless=False):
    """Animated WebP, 8-bit alpha, much smaller than APNG. quality 85-92 is visually clean."""
    d = scaled(frames_dir, width)
    files, durs = _frames(d)
    cmd = ['img2webp', '-loop', '0', '-m', '4']
    cmd += ['-lossless'] if lossless else ['-lossy', '-q', str(quality), '-mixed']
    for f, t in zip(files, durs):
        cmd += ['-d', str(t), f]
    _run(cmd + ['-o', out])
    return verify(out, d)


def webm(frames_dir, out, width=None, fps=30, crf=28):
    """VP9 + alpha. Chrome/Firefox/Edge keep transparency; Safari does NOT (pair with mov())."""
    d = scaled(frames_dir, width)
    _run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', _concat_list(d),
          '-vf', f'fps={fps},crop=trunc(iw/2)*2:trunc(ih/2)*2:0:0,format=yuva420p',
          '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', str(crf),
          '-row-mt', '1', '-an', out])
    return verify(out, d)


def mov(frames_dir, out, width=None, fps=30, alpha_quality=0.8, q=55):
    """HEVC + alpha (VideoToolbox) — the transparent-video format Safari understands."""
    d = scaled(frames_dir, width)
    _run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', _concat_list(d),
          '-vf', f'fps={fps},crop=trunc(iw/2)*2:trunc(ih/2)*2:0:0,format=bgra',
          '-c:v', 'hevc_videotoolbox', '-allow_sw', '1', '-alpha_quality', str(alpha_quality),
          '-q:v', str(q), '-tag:v', 'hvc1', '-an', out])
    return verify(out, d)


def mp4(frames_dir, out, bg='#ffffff', width=None, fps=30, crf=18):
    """H.264 on a solid background (no alpha). Smallest + universal when the page background is known."""
    d = scaled(frames_dir, width)
    w, h = Image.open(_frames(d)[0][0]).size
    color = '0x' + bg.lstrip('#')
    _run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', _concat_list(d),
          '-f', 'lavfi', '-i', f'color=c={color}:s={w}x{h}:r={fps}',
          '-filter_complex', f'[0:v]fps={fps},format=rgba[fg];[1:v][fg]overlay=shortest=1,'
                             f'crop=trunc(iw/2)*2:trunc(ih/2)*2:0:0,format=yuv420p',
          '-c:v', 'libx264', '-crf', str(crf), '-preset', 'slow', '-movflags', '+faststart', '-an', out])
    return verify(out, d)


def gif(frames_dir, out, width=None):
    """GIF fallback (1-bit alpha => jagged edges). Uses a global palette + correct disposal (no trails)."""
    d = scaled(frames_dir, width)
    files, durs = _frames(d)
    tmp = d.rstrip('/') + '_gifq'
    os.makedirs(tmp, exist_ok=True)
    imgs = [np.asarray(Image.open(f).convert('RGBA')) for f in files]
    idx = np.linspace(0, len(imgs) - 1, min(8, len(imgs))).astype(int)
    samp = np.concatenate([imgs[i][..., :3][imgs[i][..., 3] >= 128] for i in idx])[None]
    pal = Image.fromarray(samp).quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palimg = Image.new('P', (1, 1)); palimg.putpalette(pal.getpalette()[:765] + [0, 255, 0])
    cmd = ['magick', '-dispose', 'Background', '-loop', '0']
    for i, (im, t) in enumerate(zip(imgs, durs)):
        q = np.asarray(Image.fromarray(im[..., :3]).quantize(palette=palimg, dither=Image.Dither.NONE).convert('RGB'))
        transp = im[..., 3] < 128
        rgba = np.dstack([q, np.where(transp, 0, 255).astype(np.uint8)]); rgba[transp, :3] = 0
        p = os.path.join(tmp, f'f{i:04d}.png'); Image.fromarray(rgba, 'RGBA').save(p, compress_level=1)
        cmd += ['-delay', str(max(2, round(t / 10))), p]
    _run(cmd + ['-layers', 'Optimize', out])
    return verify(out, d)


# ---------------- verification ----------------
def _webp_durations(path):
    info = _run(['webpmux', '-info', path]).stdout
    return [int(m.group(1)) for m in re.finditer(r'^\s*\d+:\s+\d+\s+\d+\s+\w+\s+-?\d+\s+-?\d+\s+(\d+)', info, re.M)]


def verify(out, frames_dir):
    """Decode the output and check: total duration, and (for image formats) per-frame alpha vs source frames."""
    files, durs = _frames(frames_dir)
    total_src = sum(durs)
    ext = os.path.splitext(out)[1].lower()
    report = {'file': out, 'size': _size(out), 'src_frames': len(files), 'src_ms': total_src}
    if ext in ('.png', '.apng', '.gif', '.webp'):
        im = Image.open(out)
        n = getattr(im, 'n_frames', 1)
        dec_durs = _webp_durations(out) if ext == '.webp' else []
        starts = np.cumsum([0] + durs)
        t, worst_alpha, worst_rgb = 0, 0, 0.0
        for i in range(n):
            im.seek(i)
            dur = dec_durs[i] if dec_durs else im.info.get('duration', 0)
            src_i = int(np.searchsorted(starts, t, side='right') - 1)
            dec = np.asarray(im.convert('RGBA')).astype(np.int16)
            ref = np.asarray(Image.open(files[min(src_i, len(files) - 1)]).convert('RGBA')).astype(np.int16)
            if ext == '.gif':
                bad = (dec[..., 3] > 0) != (ref[..., 3] >= 128)
            else:
                bad = np.abs(dec[..., 3] - ref[..., 3]) > (8 if ext == '.webp' else 0)
            worst_alpha = max(worst_alpha, int(bad.sum()))
            op = ref[..., 3] > 200
            if op.any():
                worst_rgb = max(worst_rgb, float(np.abs(dec[..., :3] - ref[..., :3])[op].mean()))
            t += int(dur)
        report.update(frames=n, ms=t, alpha_mismatch_px=worst_alpha, mean_rgb_err=round(worst_rgb, 2))
        report['ok'] = (t == total_src) and worst_alpha == 0
    else:
        probe = _run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=width,height,pix_fmt,codec_name',
                      '-of', 'json', out]).stdout
        j = json.loads(probe)
        ms = round(float(j['format']['duration']) * 1000)
        report.update(ms=ms, stream=j['streams'][0])
        report['ok'] = abs(ms - total_src) <= 80
    print(('OK   ' if report['ok'] else 'FAIL ') + json.dumps(report, ensure_ascii=False))
    return report
