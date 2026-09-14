import html
import json
import re
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QSize, QTimer, QUrl, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygon
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

MERMAID_HEADS = {
    "flowchart",
    "graph",
    "sequenceDiagram",
    "classDiagram",
    "erDiagram",
    "pie",
    "gantt",
    "journey",
    "mindmap",
    "gitGraph",
    "stateDiagram",
    "stateDiagram-v2",
    "timeline",
    "quadrantChart",
    "sankey-beta",
    "C4Context",
    "block-beta",
    "zenuml",
    "architecture-beta",
}

SHAPES = [
    "Rectangle",
    "Rounded",
    "Diamond",
    "Hexagon",
    "Subroutine",
    "Cylinder",
    "Circle",
    "Parallelogram",
    "None",
]

FC_ARROWS = ["-->", "---", "-.->", "--x", "--o"]
SEQ_ARROWS = ["->>", "->", "-)", "-->>", "-->", "--x", "--)", "-x"]
CLASS_RELS = ["<|--", "<--", "--o", "--*", "--", "o--", "*--", "..>"]
ER_RELS = ["||--o{", "||--||", "|o--||", "}o--||", "||--|{", "|o--o|"]
ER_KEYS = ["", "PK", "FK", "UK"]


def _shape_wrap(kind, label):
    label = label.strip()
    if kind == "Rectangle":
        return "[%s]" % label
    if kind == "Rounded":
        return "(%s)" % label
    if kind == "Diamond":
        return "{%s}" % label
    if kind == "Hexagon":
        return "{{%s}}" % label
    if kind == "Subroutine":
        return "[[%s]]" % label
    if kind == "Cylinder":
        return "[(%s)]" % label
    if kind == "Circle":
        return "((%s))" % label
    if kind == "Parallelogram":
        return "[/%s/]" % label
    return label


def gen_flowchart(options, rows):
    lines = ["flowchart " + options.get("Direction", "TB")]
    ids = {}

    def node(kind, label):
        if kind == "None":
            return label.strip()
        key = (kind, label.strip())
        if key not in ids:
            ids[key] = "n" + str(len(ids) + 1)
        return ids[key] + _shape_wrap(kind, label)

    for r in rows:
        a, ash, arrow, label, b, bsh = (r + [""] * 6)[:6]
        if not a.strip() or not b.strip():
            continue
        anode = node(ash, a)
        bnode = node(bsh, b)
        if label.strip():
            lines.append("  %s %s|%s| %s" % (anode, arrow, label, bnode))
        else:
            lines.append("  %s %s %s" % (anode, arrow, bnode))
    return "\n".join(lines)


def _participants(rows):
    ids = {}
    names = []
    order = []
    for f, _arrow, _text, t in rows:
        for name in (f.strip(), t.strip()):
            if name and name not in ids:
                ids[name] = "P%d" % (len(order) + 1)
                order.append(name)
    return ids


def gen_sequence(options, rows):
    lines = ["sequenceDiagram"]
    ids = _participants(rows)
    for name, pid in ids.items():
        lines.append("  participant %s as %s" % (pid, name))
    for f, arrow, text, t in rows:
        if not f.strip() or not t.strip():
            continue
        line = "  %s%s%s" % (ids.get(f.strip(), f.strip()), arrow, ids.get(t.strip(), t.strip()))
        if text.strip():
            line += ": " + text
        lines.append(line)
    return "\n".join(lines)


def gen_class(options, rows):
    lines = ["classDiagram"]
    for a, rel, b, label in ((r + [""] * 4)[:4] for r in rows):
        line = "  %s %s %s" % (a.strip(), rel, b.strip())
        if label.strip():
            line += " : " + label
        if a.strip() and b.strip():
            lines.append(line)
    return "\n".join(lines)


def gen_er(options, rel_rows, attr_rows=None):
    attr_rows = attr_rows or []
    lines = ["erDiagram"]
    for a, rel, b, label in ((r + [""] * 4)[:4] for r in rel_rows):
        if not a.strip() or not b.strip():
            continue
        line = "  %s %s %s" % (a.strip(), rel, b.strip())
        if label.strip():
            line += ' : "%s"' % label
        else:
            line += ' : " "'
        lines.append(line)
    entities = {}
    for ent, attr, typ, key in ((r + [""] * 4)[:4] for r in attr_rows):
        if not ent.strip() or not attr.strip():
            continue
        entities.setdefault(ent.strip(), []).append((typ.strip(), attr.strip(), key.strip().upper()))
    for ent, attrs in entities.items():
        lines.append("  %s {" % ent)
        for typ, attr, key in attrs:
            lines.append("    " + " ".join(p for p in (typ, attr, key) if p))
        lines.append("  }")
    return "\n".join(lines)


