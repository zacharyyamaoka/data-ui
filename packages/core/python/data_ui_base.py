"""Read and write .base view files with the standard library only (no PyYAML), for Python-built pages.

    from data_ui_base import loads, dumps
    doc = loads(open("views.base", encoding="utf-8").read())

The same YAML subset as packages/core/src/base.js, ported line for line, and tested against the same oracle
(PyYAML) on every .base file in Zach's vault (test_data_ui_base.py): block mappings and sequences, flow [..] and
{..} (which may span lines), plain / 'single' / "double" scalars, null ~ true false, numbers, # comments, the block
scalars | |- > >-, and a leading ---. Anchors, aliases, tags, complex keys and several documents are refused with
a clear error.

WHY stdlib: robotparts' build is stdlib-only, and a page's views must read the same in Python, Node and the browser.
"""

from __future__ import annotations

import json
import re

__all__ = ["BaseSyntaxError", "loads", "loads_with_lines", "dumps"]

NUMBER = re.compile(r"^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$")
ITEM = re.compile(r"^-( |$)")


class BaseSyntaxError(ValueError):
    def __init__(self, message: str, line: int):
        super().__init__(f"line {line}: {message}")
        self.line = line
        self.reason = message


def _number(text: str):
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    return float(text)


def _plain(text: str):
    if text in ("", "~", "null", "Null", "NULL"):
        return None
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    if NUMBER.match(text):
        return _number(text)
    return text


def _comment_at(text: str) -> int:
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if quote == '"' and c == "\\":
                i += 1
            elif c == quote:
                if quote == "'" and text[i + 1:i + 2] == "'":
                    i += 1
                else:
                    quote = None
        elif c == "#" and (i == 0 or text[i - 1] == " "):
            return i
        elif c in "\"'" and (i == 0 or re.match(r"[\s[{,:-]", text[i - 1])):
            quote = c
        i += 1
    return -1


def _key_colon(text: str) -> int:
    quote = None
    depth = 0
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if quote == '"' and c == "\\":
                i += 1
            elif c == quote:
                if quote == "'" and text[i + 1:i + 2] == "'":
                    i += 1
                else:
                    quote = None
            i += 1
            continue
        if c in "\"'" and i == 0:
            quote = c
        elif c in "[{":
            if i == 0:
                return -1
            depth += 1
        elif c in "]}":
            depth -= 1
        elif c == ":" and depth <= 0 and (i + 1 == len(text) or text[i + 1] == " "):
            return i
        i += 1
    return -1


def _unquote(text: str, line: int) -> str:
    if text[0] == "'":
        if len(text) < 2 or not text.endswith("'"):
            raise BaseSyntaxError(f"an unclosed ' quote: {text}", line)
        return text[1:-1].replace("''", "'")
    if len(text) < 2 or not text.endswith('"'):
        raise BaseSyntaxError(f'an unclosed " quote: {text}', line)
    try:
        return json.loads(text.replace("\\'", "'").replace("\t", "\\t"))
    except ValueError:
        raise BaseSyntaxError(f"cannot read the string {text}", line) from None


def _key_text(raw: str, line: int) -> str:
    k = raw.strip()
    if k[:1] in ("'", '"'):
        return _unquote(k, line)
    if k.startswith("? "):
        raise BaseSyntaxError("complex keys (? ) are not supported", line)
    return k


def _guard(text: str, line: int) -> None:
    t = text.lstrip()
    if t[:1] in ("&", "*"):
        raise BaseSyntaxError("anchors and aliases (& *) are not supported in .base files", line)
    if t[:1] == "!":
        raise BaseSyntaxError(f"a value that starts with ! is a YAML tag; quote it: '{t}'", line)


