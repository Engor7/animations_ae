#!/usr/bin/env python3
"""MCP server exposing After Effects to Claude Code through the Claude Bridge panel.

Tools: ae_eval (run ExtendScript, get the real result or error), ae_state (project / active comp /
selection), ae_frame (render a frame and hand it back as an image).

The panel (tools/ae-bridge/extension) must be open in AE: Window > Extensions > Claude Bridge.
Run by Claude Code via .mcp.json; for a manual check:  echo '<json-rpc>' | .venv/bin/python mcp_ae.py
"""
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request

PORT = 37812
DIR = os.path.expanduser('~/animations/.ae-bridge')
TOKEN_FILE = os.path.join(DIR, 'token')
HINT = ('Is the bridge panel open in After Effects? Window > Extensions > Claude Bridge '
        '(the panel starts the server on 127.0.0.1:%d).' % PORT)


def bridge(endpoint, payload=None, timeout=180):
    try:
        token = open(TOKEN_FILE).read().strip()
    except OSError:
        raise RuntimeError('no bridge token at %s. %s' % (TOKEN_FILE, HINT))
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request('http://127.0.0.1:%d%s' % (PORT, endpoint), data=data,
                                 headers={'Content-Type': 'application/json', 'X-Bridge-Token': token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.URLError as e:
        raise RuntimeError('cannot reach the bridge (%s). %s' % (e, HINT))


def shrink(path, max_width, crop, bg):
    """Composite on a flat background and downscale, so a frame costs few tokens."""
    from PIL import Image
    im = Image.open(path).convert('RGBA')
    if crop:
        im = im.crop(tuple(int(v) for v in crop))
    flat = Image.new('RGBA', im.size, bg)
    flat.alpha_composite(im)
    im = flat.convert('RGB')
    if max_width and im.width > max_width:
        im = im.resize((max_width, max(1, round(im.height * max_width / im.width))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return base64.b64encode(buf.getvalue()).decode(), im.size


TOOLS = [
    {
        'name': 'ae_eval',
        'description': ('Run ExtendScript inside the open After Effects instance and get the result back. '
                        'The code is a function body: use `return` to send something back (return a string; '
                        'build JSON yourself, ExtendScript has no JSON object). Errors come back with the line '
                        'number. Some AE calls abort a script silently (fractional TextDocument.tracking, '
                        'OutputModule.setSettings on Color) - those return a "no result" error.'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'code': {'type': 'string', 'description': 'ExtendScript to run, e.g. `return app.version;`'},
                'timeout_ms': {'type': 'number', 'description': 'default 120000'},
            },
            'required': ['code'],
        },
    },
    {
        'name': 'ae_state',
        'description': ('What After Effects has open right now: app version, project file, every comp '
                        '(size, duration, fps, layer count), the active comp with its current time, the '
                        'selected layers and properties, and the render queue.'),
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'ae_frame',
        'description': ('Render one frame of a comp and return it as an image (also saved to disk). '
                        'Defaults to the active comp at its current time.'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'comp': {'type': 'string', 'description': 'comp name; default = the active comp'},
                'time': {'type': 'number', 'description': 'seconds; default = the comp current time'},
                'crop': {'type': 'array', 'items': {'type': 'number'},
                         'description': '[x0, y0, x1, y1] in comp pixels, to zoom into a detail'},
                'max_width': {'type': 'number', 'description': 'downscale width, default 900'},
                'bg': {'type': 'string', 'description': 'background behind alpha, default "#6e6e6e"'},
            },
        },
    },
]


def call_tool(name, args):
    if name == 'ae_eval':
        t = args.get('timeout_ms', 120000)
        r = bridge('/eval', {'code': args['code'], 'timeout': t}, timeout=t / 1000 + 30)
        if not r.get('ok'):
            return [{'type': 'text', 'text': 'AE error: ' + str(r.get('error'))}], True
        return [{'type': 'text', 'text': str(r.get('result'))}], False
    if name == 'ae_state':
        r = bridge('/state', {}, timeout=60)
        if not r.get('ok'):
            return [{'type': 'text', 'text': 'AE error: ' + str(r.get('error'))}], True
        return [{'type': 'text', 'text': str(r.get('result'))}], False
    if name == 'ae_frame':
        payload = {k: args[k] for k in ('comp', 'time') if k in args}
        r = bridge('/frame', payload, timeout=180)
        if not r.get('ok'):
            return [{'type': 'text', 'text': 'AE error: ' + str(r.get('error'))}], True
        b64, size = shrink(r['file'], args.get('max_width', 900), args.get('crop'), args.get('bg', '#6e6e6e'))
        return [{'type': 'text', 'text': '%s  shown at %dx%d  full frame: %s' % (r['result'], size[0], size[1], r['file'])},
                {'type': 'image', 'data': b64, 'mimeType': 'image/png'}], False
    raise RuntimeError('unknown tool ' + name)


def main():
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, mid = msg.get('method'), msg.get('id')
        if mid is None:                       # notification
            continue
        try:
            if method == 'initialize':
                ver = (msg.get('params') or {}).get('protocolVersion', '2024-11-05')
                result = {'protocolVersion': ver, 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'after-effects', 'version': '1.0.0'}}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                params = msg.get('params') or {}
                content, is_error = call_tool(params.get('name'), params.get('arguments') or {})
                result = {'content': content, 'isError': is_error}
            elif method == 'ping':
                result = {}
            else:
                out.write(json.dumps({'jsonrpc': '2.0', 'id': mid,
                                      'error': {'code': -32601, 'message': 'method not found: %s' % method}}) + '\n')
                out.flush()
                continue
            out.write(json.dumps({'jsonrpc': '2.0', 'id': mid, 'result': result}) + '\n')
        except Exception as e:                # report as a tool error, keep the server alive
            if method == 'tools/call':
                out.write(json.dumps({'jsonrpc': '2.0', 'id': mid, 'result': {
                    'content': [{'type': 'text', 'text': '%s: %s' % (type(e).__name__, e)}], 'isError': True}}) + '\n')
            else:
                out.write(json.dumps({'jsonrpc': '2.0', 'id': mid,
                                      'error': {'code': -32603, 'message': str(e)}}) + '\n')
        out.flush()


if __name__ == '__main__':
    main()