def gen_pie(options, rows):
    lines = ["pie"]
    if options.get("Title"):
        lines.append("  title " + options["Title"])
    for label, value in rows:
        if label.strip() and value.strip():
            lines.append('  "%s" : %s' % (label, value.strip()))
    return "\n".join(lines)


def gen_gantt(options, rows):
    lines = ["gantt"]
    if options.get("Title"):
        lines.append("  title " + options["Title"])
    fmt = options.get("Date format") or "YYYY-MM-DD"
    lines.append("  dateFormat " + fmt)
    counter = [0]

    def task_id():
        counter[0] += 1
        return "t%d" % counter[0]

    for sec, task, start, dur in ((r + [""] * 4)[:4] for r in rows):
        if sec.strip():
            lines.append("  section " + sec)
        if task.strip():
            lines.append("  %s :%s, %s, %s" % (task, task_id(), start.strip(), dur.strip()))
    return "\n".join(lines)


_FC_WRAPS = [
    ("((", "))", "Circle"),
    ("[(", ")]", "Cylinder"),
    ("[[", "]]", "Subroutine"),
    ("[/", "/]", "Parallelogram"),
    ("{{", "}}", "Hexagon"),
    ("(", ")", "Rounded"),
    ("[", "]", "Rectangle"),
    ("{", "}", "Diamond"),
]


def _fc_shape_decode(text):
    text = text.strip()
    for pre, suf, kind in _FC_WRAPS:
        if text.endswith(suf):
            i = text.rfind(pre)
            if i >= 0:
                inner = text[i + len(pre) : len(text) - len(suf)]
                if inner.strip():
                    return inner.strip(), kind
    return text, "None"


def _parse_flowchart(head, lines):
    direction = (head[1] if len(head) > 1 else "TB").upper()
    if direction == "TD":
        direction = "TB"
    options = {"Direction": direction}
    rows = []
    for line in lines[1:]:
        s = line.strip()
        if not s or s.startswith(
            ("subgraph", "end", "style", "linkStyle", "classDef", "click", "direction")
        ):
            continue
        for arrow in sorted(FC_ARROWS, key=len, reverse=True):
            idx = s.find(arrow)
            if idx <= 0:
                continue
            from_part = s[:idx].strip()
            rest = s[idx + len(arrow) :].strip()
            label = ""
            if rest.startswith("|"):
                label, _, rest = rest[1:].partition("|")
                rest = rest.strip()
            if not from_part or not rest:
                continue
            fname, fshape = _fc_shape_decode(from_part)
            tname, tshape = _fc_shape_decode(rest)
            rows.append([fname, fshape, arrow, label, tname, tshape])
            break
    return "Flowchart", options, [rows]


def _parse_sequence(lines):
    options = {}
    mapping = {}
    rows = []
    for line in lines[1:]:
        s = line.strip()
        if s.startswith("participant"):
            m = re.match(r"^participant\s+(\S+)\s+as\s+(.*)$", s)
            if m:
                mapping[m.group(1)] = m.group(2).strip()
            continue
        skip = (
            "Note",
            "actor",
            "autoactivate",
            "loop",
            "alt",
            "else",
            "opt",
            "par",
            "rect",
            "end",
            "activate",
            "deactivate",
            "title",
            "box",
            "critical",
        )
        if not s or s.startswith(skip):
            continue
        found = False
        for arrow in sorted(SEQ_ARROWS, key=len, reverse=True):
            for prefix in ("", "+", "-"):
                tok = prefix + arrow
                idx = s.find(tok)
                if idx <= 0:
                    continue
                f = s[:idx].strip()
                rest = s[idx + len(tok) :].strip()
                if ":" in rest:
                    t, _, text = rest.partition(":")
                else:
                    t, text = rest, ""
                if f and t:
                    rows.append(
                        [mapping.get(f, f), arrow, text.strip(), mapping.get(t, t)]
                    )
                found = True
                break
            if found:
                break
    return "Sequence", options, [rows]


def _parse_class(lines):
    options = {}
    rows = []
    for line in lines[1:]:
        s = line.strip()
        skip = (
            "class",
            "namespace",
            "annotation",
            "note",
            "link",
            "click",
            "style",
            "end",
            "direction",
        )
        if not s or s.startswith(skip):
            continue
        for rel in sorted(CLASS_RELS, key=len, reverse=True):
            idx = s.find(rel)
            if idx <= 0:
                continue
            f = s[:idx].strip()
            rest = s[idx + len(rel) :].strip()
            if ":" in rest:
                t, _, label = rest.partition(":")
            else:
                t, label = rest, ""
            if f and t:
                rows.append([f, rel, t.strip(), label.strip()])
            break
    return "Class", options, [rows]