def _parse_flow(src: str, line: int):
    pos = [0]

    def ws():
        while pos[0] < len(src) and src[pos[0]].isspace():
            pos[0] += 1

    def at():
        return src[pos[0]] if pos[0] < len(src) else ""

    def value(in_map: bool):
        ws()
        c = at()
        if c == "[":
            pos[0] += 1
            out = []
            ws()
            if at() == "]":
                pos[0] += 1
                return out
            while True:
                out.append(value(False))
                ws()
                if at() == ",":
                    pos[0] += 1
                    ws()
                    if at() == "]":
                        pos[0] += 1
                        return out
                    continue
                if at() == "]":
                    pos[0] += 1
                    return out
                raise BaseSyntaxError(f"expected , or ] in {src}", line)
        if c == "{":
            pos[0] += 1
            out = {}
            ws()
            if at() == "}":
                pos[0] += 1
                return out
            while True:
                k = value(True)
                ws()
                v = None
                if at() == ":":
                    pos[0] += 1
                    v = value(False)
                    ws()
                key = "null" if k is None else (json.dumps(k) if isinstance(k, bool) else str(k))
                if key in out:
                    raise BaseSyntaxError(f"the key '{key}' appears twice", line)
                out[key] = v
                if at() == ",":
                    pos[0] += 1
                    ws()
                    if at() == "}":
                        pos[0] += 1
                        return out
                    continue
                if at() == "}":
                    pos[0] += 1
                    return out
                raise BaseSyntaxError(f"expected , or }} in {src}", line)
        if c in ("'", '"'):
            j = pos[0] + 1
            while j < len(src):
                if c == '"' and src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c:
                    if c == "'" and src[j + 1:j + 2] == "'":
                        j += 2
                        continue
                    break
                j += 1
            text = src[pos[0]:j + 1]
            pos[0] = j + 1
            return _unquote(text, line)
        j = pos[0]
        while j < len(src) and src[j] not in ",[]{}" and not (
                in_map and src[j] == ":" and (j + 1 == len(src) or re.match(r"[\s,\]}]", src[j + 1]))):
            j += 1
        text = src[pos[0]:j].strip()
        pos[0] = j
        _guard(text, line)
        return _plain(text)

    out = value(False)
    ws()
    if pos[0] < len(src):
        raise BaseSyntaxError(f'unexpected "{src[pos[0]:pos[0] + 12]}" after {src[:pos[0]]}', line)
    return out


def _flow_balance(text: str) -> int:
    quote = None
    depth = 0
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if quote == '"' and c == "\\":
                i += 1
            elif c == quote:
                if quote == "'" and text[i + 1:i + 2] == "'":
                    i += 1
                else:
                    quote = None
        elif c in "\"'":
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        i += 1
    return depth


def _closes(src: str) -> bool:
    q = src[0]
    if len(src) < 2:
        return False
    k = 1
    while k < len(src):
        if q == '"' and src[k] == "\\":
            k += 2
            continue
        if src[k] == q:
            if q == "'" and src[k + 1:k + 2] == "'":
                k += 2
                continue
            return k == len(src) - 1 or not src[k + 1:].strip()
        k += 1
    return False


