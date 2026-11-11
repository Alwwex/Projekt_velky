"""Minimal S-expression parser/printer for KiCad files (no external deps)."""
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))', re.S)


class Q(str):
    """A quoted string atom."""


def parse(text):
    stack, cur = [], []
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError("parse error at %d: %r" % (pos, text[pos:pos + 40]))
        pos = m.end()
        lp, rp, qs, atom = m.groups()
        if lp:
            stack.append(cur)
            cur = []
        elif rp:
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif qs is not None:
            cur.append(Q(bytes(qs[1:-1], "utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")))
        elif atom is not None:
            cur.append(atom)
    assert not stack, "unbalanced"
    return cur[0] if len(cur) == 1 else cur


def _q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def dumps(node, indent=0):
    if isinstance(node, Q):
        return _q(node)
    if isinstance(node, str):
        return node
    if isinstance(node, (int,)):
        return str(node)
    if isinstance(node, float):
        s = ("%.4f" % node).rstrip("0").rstrip(".")
        return "0" if s == "-0" else s
    # list
    simple = all(not isinstance(x, list) for x in node)
    if simple:
        return "(" + " ".join(dumps(x) for x in node) + ")"
    # pořadí prvků zachovat (KiCad je na něm místy závislý, např. "(effects (font ..) hide)")
    pad = "  " * (indent + 1)
    out = "("
    seen_list = False
    for i, x in enumerate(node):
        if isinstance(x, list):
            out += "\n" + pad + dumps(x, indent + 1)
            seen_list = True
        elif seen_list:
            out += " " + dumps(x)
        else:
            out += ("" if i == 0 else " ") + dumps(x)
    out += "\n" + "  " * indent + ")"
    return out


def find(node, key):
    """First child list whose head == key."""
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]
