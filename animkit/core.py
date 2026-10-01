"""Pixel core: premultiplied RGBA float32 layers, warps, soft masks, inpainting.

Convention: layers are float32 HxWx4, PREMULTIPLIED, 0..255. Convert to straight uint8 only at save time.
Premultiplied math is what keeps edges clean (no dark/white fringes) when warping, resizing and compositing.
"""
import numpy as np
import cv2
from PIL import Image


# ---------- io ----------
def load(path):
    """Load any image -> premultiplied float32 RGBA."""
    a = np.asarray(Image.open(path).convert('RGBA'), dtype=np.float32)
    return premultiply(a)


def premultiply(straight):
    out = straight.astype(np.float32).copy()
    out[..., :3] *= out[..., 3:4] / 255.0
    return out


def unpremultiply(prem):
    """premultiplied float -> straight uint8 RGBA."""
    a = prem[..., 3:4]
    rgb = np.where(a > 1e-3, prem[..., :3] * 255.0 / np.maximum(a, 1e-3), 0)
    return np.concatenate([rgb, a], axis=2).round().clip(0, 255).astype(np.uint8)


def save(path, prem, compress_level=1):
    Image.fromarray(unpremultiply(prem), 'RGBA').save(path, compress_level=compress_level)


def resize(prem, size):
    """High-quality resize (Lanczos) in premultiplied space. size=(w, h)."""
    return cv2.resize(prem, size, interpolation=cv2.INTER_LANCZOS4 if size[0] > prem.shape[1] else cv2.INTER_AREA).clip(0, 255)


# ---------- compositing ----------
def over(top, bottom):
    """Porter-Duff over, both premultiplied."""
    return top + bottom * (1.0 - top[..., 3:4] / 255.0)


def with_mask(prem, coverage):
    """Multiply a layer by a 0..1 coverage mask (HxW)."""
    return prem * coverage[..., None]


def solid(h, w, rgb, alpha=255.0):
    out = np.empty((h, w, 4), np.float32)
    out[..., :3] = np.asarray(rgb, np.float32) * alpha / 255.0
    out[..., 3] = alpha
    return out


# ---------- coordinate grids & warps ----------
def grid(h, w, x0=0, y0=0):
    """Pixel-center coordinates (float32) for a region."""
    ys, xs = np.mgrid[y0:y0 + h, x0:x0 + w].astype(np.float32)
    return xs, ys


def remap(prem, map_x, map_y, cubic=False):
    """Sample layer at (map_x, map_y) (inverse mapping). Outside -> transparent."""
    return cv2.remap(prem, map_x.astype(np.float32), map_y.astype(np.float32),
                     cv2.INTER_CUBIC if cubic else cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0)).clip(0, 255)


def rotate_maps(xs, ys, pivot, angle_rad):
    """Inverse maps for rotating content by angle (rad, per-pixel array allowed) around pivot.
    Positive angle = clockwise on screen (y down)."""
    px, py = pivot
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    dx, dy = xs - px, ys - py
    return px + c * dx + s * dy, py - s * dx + c * dy


def transform(prem, pivot=(0, 0), angle_deg=0.0, scale=(1.0, 1.0), translate=(0.0, 0.0), cubic=False):
    """Rigid/affine move of a whole layer about pivot (inverse-mapped, so no holes)."""
    h, w = prem.shape[:2]
    xs, ys = grid(h, w)
    xs = xs - translate[0]; ys = ys - translate[1]
    mx, my = rotate_maps(xs, ys, pivot, np.deg2rad(angle_deg))
    mx = pivot[0] + (mx - pivot[0]) / scale[0]
    my = pivot[1] + (my - pivot[1]) / scale[1]
    return remap(prem, mx, my, cubic)