def loads_with_lines(text: str):
    """(doc, lines): lines maps a path tuple to the 1-based line it was written on."""
    raw = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = []
    for n, full in enumerate(raw):
        indent = re.match(r"^[ \t]*", full).group(0)
        if "\t" in indent and full.strip() and not full.strip().startswith("#"):
            raise BaseSyntaxError("a tab in the indentation (use spaces)", n + 1)
        at = _comment_at(full)
        body = (full[:at] if at >= 0 else full).rstrip()
        lines.append({"n": n + 1, "indent": len(indent), "text": body[len(indent):], "raw": full})
    where: dict[tuple, int] = {}
    pos = [0]

    def skip():
        while pos[0] < len(lines) and not lines[pos[0]]["text"]:
            pos[0] += 1

    skip()
    if pos[0] < len(lines) and lines[pos[0]]["indent"] == 0 and lines[pos[0]]["text"] == "---":
        pos[0] += 1
        skip()

    def block_scalar(header: str, parent_indent: int) -> str:
        folded = header[0] == ">"
        chomp = "strip" if "-" in header else "keep" if "+" in header else "clip"
        body: list[str] = []
        indent = None
        while pos[0] < len(lines):
            l = lines[pos[0]]
            if l["raw"].strip() == "":
                body.append("")
                pos[0] += 1
                continue
            ind = len(re.match(r"^ *", l["raw"]).group(0))
            if ind <= parent_indent:
                break
            if indent is None:
                indent = ind
            if ind < indent:
                break
            body.append(l["raw"][indent:])
            pos[0] += 1
        while body and body[-1] == "" and chomp != "keep":
            body.pop()
        if folded:
            out = ""
            for k, x in enumerate(body):
                out = x if k == 0 else (out + "\n" + x if x == "" or body[k - 1] == "" else out + " " + x)
        else:
            out = "\n".join(body)
        if chomp != "strip" and body:
            out += "\n"
        return out

    def inline(text: str, line: int, parent_indent: int):
        _guard(text, line)
        if text in ("|", "|-", "|+", ">", ">-", ">+"):
            return block_scalar(text, parent_indent)
        if text[0] in "[{":
            src = text
            while _flow_balance(src) > 0 and pos[0] < len(lines):
                src += " " + lines[pos[0]]["text"].strip()
                pos[0] += 1
                skip()
            return _parse_flow(src, line)
        if text[0] in "\"'":
            src = text
            while not _closes(src) and pos[0] < len(lines):
                src += " " + lines[pos[0]]["raw"].strip()
                pos[0] += 1
            return _unquote(src, line)
        src = text
        while (pos[0] < len(lines) and lines[pos[0]]["text"] and lines[pos[0]]["indent"] > parent_indent
               and _key_colon(lines[pos[0]]["text"]) < 0 and not ITEM.match(lines[pos[0]]["text"])):
            src += " " + lines[pos[0]]["text"].strip()
            pos[0] += 1
        return _plain(src)

    def block(path):
        skip()
        if pos[0] >= len(lines):
            return None
        l = lines[pos[0]]
        if ITEM.match(l["text"]):
            return sequence(l["indent"], path)
        return mapping(l["indent"], path)

    def value_after_key(rest, key_indent, line, path):
        if rest != "":
            return inline(rest, line, key_indent)
        skip()
        if pos[0] >= len(lines):
            return None
        nxt = lines[pos[0]]
        if nxt["indent"] > key_indent:
            return block(path)
        if nxt["indent"] == key_indent and ITEM.match(nxt["text"]):
            return sequence(key_indent, path)
        return None

    def mapping(indent, path, first=None):
        out = {}
        while True:
            if first is not None:
                l, first = first, None
            else:
                skip()
                if pos[0] >= len(lines):
                    break
                l = lines[pos[0]]
                if l["indent"] < indent:
                    break
                if l["indent"] > indent:
                    raise BaseSyntaxError(f"unexpected indentation: {l['text']}", l["n"])
                if ITEM.match(l["text"]):
                    break
                pos[0] += 1
            at = _key_colon(l["text"])
            if at < 0 and l["text"] in ("---", "..."):
                raise BaseSyntaxError("a .base file holds one YAML document", l["n"])
            if at < 0:
                raise BaseSyntaxError(f'expected "key: value", got: {l["text"]}', l["n"])
            key = _key_text(l["text"][:at], l["n"])
            if key in out:
                raise BaseSyntaxError(f"the key '{key}' appears twice", l["n"])
            child = path + (key,)
            where[child] = l["n"]
            out[key] = value_after_key(l["text"][at + 1:].strip(), indent, l["n"], child)
        return out

    def sequence(indent, path):
        out = []
        while True:
            skip()
            if pos[0] >= len(lines):
                break
            l = lines[pos[0]]
            if l["indent"] != indent or not ITEM.match(l["text"]):
                if l["indent"] > indent:
                    raise BaseSyntaxError(f"unexpected indentation: {l['text']}", l["n"])
                break
            pos[0] += 1
            child = path + (len(out),)
            where[child] = l["n"]
            rest = l["text"][1:].lstrip(" ")
            col = indent + (len(l["text"]) - len(rest))
            if rest == "":
                skip()
                out.append(block(child) if pos[0] < len(lines) and lines[pos[0]]["indent"] > indent else None)
            elif ITEM.match(rest):
                pos[0] -= 1
                lines[pos[0]] = {**l, "indent": col, "text": rest}
                out.append(sequence(col, child))
            elif rest[0] not in "[{\"'" and _key_colon(rest) >= 0:
                out.append(mapping(col, child, {**l, "indent": col, "text": rest}))
            else:
                out.append(inline(rest, l["n"], indent))
        return out

    doc = None
    if pos[0] < len(lines):
        l = lines[pos[0]]
        if ITEM.match(l["text"]) or _key_colon(l["text"]) >= 0:
            doc = block(())
        else:
            pos[0] += 1
            doc = inline(l["text"], l["n"], -1)
        skip()
        if pos[0] < len(lines):
            extra = lines[pos[0]]
            if extra["text"] in ("---", "..."):
                raise BaseSyntaxError("a .base file holds one YAML document", extra["n"])
            raise BaseSyntaxError(f"unexpected indentation: {extra['text']}", extra["n"])
    return doc, where