def _parse_er(lines):
    options = {}
    rel_rows = []
    attr_rows = []
    i = 1
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        has_rel = any(rel in s for rel in ER_RELS)
        if "{" in s and not has_rel:
            entity = s[: s.index("{")].strip()
            block = s[s.index("{") + 1 :]
            while "}" not in block:
                i += 1
                if i >= len(lines):
                    break
                nxt = lines[i]
                if "}" in nxt:
                    block += " " + nxt.split("}")[0]
                    break
                block += " " + nxt
            if "}" in block:
                block = block.split("}")[0]
            tokens = block.split()
            j = 0
            while j + 1 < len(tokens):
                typ = tokens[j]
                name = tokens[j + 1]
                key = ""
                if (
                    j + 2 < len(tokens)
                    and tokens[j + 2].upper() in ("PK", "FK", "UK")
                ):
                    key = tokens[j + 2].upper()
                    j += 3
                else:
                    j += 2
                if entity and name:
                    attr_rows.append([entity, name, typ, key])
            i += 1
            continue
        for rel in sorted(ER_RELS, key=len, reverse=True):
            idx = s.find(rel)
            if idx <= 0:
                continue
            f = s[:idx].strip()
            rest = s[idx + len(rel) :].strip()
            if ":" in rest:
                t, _, label = rest.partition(":")
            else:
                t, label = rest, ""
            rel_rows.append([f, rel, t.strip(), label.strip().strip('"').strip()])
            break
        i += 1
    return "ER", options, [rel_rows, attr_rows]


def _parse_pie(lines):
    options = {}
    rows = []
    for line in lines:
        s = line.strip()
        if s.startswith("pie"):
            parts = s.split(None, 2)
            if len(parts) >= 3 and parts[1].lower() == "title":
                options["Title"] = parts[2]
            continue
        if s.lower().startswith("title "):
            options["Title"] = s.split(None, 1)[1].strip()
            continue
        m = re.match(r'"([^"]+)"\s*:\s*(.*)', s)
        if m:
            rows.append([m.group(1), m.group(2).strip()])
    return "Pie", options, [rows]


def _parse_gantt(lines):
    options = {}
    rows = []
    section = ""
    for line in lines:
        s = line.strip()
        if not s or s.startswith(("gantt", "excludes", "includes", "axisFormat", "todayMarker")):
            continue
        if s.lower().startswith("dateformat"):
            options["Date format"] = s.split(None, 1)[1].strip()
            continue
        if s.startswith("title"):
            options["Title"] = s.split(None, 1)[1].strip()
            continue
        if s.lower().startswith("section "):
            section = s.split(None, 1)[1].strip()
            continue
        if ":" in s:
            task, _, rest = s.partition(":")
            parts = [p.strip() for p in rest.split(",")]
            start = parts[1] if len(parts) > 1 else ""
            dur = parts[2] if len(parts) > 2 else ""
            rows.append([section, task.strip(), start, dur])
        else:
            rows.append([section, s, "", ""])
    return "Gantt", options, [rows]


def parse_mermaid_wizard(source):
    lines = source.strip().splitlines()
    if not lines:
        return None
    heads = lines[0].strip().split(None, 1)
    if not heads:
        return None
    kind = heads[0]
    if kind in ("flowchart", "graph"):
        return _parse_flowchart(lines[0].split(), lines)
    if kind == "sequenceDiagram":
        return _parse_sequence(lines)
    if kind == "classDiagram":
        return _parse_class(lines)
    if kind == "erDiagram":
        return _parse_er(lines)
    if kind == "pie":
        return _parse_pie(lines)
    if kind == "gantt":
        return _parse_gantt(lines)
    return None


