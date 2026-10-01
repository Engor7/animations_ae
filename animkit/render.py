"""Parallel frame rendering -> frames_dir/f0000.png ... + meta.json (durations, states)."""
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

from . import core


def _save_result(img, path):
    if img.dtype == np.uint8:
        Image.fromarray(img, 'RGBA').save(path, compress_level=1)
    else:
        core.save(path, img)


def _job(args):
    render_fn, state, path = args
    _save_result(render_fn(state), path)
    return path


def render_frames(frames, render_fn, out_dir, workers=None):
    """frames: [(state_dict, duration_ms), ...] from timeline.schedule.
    render_fn(state) -> premultiplied float32 RGBA (or straight uint8 RGBA).
    render_fn must be a module-level function (picklable) for workers>1; keep script body under __main__."""
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.startswith('f') and f.endswith('.png'):
            os.remove(os.path.join(out_dir, f))
    jobs = [(render_fn, s, os.path.join(out_dir, f'f{i:04d}.png')) for i, (s, _) in enumerate(frames)]
    workers = workers if workers is not None else min(8, os.cpu_count() or 1)
    t0 = time.time()
    if workers <= 1:
        for j in jobs:
            _job(j)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_job, jobs, chunksize=2))
    meta = [{'duration': int(d), 'state': s} for s, d in frames]
    json.dump(meta, open(os.path.join(out_dir, 'meta.json'), 'w'))
    total = sum(d for _, d in frames)
    print(f'rendered {len(frames)} frames ({total} ms) in {time.time() - t0:.1f}s -> {out_dir}')
    return out_dir