def bend(prem, pivot, angle_deg, weight, side_sign=None, cubic=False):
    """Non-rigid 'flex': rotate each pixel around pivot by angle*weight(x,y).
    weight: HxW array (e.g. smoothstep of distance) -> roots move little, tips a lot.
    side_sign: optional HxW array of +1/-1 to mirror the motion (left/right wings).
    Rotation around pivot keeps distance to pivot, so content under a round body is never revealed."""
    h, w = prem.shape[:2]
    xs, ys = grid(h, w)
    ang = np.deg2rad(angle_deg) * weight
    if side_sign is not None:
        ang = ang * side_sign
    mx, my = rotate_maps(xs, ys, pivot, ang)
    return remap(prem, mx, my, cubic)


def displace(prem, dx, dy, cubic=False):
    """Generic displacement field warp: output(x,y) = input(x - dx, y - dy)."""
    h, w = prem.shape[:2]
    xs, ys = grid(h, w)
    return remap(prem, xs - dx, ys - dy, cubic)


# ---------- masks (0..1 coverage, anti-aliased) ----------
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def cov(signed_dist, soft=1.0):
    """Coverage from signed distance (positive inside). soft>1 = blurrier edge."""
    return np.clip(signed_dist / soft + 0.5, 0.0, 1.0)


def disk(xs, ys, cx, cy, r, soft=1.0):
    return cov(r - np.hypot(xs - cx, ys - cy), soft)


def stroke_along(xs, ys, curve, thickness, soft=1.0):
    """Anti-aliased stroke along y = curve(x) (curve: callable, e.g. np.poly1d)."""
    c = curve(xs)
    d = np.gradient(curve(xs[0]))[None, :] if xs.ndim == 2 else np.gradient(c)
    dist = np.abs(ys - c) / np.sqrt(1 + d ** 2)
    return cov(thickness / 2 - dist, soft)


def supersample(fn, x0, y0, w, h, ss=4):
    """Exact AA for arbitrary boolean shapes: fn(xs, ys)->bool on an ss×ss subgrid, averaged."""
    xs = x0 + (np.arange(w * ss, dtype=np.float32) + 0.5) / ss - 0.5
    ys = y0 + (np.arange(h * ss, dtype=np.float32) + 0.5) / ss - 0.5
    m = fn(xs[None, :], ys[:, None]).astype(np.float32)
    return m.reshape(h, ss, w, ss).mean(axis=(1, 3))


def alpha_mask(prem, thr=8):
    return prem[..., 3] > thr


def feather(mask01, radius):
    """Blur a 0..1 mask for soft transitions."""
    k = int(radius * 3) | 1
    return cv2.GaussianBlur(mask01.astype(np.float32), (k, k), radius)


# ---------- reconstruction of hidden areas ----------
def inpaint(prem, hole_mask, radius=6, method='telea'):
    """Fill hole_mask (bool HxW) from surroundings. Works on straight RGB + alpha separately."""
    st = unpremultiply(prem)
    m = hole_mask.astype(np.uint8) * 255
    flag = cv2.INPAINT_TELEA if method == 'telea' else cv2.INPAINT_NS
    rgb = cv2.inpaint(np.ascontiguousarray(st[..., :3]), m, radius, flag)
    a = cv2.inpaint(np.ascontiguousarray(st[..., 3]), m, radius, flag)
    return premultiply(np.dstack([rgb, a]).astype(np.float32))


def radial_fill_from_reflection(img, valid, cx, cy):
    """Fill invalid pixels of a round object (iris, ball, coin) by point-reflection through its center."""
    out = img.copy()
    ys, xs = np.nonzero(~valid)
    rx = (2 * cx - xs).astype(np.float32); ry = (2 * cy - ys).astype(np.float32)
    out[ys, xs] = cv2.remap(img, rx[None, :], ry[None, :], cv2.INTER_LINEAR)[0]
    return out


def high_pass_texture(straight_rgb, sigma=2.5):
    """Grain/texture component (image - blur) — add onto flat synthesized fills so they match hand-drawn grain."""
    blur = cv2.GaussianBlur(straight_rgb.astype(np.float32), (0, 0), sigma)
    return straight_rgb.astype(np.float32) - blur