SCHEMAS = {
    "Flowchart": {
        "options": [("Direction", "combo", ["TB", "LR", "BT", "RL"], "TB")],
        "view": "flow",
        "chain": (0, 4),
        "add_label": "Add Step",
        "card": [
            ["text", 0, "From node"],
            ["shape", 1, "From shape"],
            ["arrow", 2, ""],
            ["text", 3, "Edge label"],
            ["text", 4, "To node"],
            ["shape", 5, "To shape"],
        ],
        "cols": [
            ("From", "text", ""),
            ("From shape", "shape", "Rectangle"),
            ("Arrow", "fcarrow", "-->"),
            ("Edge label", "text", ""),
            ("To", "text", ""),
            ("To shape", "shape", "Rectangle"),
        ],
        "default_rows": 2,
        "example": [
            ["Start", "Rectangle", "-->", "", "Next", "Rectangle"],
            ["Next", "Rectangle", "-->", "", "End", "Rounded"],
        ],
        "gen": gen_flowchart,
    },
    "Sequence": {
        "options": [],
        "view": "flow",
        "chain": (0, 3),
        "add_label": "Add Step",
        "card": [
            ["text", 0, "From"],
            ["arrow", 1, ""],
            ["text", 2, "Message"],
            ["text", 3, "To"],
        ],
        "cols": [
            ("From", "text", ""),
            ("Arrow", "seqarrow", "->>"),
            ("Text", "text", ""),
            ("To", "text", ""),
        ],
        "default_rows": 2,
        "example": [
            ["Alice", "->>", "Hello", "Bob"],
            ["Bob", "-->>", "Hi", "Alice"],
        ],
        "gen": gen_sequence,
    },
    "Class": {
        "options": [],
        "view": "flow",
        "chain": (0, 2),
        "add_label": "Add Relation",
        "card": [
            ["text", 0, "From class"],
            ["arrow", 1, ""],
            ["text", 2, "To class"],
            ["text", 3, "Label"],
        ],
        "cols": [
            ("Class A", "text", ""),
            ("Relationship", "classrel", "<|--"),
            ("Class B", "text", ""),
            ("Label", "text", ""),
        ],
        "default_rows": 2,
        "example": [
            ["Animal", "<|--", "Dog", ""],
            ["Dog", "--*", "Leash", ""],
        ],
        "gen": gen_class,
    },
    "ER": {
        "options": [],
        "tables": [
            {
                "title": "Relationships",
                "view": "flow",
                "chain": (0, 2),
                "add_label": "Add Relationship",
                "card": [
                    ["text", 0, "Entity A"],
                    ["arrow", 1, ""],
                    ["text", 2, "Entity B"],
                    ["text", 3, "Label"],
                ],
                "cols": [
                    ("Entity A", "text", ""),
                    ("Relationship", "errel", "||--o{"),
                    ("Entity B", "text", ""),
                    ("Label", "text", ""),
                ],
                "default_rows": 2,
                "example": [
                    ["User", "||--o{", "Order", "places"],
                    ["Order", "||--||", "Item", "contains"],
                ],
            },
            {
                "title": "Entity attributes",
                "view": "flow",
                "add_label": "Add Attribute",
                "card": [
                    ["text", 0, "Entity"],
                    ["text", 1, "Attribute"],
                    ["text", 2, "Type"],
                    ["combo", 3, "Key"],
                ],
                "cols": [
                    ("Entity", "text", ""),
                    ("Attribute", "text", ""),
                    ("Type", "text", ""),
                    ("Key", "erkey", ""),
                ],
                "default_rows": 3,
                "example": [
                    ["User", "id", "int", "PK"],
                    ["User", "name", "string", ""],
                    ["Order", "order_id", "int", "PK"],
                ],
            },
        ],
        "gen": gen_er,
    },
    "Pie": {
        "options": [("Title", "text", None, "")],
        "view": "flow",
        "add_label": "Add Slice",
        "card": [
            ["text", 0, "Label"],
            ["text", 1, "Value"],
        ],
        "cols": [("Label", "text", ""), ("Value", "text", "")],
        "default_rows": 3,
        "example": [
            ["Food", "40"],
            ["Rent", "60"],
            ["Fun", "20"],
        ],
        "gen": gen_pie,
    },
    "Gantt": {
        "options": [
            ("Title", "text", None, ""),
            ("Date format", "combo", ["YYYY-MM-DD", "MM-DD-YYYY", "DD-MM-YYYY"], "YYYY-MM-DD"),
        ],
        "view": "flow",
        "add_label": "Add Task",
        "card": [
            ["text", 0, "Section"],
            ["text", 1, "Task"],
            ["text", 2, "Start"],
            ["text", 3, "Duration"],
        ],
        "cols": [
            ("Section", "text", ""),
            ("Task", "text", ""),
            ("Start", "text", ""),
            ("Duration", "text", ""),
        ],
        "default_rows": 2,
        "example": [
            ["Dev", "Design", "2026-09-01", "5d"],
            ["Dev", "Code", "2026-09-08", "10d"],
        ],
        "gen": gen_gantt,
    },
}

CHOICES = {
    "shape": SHAPES,
    "fcarrow": FC_ARROWS,
    "seqarrow": SEQ_ARROWS,
    "classrel": CLASS_RELS,
    "errel": ER_RELS,
    "erkey": ER_KEYS,
}


def resource_dir():
    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return base / "web"


def load_web_page(view):
    view.load(QUrl.fromLocalFile(str(resource_dir() / "preview.html")))


def push_html(view, fragment):
    js = (
        "if (window.mermaidRender) { window.mermaidRender(%s); }"
        " else { document.body.setAttribute('data-pending-html', %s); }"
        % (json.dumps(fragment), json.dumps(fragment))
    )
    view.page().runJavaScript(js)


def mermaid_fragment(source):
    return '<pre class="mermaid">' + html.escape(source) + "</pre>"


class MdbBridge(QObject):
    editRequested = pyqtSignal(int, str)

    @pyqtSlot(int, str)
    def editMermaid(self, index, source):
        self.editRequested.emit(index, source)


