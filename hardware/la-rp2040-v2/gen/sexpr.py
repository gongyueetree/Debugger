"""Minimal KiCad S-expression reader/writer that preserves quoting."""


class Q(str):
    """A string that was (or must be) written in double quotes."""


def parse(text):
    stack = [[]]
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '(':
            stack.append([])
            i += 1
        elif c == ')':
            done = stack.pop()
            stack[-1].append(done)
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while text[j] != '"':
                if text[j] == '\\':
                    buf.append({'n': '\n', 't': '\t'}.get(text[j + 1], text[j + 1]))
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            stack[-1].append(Q(''.join(buf)))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()':
                j += 1
            stack[-1].append(text[i:j])
            i = j
    return stack[0][0]


def _atom(a):
    if isinstance(a, Q):
        return '"' + a.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if isinstance(a, float):
        s = f'{a:.4f}'.rstrip('0').rstrip('.')
        return s if s not in ('-0', '') else '0'
    return str(a)


def dump(node, indent=0):
    if not isinstance(node, list):
        return _atom(node)
    flat = '(' + ' '.join(dump(x) for x in node) + ')'
    if len(flat) <= 100 and '\n' not in flat:
        return flat
    pad = '\t' * (indent + 1)
    out = ['(' + _atom(node[0])]
    for x in node[1:]:
        if isinstance(x, list):
            out.append('\n' + pad + dump(x, indent + 1))
        else:
            out.append(' ' + _atom(x))
    out.append('\n' + '\t' * indent + ')')
    return ''.join(out)


def find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def first(node, key):
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None
