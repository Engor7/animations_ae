"""CLI:  .venv/bin/python -m animkit <command> ...

  encode FRAMES_DIR [--apng OUT] [--webp OUT] [--webm OUT] [--mov OUT] [--mp4 OUT --bg '#fff'] [--gif OUT]
                    [--width PX] [--fps 30] [--quality 90]
  sheet  FRAMES_DIR OUT.png [--times 0,1200,...] [--count 8] [--cols 2] [--width 540] [--bg checker|white|dark|gray]
                    [--crop x0,y0,x1,y1]
  grid   IMAGE OUT.png [--box x0,y0,x1,y1] [--step 25] [--zoom 2]
  html   OUT.html FILE [FILE ...] [--width PX]
  verify OUTPUT FRAMES_DIR [--width PX]
"""
import argparse
import sys

from . import encode, preview


def ints(s):
    return tuple(int(v) for v in s.split(',')) if s else None


def main(argv=None):
    p = argparse.ArgumentParser(prog='animkit', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)

    e = sub.add_parser('encode')
    e.add_argument('frames')
    for k in ('apng', 'webp', 'webm', 'mov', 'mp4', 'gif'):
        e.add_argument(f'--{k}')
    e.add_argument('--bg', default='#ffffff')
    e.add_argument('--width', type=int)
    e.add_argument('--fps', type=int, default=30)
    e.add_argument('--quality', type=int, default=90)

    s = sub.add_parser('sheet')
    s.add_argument('frames'); s.add_argument('out')
    s.add_argument('--times'); s.add_argument('--count', type=int, default=8); s.add_argument('--cols', type=int, default=2)
    s.add_argument('--width', type=int, default=540); s.add_argument('--bg', default='checker'); s.add_argument('--crop')

    g = sub.add_parser('grid')
    g.add_argument('image'); g.add_argument('out')
    g.add_argument('--box'); g.add_argument('--step', type=int, default=25); g.add_argument('--zoom', type=int, default=2)

    h = sub.add_parser('html')
    h.add_argument('out'); h.add_argument('files', nargs='+'); h.add_argument('--width', type=int)

    v = sub.add_parser('verify')
    v.add_argument('output'); v.add_argument('frames'); v.add_argument('--width', type=int)

    a = p.parse_args(argv)
    ok = True
    if a.cmd == 'encode':
        jobs = [('apng', lambda o: encode.apng(a.frames, o, a.width)),
                ('webp', lambda o: encode.webp(a.frames, o, a.width, a.quality)),
                ('webm', lambda o: encode.webm(a.frames, o, a.width, a.fps)),
                ('mov', lambda o: encode.mov(a.frames, o, a.width, a.fps)),
                ('mp4', lambda o: encode.mp4(a.frames, o, a.bg, a.width, a.fps)),
                ('gif', lambda o: encode.gif(a.frames, o, a.width))]
        for key, fn in jobs:
            out = getattr(a, key)
            if out:
                ok &= fn(out)['ok']
    elif a.cmd == 'sheet':
        preview.contact_sheet(a.frames, a.out, times=ints(a.times), count=a.count, cols=a.cols,
                              width=a.width, bg=a.bg, crop=ints(a.crop))
    elif a.cmd == 'grid':
        preview.grid(a.image, a.out, box=ints(a.box), step=a.step, zoom=a.zoom)
    elif a.cmd == 'html':
        preview.html(a.out, a.files, a.width)
    elif a.cmd == 'verify':
        ok = encode.verify(a.output, encode.scaled(a.frames, a.width))['ok']
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