_ARROW_STYLE = {
    "-->": ("solid", None, ">"),
    "---": ("solid", None, None),
    "-.->": ("dash", None, ">"),
    "--x": ("solid", None, "x"),
    "--o": ("solid", None, "o"),
    "->>": ("solid", None, ">>"),
    "->": ("solid", None, ">"),
    "-)": ("solid", None, ")"),
    "-->>": ("dash", None, ">>"),
    "--)": ("dash", None, ")"),
    "-x": ("solid", None, "x"),
    "<|--": ("solid", "<|", None),
    "<--": ("solid", "<", None),
    "--*": ("solid", None, "*"),
    "--": ("solid", None, None),
    "o--": ("solid", "o", None),
    "*--": ("solid", "*", None),
    "..>": ("dash", None, ">"),
}

_ARROW_COLOR = QColor("#30506b")


def _shape_icon(kind):
    pm = QPixmap(26, 20)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    pen = QPen(_ARROW_COLOR)
    pen.setWidth(2)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "Rectangle":
        p.drawRect(3, 3, 19, 14)
    elif kind == "Rounded":
        p.drawRoundedRect(3, 3, 19, 14, 4, 4)
    elif kind == "Circle":
        p.drawEllipse(5, 4, 16, 12)
    elif kind == "Diamond":
        p.drawPolygon(QPolygon([QPoint(13, 2), QPoint(22, 10), QPoint(13, 18), QPoint(4, 10)]))
    elif kind == "Hexagon":
        p.drawPolygon(QPolygon([QPoint(8, 3), QPoint(20, 3), QPoint(24, 10), QPoint(20, 17), QPoint(8, 17), QPoint(4, 10)]))
    elif kind == "Subroutine":
        p.drawRect(3, 3, 19, 14)
        p.drawLine(8, 3, 8, 17)
        p.drawLine(18, 3, 18, 17)
    elif kind == "Cylinder":
        p.drawEllipse(4, 2, 18, 5)
        p.drawLine(4, 4, 4, 15)
        p.drawLine(22, 4, 22, 15)
        p.drawEllipse(4, 12, 18, 4)
    elif kind == "Parallelogram":
        p.drawPolygon(QPolygon([QPoint(2, 3), QPoint(15, 3), QPoint(22, 17), QPoint(9, 17)]))
    else:
        p.drawLine(6, 6, 20, 6)
        p.drawLine(6, 14, 20, 14)
    p.end()
    return QIcon(pm)


def _draw_er_icon(p, token):
    left, _, right = token.partition("--")
    cy = 9
    x = 4
    for ch in left:
        if ch == "|":
            p.drawLine(x, cy - 4, x, cy + 4)
        elif ch == "o":
            p.drawEllipse(x - 2, cy - 3, 6, 6)
        elif ch == "}":
            for dy in (-3, 0, 3):
                p.drawLine(x, cy, x - 4, cy + dy)
        x += 3
    x = 38
    for ch in reversed(right):
        if ch == "|":
            p.drawLine(x, cy - 4, x, cy + 4)
        elif ch == "o":
            p.drawEllipse(x - 2, cy - 3, 6, 6)
        elif ch == "{":
            for dy in (-3, 0, 3):
                p.drawLine(x, cy, x + 4, cy + dy)
        x -= 3


def _arrow_icon(token):
    pm = QPixmap(42, 18)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    pen = QPen(_ARROW_COLOR)
    pen.setWidth(2)
    cy = 9
    if token in ER_RELS:
        p.setPen(pen)
        _draw_er_icon(p, token)
        p.end()
        return QIcon(pm)
    style = _ARROW_STYLE.get(token)
    if style is None:
        p.setPen(QPen(QColor("#b0b0b0")))
        p.drawText(3, 13, token)
        p.end()
        return QIcon(pm)
    line_kind, left_head, right_head = style
    x1, x2 = 4, 34
    if left_head:
        x1 = 13
    if right_head:
        x2 = 27
    p.setPen(pen)
    if line_kind == "dash":
        p.setPen(QPen(_ARROW_COLOR, 2, Qt.PenStyle.DashLine))
    p.drawLine(x1, cy, x2, cy)
    p.setPen(pen)
    if right_head == ">":
        p.setBrush(Qt.BrushStyle.SolidPattern)
        p.drawPolygon(QPolygon([QPoint(x2 - 1, cy), QPoint(x2 + 6, cy - 3), QPoint(x2 + 6, cy + 3)]))
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif right_head == ">>":
        p.drawLine(x2, cy, x2 + 6, cy - 3)
        p.drawLine(x2, cy, x2 + 6, cy + 3)
    elif right_head == "o":
        p.drawEllipse(x2 - 2, cy - 3, 6, 6)
    elif right_head == "x":
        p.drawLine(x2, cy - 3, x2 + 7, cy + 3)
        p.drawLine(x2, cy + 3, x2 + 7, cy - 3)
    elif right_head == ")":
        p.drawEllipse(x2 - 2, cy - 5, 10, 10)
    elif left_head == "<|":
        p.setBrush(Qt.BrushStyle.SolidPattern)
        p.drawPolygon(QPolygon([QPoint(x1 + 1, cy), QPoint(x1 - 6, cy - 3), QPoint(x1 - 6, cy + 3)]))
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif left_head == "<":
        p.drawLine(x1, cy, x1 - 6, cy - 3)
        p.drawLine(x1, cy, x1 - 6, cy + 3)
    elif left_head == "o":
        p.drawEllipse(x1 - 2, cy - 3, 6, 6)
    elif left_head == "*":
        p.setBrush(Qt.BrushStyle.SolidPattern)
        p.drawPolygon(QPolygon([QPoint(x1, cy - 3), QPoint(x1 + 3, cy), QPoint(x1, cy + 3), QPoint(x1 - 3, cy)]))
        p.setBrush(Qt.BrushStyle.NoBrush)
    p.end()
    return QIcon(pm)


