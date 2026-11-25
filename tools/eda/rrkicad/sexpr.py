"""Minimal S-expression reader/writer for KiCad files.

Parsed form: nested Python lists.  Bare tokens are ``str``; quoted strings are
``Q`` (a ``str`` subclass) so they are re-quoted on output.  Numbers given as
``int``/``float`` when *building* trees are formatted compactly.
"""
import re

__all__ = ["Q", "parse", "dump", "find", "find_all", "num", "extract_block"]


class Q(str):
    """A string that must be written in double quotes."""
    __slots__ = ()


_TOKEN = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+')
_UNESC = re.compile(r'\\(.)')
_UNESC_MAP = {"n": "\n", "t": "\t", "r": "\r"}


def _unescape(s):
    return _UNESC.sub(lambda m: _UNESC_MAP.get(m.group(1), m.group(1)), s)


def _escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            .replace("\t", "\\t").replace("\r", ""))


def parse(text):
    """Parse one S-expression (the first complete list in *text*)."""
    stack = []
    cur = None
    for m in _TOKEN.finditer(text):
        t = m.group(0)
        if t == "(":
            new = []
            if cur is not None:
                cur.append(new)
                stack.append(cur)
            cur = new
        elif t == ")":
            if not stack:
                return cur
            cur = stack.pop()
        elif t[0] == '"':
            cur.append(Q(_unescape(t[1:-1])))
        else:
            cur.append(t)
    raise ValueError("unbalanced S-expression")


def num(v):
    """Format a number the way KiCad likes it (no exponent, trimmed zeros)."""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    s = "%.4f" % v
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _atom(a):
    if isinstance(a, Q):
        return '"' + _escape(a) + '"'
    if isinstance(a, str):
        return a
    return num(a)


def dump(node, indent=0, out=None):
    """Serialise *node* to KiCad-style text (tabs, one sub-list per line)."""
    top = out is None
    if top:
        out = []
    pad = "\t" * indent
    if not any(isinstance(c, list) for c in node):
        out.append(pad + "(" + " ".join(_atom(a) for a in node) + ")")
    else:
        # keep leading atoms on the opening line
        i = 0
        head = []
        while i < len(node) and not isinstance(node[i], list):
            head.append(_atom(node[i]))
            i += 1
        out.append(pad + "(" + " ".join(head))
        # compact "(xy ..)" runs as KiCad does
        run = []
        for c in node[i:]:
            if isinstance(c, list):
                if c and c[0] == "xy" and len(c) == 3:
                    run.append("(xy %s %s)" % (_atom(c[1]), _atom(c[2])))
                    continue
                if run:
                    out.append(pad + "\t" + " ".join(run))
                    run = []
                dump(c, indent + 1, out)
            else:
                if run:
                    out.append(pad + "\t" + " ".join(run))
                    run = []
                out.append(pad + "\t" + _atom(c))
        if run:
            out.append(pad + "\t" + " ".join(run))
        out.append(pad + ")")
    if top:
        return "\n".join(out) + "\n"
    return None


def find(node, key):
    """First child list whose head is *key* (or None)."""
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def find_all(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


_PQ = re.compile(r'[()]|"(?:\\.|[^"\\])*"')


def extract_block(text, start):
    """Return the balanced ``( ... )`` substring of *text* starting at *start*."""
    depth = 0
    for m in _PQ.finditer(text, start):
        t = m.group(0)
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
            if depth == 0:
                return text[start:m.end()]
    raise ValueError("unbalanced block")
