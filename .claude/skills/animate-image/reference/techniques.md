# Motion recipes (all proven on projects/winged-eye unless noted)

## Eye: look around
- Fit iris circle (outer dark ring) + pupil + highlight; fit upper/lower lid centerlines with `np.polyfit` (deg 4, robust: drop residual > 1.5 px, refit).
- Iris texture: copy disk; pixels hidden under the lid → `core.radial_fill_from_reflection` (point reflection through center). Remove highlight the same way and redraw it as a white `core.disk`.
- Clean base: fill the old iris area inside the opening with sclera color (median of sclera).
- Per frame: sample iris with offset (gx, gy); squash horizontally `sx = 1 - 0.07*|gx|/max` (reads as a sphere); clip by opening coverage (below upper centerline, above lower); redraw lid strokes on top (fit thickness/softness so neutral frame == source).
- Ranges that read well: gx ±50 px on a 160 px iris, gy −8…+10. Saccade 100–120 ms `out_cubic`; micro-move 3–4 px / 80 ms.
- Upper lid droops ~10% when looking down.

## Eye: blink
- Lid edge E(x) = U(x) + p·(L(x) − U(x)); fill from above the upper stroke to E with lid color (median of the lid band + tiled high-pass grain from that band, random offsets/flips, + faint low-freq tint), dark stroke along E (thickness tapers to corners). Supersample 4×.
- `timeline.blink`: close 80 ms, hold 40, open 160 (ease-out). 3–5 blinks per 15 s, one double blink, one blink hiding a gaze jump.

## Wings / arms / petals around a round body: flap
- Static body = soft disk mask (radius + 1.5). Wings = whole source warped by `core.bend(src, body_center, angle, weight, side_sign)`.
- weight = 0.15 + 0.85·smoothstep(R_body, tip_distance, dist) → roots barely move, tips lead (feels like flexing feathers).
- Rotation about the body center preserves distance → nothing hidden under the body is ever revealed.
- Keys (deg, tips): 0 → +4.5 (400 ms) → −1.8 (720) → +3.2 (1080) → −0.9 (1360) → 0 (1640). Check top/bottom rows stay transparent (no clipping at canvas edge).
- Once per 10–15 s loop is "иногда, аккуратно".

## Float / bob / breathe
- Float: `core.transform(frame, translate=(0, breathe(t, period, 3px)))` — moves every pixel ⇒ heavy files; prefer small localized motion.
- Breathe: scale 1 ± 0.01 about the bottom-center pivot.

## Sway (plants, hair, flags, tails) — not yet used in a project
- `core.bend` with pivot at the base and weight = smoothstep of distance from base; or `core.displace` with dx = A·sin(ωt + k·y)·(y-weight).
- Layer the swaying part over an inpainted background (`core.inpaint` of the part's mask dilated by 3–6 px).

## Glow / pulse / sparkle — not yet used in a project
- Glow: blurred copy of a bright part (`cv2.GaussianBlur` on the premultiplied layer), alpha × (0.5 + 0.5·sin), composited with `core.over` under/over.
- Sparkle: small 4-point stars from `core.supersample`, `pulse` envelopes at random times (fixed seed).

## Pitfalls
- Source alpha of AI cut-outs is often 250–254 inside — keep source alpha, never force 255 in a region (visible box on dark bg).
- Always premultiplied resize/warp (`core.resize`, `core.remap`) — straight-alpha resampling makes dark fringes.
- Pillow APNG `append_images` must be a list. Pillow WebP durations are unreliable → `webpmux -info`.
- GIF needs `-dispose Background -layers Optimize` (else trails when something moves over transparency). Already in `encode.gif`.
- Parallel render uses processes: keep script work under `if __name__ == '__main__'`, render function at module level.