class _StepCard(QWidget):
    def __init__(self, control, values=None):
        super().__init__()
        if not isinstance(values, (list, tuple)):
            values = []
        self._control = control
        spec = control._spec
        self._cols = spec["cols"]
        ncols = len(self._cols)
        row = ((values + [""] * ncols)[:ncols])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(6)
        self._widgets = {}
        self._text_fields = {}
        index_label = QLabel("")
        index_label.setFixedWidth(18)
        lay.addWidget(index_label)
        self._index_label = index_label
        for kind, col, placeholder in control._card_spec:
            label, _, default = (list(self._cols[col]) + ["", None, ""])[:3]
            cur = row[col] if (values is not None or row[col]) else default
            if kind == "shape":
                combo = QComboBox()
                combo.setIconSize(QSize(24, 18))
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
                for k in CHOICES["shape"]:
                    combo.addItem(_shape_icon(k), k)
                combo.setCurrentText(cur if cur else "Rectangle")
                combo.currentIndexChanged.connect(control._notify)
                combo.setToolTip(label)
                lay.addWidget(combo)
                self._widgets[col] = combo
            elif kind == "arrow":
                combo = QComboBox()
                combo.setIconSize(QSize(40, 16))
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
                choices = CHOICES[self._cols[col][1]]
                for tok in choices:
                    combo.addItem(_arrow_icon(tok), tok)
                combo.setCurrentText(cur if cur else (choices[0] if choices else ""))
                combo.currentIndexChanged.connect(control._notify)
                combo.setToolTip(label)
                lay.addWidget(combo)
                self._widgets[col] = combo
            elif kind == "combo":
                combo = QComboBox()
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
                choices = CHOICES[self._cols[col][1]]
                combo.addItems(choices)
                combo.setCurrentText(cur if cur else (choices[0] if choices else ""))
                combo.currentIndexChanged.connect(control._notify)
                combo.setToolTip(label)
                lay.addWidget(combo)
                self._widgets[col] = combo
            else:
                le = QLineEdit(cur if cur else "")
                ph = placeholder or label
                le.setPlaceholderText(ph)
                le.textChanged.connect(control._notify)
                le.textChanged.connect(lambda _=False, e=le, p=ph: self._autosize(e, p))
                lay.addWidget(le)
                self._widgets[col] = le
                self._text_fields[col] = le
                self._autosize(le, ph)
        chain = control._spec.get("chain")
        if chain:
            self._source_le = self._text_fields.get(chain[0])
            self._target_le = self._text_fields.get(chain[1])
        else:
            text_cols = list(self._text_fields)
            if text_cols:
                self._source_le = self._text_fields[text_cols[0]]
                self._target_le = self._text_fields[text_cols[-1]]
            else:
                self._source_le = self._target_le = None
        lay.addStretch(1)
        for symbol, tool, slot in (("▲", "Move up", lambda: control._move(self, -1)),
                                   ("▼", "Move down", lambda: control._move(self, 1)),
                                   ("✕", "Remove this step", lambda: control._remove(self))):
            btn = QToolButton()
            btn.setText(symbol)
            btn.setAutoRaise(True)
            btn.setFixedWidth(24)
            btn.setToolTip(tool)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

    def _autosize(self, edit, placeholder):
        fm = edit.fontMetrics()
        text = edit.text() or placeholder or ""
        w = fm.horizontalAdvance(text) + 26
        w = max(40, min(w, 240))
        edit.setMinimumWidth(w)
        edit.setMaximumWidth(w)

    def set_index(self, i, total):
        self._index_label.setText(str(i + 1))

    def collect(self, row):
        for kind, col, _ph in self._control._card_spec:
            w = self._widgets[col]
            if kind == "text":
                row[col] = w.text().strip()
            else:
                row[col] = w.currentText()


