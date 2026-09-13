import html
import json
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
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
        return "(((%s)))" % label
    if kind == "Parallelogram":
        return "[/%s/]" % label
    return label


def gen_flowchart(options, rows):
    lines = ["flowchart " + options.get("Direction", "TB")]
    ids = {}

    def node(kind, label):
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


SCHEMAS = {
    "Flowchart": {
        "options": [("Direction", "combo", ["TB", "LR", "BT", "RL"], "TB")],
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
    js = "window.mermaidRender(%s);" % json.dumps(fragment)
    view.page().runJavaScript(js)


def mermaid_fragment(source):
    return '<pre class="mermaid">' + html.escape(source) + "</pre>"


class MermaidWizardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mermaid Diagram Wizard")
        self.resize(880, 640)
        self._building = False
        self.generated_source = ""

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Diagram type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(list(SCHEMAS.keys()))
        top.addWidget(self.type_combo, 1)
        root.addLayout(top)

        self.options_box = QWidget()
        self.options_layout = QHBoxLayout(self.options_box)
        self.options_layout.setContentsMargins(0, 0, 0, 4)
        root.addWidget(self.options_box)

        self.sections_box = QWidget()
        self.sections_layout = QVBoxLayout(self.sections_box)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.sections_box, 1)

        mid = QHBoxLayout()
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
        mid.addWidget(self.code_box, 1)
        mid.addLayout(preview_col, 2)
        root.addLayout(mid, 2)

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
            }
        ]
        for tspec in tables:
            group = QGroupBox(tspec.get("title", ""))
            lay = QVBoxLayout(group)
            tbl = QTableWidget()
            tbl.verticalHeader().setVisible(False)
            tbl.clear()
            tbl.setColumnCount(len(tspec["cols"]))
            tbl.setRowCount(0)
            tbl.setHorizontalHeaderLabels([c[0] for c in tspec["cols"]])
            tbl.itemChanged.connect(self._on_changed)
            tbl.cellChanged.connect(self._on_changed)
            hb = QHBoxLayout()
            add_btn = QPushButton("Add Row")
            remove_btn = QPushButton("Remove Row")
            add_btn.clicked.connect(lambda _=False, t=tbl, s=tspec: self._add_row(t, s))
            remove_btn.clicked.connect(lambda _=False, t=tbl: self._remove_row(t))
            hb.addWidget(add_btn)
            hb.addWidget(remove_btn)
            hb.addStretch(1)
            lay.addWidget(tbl)
            lay.addLayout(hb)
            self.sections_layout.addWidget(group)
            example = tspec.get("example") or []
            total_rows = max(tspec.get("default_rows", 2), len(example))
            for i in range(total_rows):
                self._add_row(tbl, tspec, example[i] if i < len(example) else None)
            tbl.resizeColumnsToContents()
            self.sections.append({"table": tbl, "spec": tspec})
        self.sections_layout.addStretch(1)
        self._building = False
        self._render()

    def _line_edit(self):
        from PyQt6.QtWidgets import QLineEdit

        le = QLineEdit()
        le.textChanged.connect(self._on_changed)
        return le

    def _add_row(self, table, spec, values=None):
        row = table.rowCount()
        table.insertRow(row)
        for col, (_, kind, default) in enumerate(spec["cols"]):
            val = values[col] if values and col < len(values) else default
            if kind in CHOICES:
                cb = QComboBox()
                cb.addItems(CHOICES[kind])
                cb.setCurrentText(val)
                cb.currentIndexChanged.connect(self._on_changed)
                table.setCellWidget(row, col, cb)
            else:
                item = QTableWidgetItem(val)
                table.setItem(row, col, item)

    def _remove_row(self, table):
        if table.rowCount() > 1:
            table.removeRow(table.currentRow() if table.currentRow() >= 0 else table.rowCount() - 1)
            self._on_changed()

    def _collect_rows(self, table):
        rows = []
        for r in range(table.rowCount()):
            row = []
            for c in range(table.columnCount()):
                w = table.cellWidget(r, c)
                if isinstance(w, QComboBox):
                    row.append(w.currentText())
                else:
                    item = table.item(r, c)
                    row.append(item.text() if item else "")
            rows.append(row)
        return rows

    def build_mermaid(self):
        schema = self._current_schema()
        options = {}
        for name, w in self.option_widgets.items():
            if hasattr(w, "currentText"):
                options[name] = w.currentText()
            else:
                options[name] = w.text()
        row_sets = [self._collect_rows(sec["table"]) for sec in self.sections]
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
            "document.getElementById('content').dataset.mermaidState || 'none'", on_state
        )

    def _on_accept(self):
        self.generated_source = self.build_mermaid()
        self.accept()