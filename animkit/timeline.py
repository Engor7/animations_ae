"""Time-based motion: easing, keyframe tracks, one-shot pulses, frame scheduling with hold-merging.

All times in milliseconds. A scene is a function state(t_ms) -> dict of floats.
schedule() samples it on a fixed step and merges identical consecutive states into one long frame,
so holds cost nothing in file size.
"""
import math


# ---------- easing (u in 0..1) ----------
def linear(u): return u
def in_quad(u): return u * u
def out_quad(u): return 1 - (1 - u) ** 2
def in_out_quad(u): return 2 * u * u if u < 0.5 else 1 - (-2 * u + 2) ** 2 / 2
def out_cubic(u): return 1 - (1 - u) ** 3
def in_out_cubic(u): return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2
def in_out_sine(u): return (1 - math.cos(math.pi * u)) / 2
def out_back(u, s=1.70158): return 1 + (s + 1) * (u - 1) ** 3 + s * (u - 1) ** 2


def out_elastic(u):
    if u in (0, 1):
        return u
    return 2 ** (-10 * u) * math.sin((u * 10 - 0.75) * (2 * math.pi) / 3) + 1


class Track:
    """Keyframes [(t_ms, value), ...] (value: float or tuple). ease applies per segment.
    Holds first value before the first key and last value after the last key."""

    def __init__(self, keys, ease=in_out_sine):
        self.keys = sorted(keys, key=lambda k: k[0])
        self.ease = ease

    def __call__(self, t):
        k = self.keys
        if t <= k[0][0]:
            return k[0][1]
        for (ta, va), (tb, vb) in zip(k, k[1:]):
            if ta <= t <= tb:
                e = self.ease((t - ta) / (tb - ta)) if tb > ta else 1.0
                if isinstance(va, (tuple, list)):
                    return tuple(a + (b - a) * e for a, b in zip(va, vb))
                return va + (vb - va) * e
        return k[-1][1]


class Moves:
    """Sequence of moves to targets: [(start_ms, target, duration_ms), ...]. Each move eases from wherever
    the value currently is — ideal for eye saccades, head turns, 'look at' behavior."""

    def __init__(self, moves, initial, ease=out_cubic):
        self.moves = sorted(moves, key=lambda m: m[0])
        self.initial = initial
        self.ease = ease

    def __call__(self, t):
        pos = self.initial
        for t0, target, dur in self.moves:
            if t < t0:
                break
            u = min((t - t0) / max(dur, 1e-6), 1.0)
            e = self.ease(u)
            if isinstance(pos, (tuple, list)):
                pos = tuple(p + (q - p) * e for p, q in zip(pos, target))
            else:
                pos = pos + (target - pos) * e
        return pos


def pulse(t, start, attack, hold, release, ease_in=None, ease_out=out_quad):
    """0 -> 1 -> 0 envelope (blink, squash, flash). Returns 0 outside."""
    d = t - start
    if d < 0 or d >= attack + hold + release:
        return 0.0
    if d < attack:
        u = d / attack
        return ease_in(u) if ease_in else u ** 1.15
    if d < attack + hold:
        return 1.0
    return 1.0 - ease_out((d - attack - hold) / release)


def blink(t, starts, close=80, hold=40, open_=160):
    """Natural eyelid closure 0..1 for blinks starting at each time in starts (fast close, slower open)."""
    return max([pulse(t, s, close, hold, open_) for s in starts] + [0.0])


def oscillation(t, keys_deg, start, ease=in_out_sine):
    """Damped flap/wave defined as extremes: keys_deg=[(dt, value), ...] relative to start; 0 outside."""
    d = t - start
    if d < keys_deg[0][0] or d > keys_deg[-1][0]:
        return 0.0
    return Track(keys_deg, ease)(d)


def breathe(t, period_ms, amp, phase=0.0):
    """Continuous seamless sine (make period divide the loop length to loop cleanly)."""
    return amp * math.sin(2 * math.pi * (t / period_ms) + phase)


# ---------- sampling ----------
def schedule(state_fn, duration_ms, step_ms=40, decimals=3):
    """Sample state_fn on a grid; merge equal consecutive states. Returns [(state_dict, duration_ms), ...].
    step 40ms = 25fps (smooth, GIF/APNG-safe). Use multiples of step for all event times."""
    frames = []
    for t in range(0, int(duration_ms), step_ms):
        s = {k: round(float(v), decimals) for k, v in state_fn(t).items()}
        if frames and frames[-1][0] == s:
            frames[-1][1] += step_ms
        else:
            frames.append([s, step_ms])
    return [(s, d) for s, d in frames]