class _StepListControl(QWidget):
    def __init__(self, spec, on_change=None):
        super().__init__()
        self._spec = spec
        self._card_spec = spec["card"]
        self._ncols = len(spec["cols"])
        self.on_change = on_change
        self._cards = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        header = QHBoxLayout()
        add_btn = QPushButton(spec.get("add_label", "Add Step"))
        add_btn.clicked.connect(self.add_card)
        header.addWidget(add_btn)
        self.chain_check = None
        if spec.get("chain"):
            self.chain_check = QCheckBox("Connect each step to the next")
            self.chain_check.setChecked(True)
            self.chain_check.toggled.connect(self._notify)
            header.addWidget(self.chain_check)
        header.addStretch(1)
        root.addLayout(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self._cards_lay = QVBoxLayout(host)
        self._cards_lay.setContentsMargins(0, 0, 0, 0)
        self._cards_lay.setSpacing(4)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

    def _notify(self, *_):
        if self.on_change:
            self.on_change()

    def add_card(self, values=None):
        card = _StepCard(self, values)
        if card._target_le:
            card._target_le.editingFinished.connect(lambda c=card: self._chain_next(c))
        self._cards.append(card)
        self._cards_lay.addWidget(card)
        self._refresh_indexes()
        self._notify()
        return card

    def _remove(self, card):
        if card in self._cards:
            self._cards.remove(card)
            self._cards_lay.removeWidget(card)
            card.deleteLater()
            self._refresh_indexes()
            self._notify()

    def _move(self, card, delta):
        i = self._cards.index(card)
        j = i + delta
        if j < 0 or j >= len(self._cards):
            return
        self._cards[i], self._cards[j] = self._cards[j], self._cards[i]
        self._cards_lay.removeWidget(self._cards[i])
        self._cards_lay.removeWidget(self._cards[j])
        self._cards_lay.insertWidget(i, self._cards[i])
        self._cards_lay.insertWidget(j, self._cards[j])
        self._refresh_indexes()

    def _chain_next(self, card):
        if not self.chain_check or not self.chain_check.isChecked():
            return
        i = self._cards.index(card)
        if i + 1 >= len(self._cards):
            return
        nxt = self._cards[i + 1]
        if nxt._source_le and not nxt._source_le.text().strip():
            nxt._source_le.setText(card._target_le.text() if card._target_le else "")

    def _refresh_indexes(self):
        n = len(self._cards)
        for i, card in enumerate(self._cards):
            card.set_index(i, n)

    def set_rows(self, rows):
        for card in list(self._cards):
            self._cards.remove(card)
            self._cards_lay.removeWidget(card)
            card.deleteLater()
        for row in rows:
            self.add_card(list(row))
        self._refresh_indexes()

    def collect_rows(self):
        rows = []
        for card in self._cards:
            row = [""] * self._ncols
            card.collect(row)
            rows.append(row)
        return rows

    def row_count(self):
        return len(self._cards)


class MermaidEditDialog(QDialog):
    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Mermaid Diagram")
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        editor = QPlainTextEdit()
        from PyQt6.QtGui import QFontDatabase

        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(11)
        editor.setFont(font)
        editor.setPlainText(source)
        layout.addWidget(editor, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._editor = editor

    def edited_source(self):
        return self._editor.toPlainText()


class MermaidWizardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mermaid Diagram Wizard")
        self.resize(880, 640)
        self._building = False
        self.generated_source = ""

        root = QVBoxLayout(self)

        config_col = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("Diagram type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(list(SCHEMAS.keys()))
        top.addWidget(self.type_combo, 1)
        config_col.addLayout(top)

        self.options_box = QWidget()
        self.options_layout = QHBoxLayout(self.options_box)
        self.options_layout.setContentsMargins(0, 0, 0, 4)
        config_col.addWidget(self.options_box)

        self.sections_box = QWidget()
        self.sections_layout = QVBoxLayout(self.sections_box)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        config_col.addWidget(self.sections_box, 1)

        self.config_widget = QWidget()
        self.config_widget.setLayout(config_col)

        self.code_box = QPlainTextEdit()
        self.code_box.setReadOnly(True)
        self.code_box.setPlaceholderText("Generated mermaid source appears here...")
        self.preview_view = QWebEngineView()
        self.state_label = QLabel("")
        self.state_label.setStyleSheet("color: #c0392b;")
        self.state_label.hide()
        preview_col = QVBoxLayout()
        preview_col.addWidget(self.preview_view, 1)
        preview_col.addWidget(self.state_label)
        self.output_widget = QWidget()
        self.output_widget.setLayout(preview_col)

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(self.code_box)
        self.right_splitter.addWidget(self.output_widget)
        self.right_splitter.setSizes([180, 420])
        self.right_splitter.setChildrenCollapsible(False)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.config_widget)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setSizes([400, 520])
        self.main_splitter.setChildrenCollapsible(False)
        root.addWidget(self.main_splitter, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Insert")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.type_combo.currentTextChanged.connect(self._rebuild_form)

        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(400)
        self.render_timer.timeout.connect(self._render)

        self.preview_view.loadFinished.connect(self._render)
        load_web_page(self.preview_view)
        self._rebuild_form(self.type_combo.currentText())

    def _current_schema(self):
        return SCHEMAS[self.type_combo.currentText()]

    def _rebuild_form(self, _type):
        self._building = True
        schema = self._current_schema()

        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.option_widgets = {}
        for opt in schema.get("options", []):
            name, kind, choices, default = (list(opt) + [None, None, None, ""])[0:4]
            self.options_layout.addWidget(QLabel(name + ":"))
            if kind == "combo":
                cb = QComboBox()
                cb.addItems(choices)
                cb.setCurrentText(default)
                self.option_widgets[name] = cb
                cb.currentIndexChanged.connect(self._on_changed)
                self.options_layout.addWidget(cb)
            else:
                le = self._line_edit()
                le.setText(default)
                self.option_widgets[name] = le
                self.options_layout.addWidget(le)
        self.options_layout.addStretch(1)

        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        schema = self._current_schema()
        self.sections = []
        tables = schema.get("tables") or [
            {
                "title": "",
                "cols": schema["cols"],
                "default_rows": schema.get("default_rows", 2),
                "example": schema.get("example") or [],
                "view": schema.get("view"),
                "card": schema.get("card"),
                "chain": schema.get("chain"),
                "add_label": schema.get("add_label"),
            }
        ]
        for tspec in tables:
            group = QGroupBox(tspec.get("title", ""))
            lay = QVBoxLayout(group)
            example = tspec.get("example") or []
            total_rows = max(tspec.get("default_rows", 2), len(example))
            flow = _StepListControl(tspec, on_change=self._on_changed)
            lay.addWidget(flow, 1)
            self.sections_layout.addWidget(group, 1)
            for i in range(total_rows):
                flow.add_card(example[i] if i < len(example) else None)
            self.sections.append({"widget": flow, "spec": tspec})
        self._building = False
        self._render()

    def _line_edit(self):
        from PyQt6.QtWidgets import QLineEdit

        le = QLineEdit()
        le.textChanged.connect(self._on_changed)
        return le

    def set_source(self, source):
        parsed = parse_mermaid_wizard(source)
        if not parsed:
            return False
        diagram_type, options, rows_list = parsed
        self.type_combo.blockSignals(True)
        self.type_combo.setCurrentText(diagram_type)
        self.type_combo.blockSignals(False)
        self._rebuild_form(diagram_type)
        for name, val in options.items():
            w = self.option_widgets.get(name)
            if w:
                if hasattr(w, "setCurrentText"):
                    w.setCurrentText(str(val))
                elif hasattr(w, "setText"):
                    w.setText(str(val))
        for sec, table_rows in zip(self.sections, rows_list):
            w = sec["widget"]
            w.set_rows([list(r) for r in table_rows])
        self._on_changed()
        return True

    def _section_rows(self, sec):
        return sec["widget"].collect_rows()

    def build_mermaid(self):
        schema = self._current_schema()
        options = {}
        for name, w in self.option_widgets.items():
            if hasattr(w, "currentText"):
                options[name] = w.currentText()
            else:
                options[name] = w.text()
        row_sets = [self._section_rows(sec) for sec in self.sections]
        return schema["gen"](options, *row_sets)

    def _on_changed(self, *_):
        if not self._building:
            self.render_timer.start()

    def _render(self, *_):
        source = self.build_mermaid()
        self.generated_source = source
        if self.code_box.toPlainText() != source:
            self.code_box.setPlainText(source)
        push_html(self.preview_view, mermaid_fragment(source))
        self._check_render_state(12)

    def _check_render_state(self, tries):
        if not self.preview_view.page():
            return

        def on_state(state, tries=tries):
            if state == "ok":
                self.state_label.hide()
            elif state == "error":
                self.state_label.setText(
                    "Could not render this diagram. Check entity names (no spaces, commas or slashes) and relationship labels."
                )
                self.state_label.show()
            elif tries > 0:
                QTimer.singleShot(400, lambda: self._check_render_state(tries - 1))

        self.preview_view.page().runJavaScript(
            "(function(){var el=document.getElementById('content');"
            "return el ? (el.dataset.mermaidState || 'none') : 'none';})()",
            on_state,
        )

    def _on_accept(self):
        self.generated_source = self.build_mermaid()
        self.accept()