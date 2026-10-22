"""Read embedded KiCad board geometry without changing the engineering source."""
import json
import math
import re
from pathlib import Path


def parse(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    stack, root = [], None
    for token in tokens:
        if token == '(':
            node = []
            if stack:
                stack[-1].append(node)
            else:
                root = node
            stack.append(node)
        elif token == ')':
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if stack:
        raise ValueError('Unclosed KiCad node')
    return root


def nodes(parent, key):
    return [n for n in parent if isinstance(n, list) and n and n[0] == key]


def node(parent, key, default=None):
    return next(iter(nodes(parent, key)), default)


def board_data(path):
    board = parse(Path(path).read_text())
    components = []
    for fp in nodes(board, 'footprint'):
        props = {p[1]: p[2] for p in nodes(fp, 'property')}
        at = list(map(float, node(fp, 'at')[1:]))
        x, y = at[:2]
        angle = at[2] if len(at) > 2 else 0
        theta = math.radians(angle)
        pads = []
        for p in nodes(fp, 'pad'):
            pos = list(map(float, node(p, 'at', ['at', 0, 0])[1:]))
            px = x + pos[0] * math.cos(theta) + pos[1] * math.sin(theta)
            py = y - pos[0] * math.sin(theta) + pos[1] * math.cos(theta)
            net = node(p, 'net', ['net', 0, ''])[2]
            pads.append({'number': p[1], 'net': net, 'x': round(px, 5), 'y': round(py, 5), 'shape': p[3], 'layers': node(p, 'layers', ['layers'])[1:], 'size': list(map(float, node(p, 'size')[1:]))})
        components.append({'ref': props.get('Reference', ''), 'value': props.get('Value', ''), 'footprint': fp[1], 'x': x, 'y': y, 'angle': angle, 'side': node(fp, 'layer')[1], 'pads': pads})
    edges = [n for n in board if isinstance(n, list) and n[0].startswith('gr_') and node(n, 'layer', ['', ''])[1] == 'Edge.Cuts']
    points = [list(map(float, p[1:])) for e in edges for key in ['start', 'end', 'mid', 'center'] for p in nodes(e, key)]
    bounds = {'minX': min(p[0] for p in points), 'minY': min(p[1] for p in points), 'maxX': max(p[0] for p in points), 'maxY': max(p[1] for p in points)}
    silkscreen = [{'text': n[1], 'at': list(map(float, node(n, 'at')[1:])), 'layer': node(n, 'layer')[1]} for n in nodes(board, 'gr_text') if node(n, 'layer')[1] in ['F.SilkS', 'B.SilkS']]
    return {'silkscreen': silkscreen, 'bounds': bounds, 'thickness': float(node(node(board, 'general'), 'thickness')[1]), 'components': components, 'connectors': [c for c in components if c['ref'] in ('J2', 'J3')]}


if __name__ == '__main__':
    import sys
    print(json.dumps(board_data(sys.argv[1]), ensure_ascii=False, indent=2))