def loads(text: str):
    """A .base file's text as plain Python data (dict, list, str, int, float, bool, None)."""
    return loads_with_lines(text)[0]


# ------------------------------------------------------------------------------------------------ writing

PLAIN = re.compile(r"^[^\W\d][\w .·/()›×$%+&'-]*$")
RESERVED = re.compile(r"^(?:true|false|null|yes|no|on|off|y|n|~)$", re.I)
BLOCK_KEYS = {"views", "filters", "and", "or", "not", "sort", "chart", "layer", "encoding", "guides", "kpi", "properties", "formulas"}
WIDTH = 110


def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v) if v == v and v not in (float("inf"), float("-inf")) else json.dumps(str(v))
    s = str(v)
    if PLAIN.match(s) and not RESERVED.match(s) and s.strip() == s and not NUMBER.match(s) and " '" not in s:
        return s
    if "'" not in s and not re.search(r"[\x00-\x1f]", s):
        return f"'{s}'"
    return json.dumps(s, ensure_ascii=False)


def _is_scalar(v) -> bool:
    return not isinstance(v, (dict, list))


def _flow(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_flow(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_scalar(k)}: {_flow(x)}" for k, x in v.items()) + " }" if v else "{}"
    return _scalar(v)


def _emit(value, indent: int, key, out: list) -> None:
    pad = " " * indent
    if isinstance(value, list):
        for item in value:
            if _is_scalar(item) or (len(_flow(item)) + indent + 4 <= WIDTH and key != "views"):
                out.append(f"{pad}- {_flow(item)}")
            elif isinstance(item, list):
                out.append(f"{pad}-")
                _emit(item, indent + 2, None, out)
            else:
                lines: list[str] = []
                _emit(item, indent + 2, None, lines)
                if lines:
                    lines[0] = f"{pad}- {lines[0][indent + 2:]}"
                out.extend(lines)
        return
    for k, v in value.items():
        head = f"{pad}{_scalar(k)}:"
        flow = _flow(v)
        names = isinstance(v, list) and all(_is_scalar(x) for x in v)
        inline_ok = _is_scalar(v) or (k not in BLOCK_KEYS and (names or (
            len(head) + 1 + len(flow) <= WIDTH and not (isinstance(v, list) and any(isinstance(x, (dict, list)) for x in v) and len(v) > 1))))
        if inline_ok or (isinstance(v, (list, dict)) and not v):
            out.append(f"{head} {flow}")
        else:
            out.append(head)
            _emit(v, indent + 2, k, out)


def dumps(doc, key=None) -> str:
    """YAML text in the house style of packages/core/src/base.js stringifyBase(); loads(dumps(doc)) == doc."""
    if _is_scalar(doc):
        return _scalar(doc) + "\n"
    out: list[str] = []
    _emit(doc, 0, key, out)
    return "\n".join(out) + "\n"
