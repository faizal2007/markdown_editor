import json
import re
import sys

import markdown
from PyQt6.QtCore import QPointF, QRectF, QSettings, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QStyle,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from markdown_edit import CodeEditor, MarkdownHighlighter
from mermaid_wizard import (
    MERMAID_HEADS,
    MermaidWizardDialog,
    load_web_page,
    push_html,
)


def make_text_icon(symbol, bold=False, italic=False, mono=False):
    pm = QPixmap(28, 28)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    f = QFont("Segoe UI", 13)
    f.setBold(bold)
    f.setItalic(italic)
    if mono:
        f = QFont("Consolas", 12)
    p.setFont(f)
    p.setPen(QColor("#333333"))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, symbol)
    p.end()
    return QIcon(pm)


def make_table_icon():
    pm = QPixmap(28, 28)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(4, 5, 20, 18)
    x1 = rect.x() + rect.width() / 3
    x2 = rect.x() + 2 * rect.width() / 3
    y1 = rect.y() + rect.height() / 3
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#cbd5e1"))
    p.drawRect(QRectF(rect.x(), rect.y(), rect.width(), rect.height() / 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    pen = QPen(QColor("#333333"))
    pen.setWidth(2)
    p.setPen(pen)
    p.drawRect(rect)
    p.drawLine(QPointF(x1, rect.y()), QPointF(x1, rect.bottom()))
    p.drawLine(QPointF(x2, rect.y()), QPointF(x2, rect.bottom()))
    p.drawLine(QPointF(rect.x(), y1), QPointF(rect.right(), y1))
    p.end()
    return QIcon(pm)


def make_mermaid_icon():
    pm = QPixmap(28, 28)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#333333"))
    pen.setWidth(2)
    p.setPen(pen)
    p.setBrush(QColor("#cbd5e1"))
    p.drawRoundedRect(QRectF(3, 7, 9, 14), 3, 3)
    p.drawRoundedRect(QRectF(16, 7, 9, 14), 3, 3)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(12, 14), QPointF(16, 14))
    p.drawLine(QPointF(13, 11), QPointF(16, 14))
    p.drawLine(QPointF(13, 17), QPointF(16, 14))
    p.end()
    return QIcon(pm)


MARKDOWN_EXTENSIONS = ["fenced_code", "tables", "codehilite", "toc"]
CODEHILITE_CONFIG = {
    "codehilite": {
        "noclasses": True,
        "guess_lang": False,
        "pygments_style": "default",
    }
}

_CODEHILITE_RE = re.compile(
    r'<div class="codehilite"[^>]*><pre[^>]*><span></span><code>(.*?)</code></pre></div>',
    re.DOTALL,
)
_MERMAID_FENCE_RE = re.compile(
    r'<pre><code class="language-mermaid">(.*?)</code></pre>',
    re.DOTALL,
)


def _preview_transform(m):
    head = m.group(1).lstrip().split(None, 1)
    if head and head[0] in MERMAID_HEADS:
        return '<pre class="mermaid">' + m.group(1) + "</pre>"
    return m.group(0)


class MarkdownEditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_path = None
        self.untitled_count = 0
        self._mode = 2

        self.editor = CodeEditor()
        self.highlighter = MarkdownHighlighter(self.editor.document())

        self.preview = QWebEngineView()
        self._web_ready = False
        self._pending_html = None
        load_web_page(self.preview)
        self.preview.loadFinished.connect(self._on_web_loaded)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([400, 400])

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(300)
        self.render_timer.timeout.connect(self.render_preview)

        self.editor.textChanged.connect(self.render_timer.start)

    def mode(self):
        return self._mode

    def set_mode(self, mode):
        self._mode = mode
        edit = mode == 0 or mode == 2
        preview = mode == 1 or mode == 2
        self.editor.setVisible(edit)
        self.preview.setVisible(preview)
        if preview:
            self.render_preview()

    def _on_web_loaded(self, ok):
        if ok:
            self._web_ready = True
            if self._pending_html is not None:
                html = self._pending_html
                self._pending_html = None
                push_html(self.preview, html)

    def render_preview(self):
        if not self.isVisible():
            return
        html = markdown.markdown(
            self.editor.toPlainText(),
            extensions=MARKDOWN_EXTENSIONS,
            extension_configs=CODEHILITE_CONFIG,
        )
        html = _CODEHILITE_RE.sub(_preview_transform, html)
        html = _MERMAID_FENCE_RE.sub(
            lambda m: '<pre class="mermaid">' + m.group(1) + "</pre>", html
        )
        if self._web_ready:
            push_html(self.preview, html)
        else:
            self._pending_html = html

    def set_text(self, text):
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
        self.render_preview()

    def text(self):
        return self.editor.toPlainText()

    def set_file_path(self, path):
        self.file_path = path

    def set_highlight_enabled(self, enabled):
        if enabled:
            self.highlighter.setDocument(self.editor.document())
        else:
            self.highlighter.setDocument(None)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Markdown Editor")
        self.resize(1000, 700)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.setCentralWidget(self.tabs)

        self.mode_index = 2

        self.settings = QSettings("MarkdownEditor", "MarkdownEditor")

        self._create_actions()
        self._create_format_actions()
        self._create_format_bar()
        self._create_toolbar()
        self._create_menu()

        self.central = QWidget()
        self.root_layout = QVBoxLayout(self.central)
        self.root_layout.setContentsMargins(4, 4, 4, 0)
        self.root_layout.setSpacing(4)
        self.root_layout.addWidget(self.format_box)
        self.root_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(self.central)

        self._load_session()

        self.statusBar().showMessage("Ready")

    def _create_actions(self):
        self.action_new = QAction("&New", self)
        self.action_new.setShortcut(QKeySequence.StandardKey.New)
        self.action_new.triggered.connect(self.new_tab)

        self.action_open = QAction("&Open...", self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self.open_file)

        self.action_save = QAction("&Save", self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self.save_file)

        self.action_save_as = QAction("Save &As...", self)
        self.action_save_as.triggered.connect(self.save_file_as)

        self.action_mode_edit = QAction("Edit", self)
        self.action_mode_edit.setCheckable(True)
        self.action_mode_edit.triggered.connect(lambda: self.set_mode(0))

        self.action_mode_preview = QAction("Preview", self)
        self.action_mode_preview.setCheckable(True)
        self.action_mode_preview.triggered.connect(lambda: self.set_mode(1))

        self.action_mode_split = QAction("Split", self)
        self.action_mode_split.setCheckable(True)
        self.action_mode_split.triggered.connect(lambda: self.set_mode(2))

        self.action_group = [
            self.action_mode_edit,
            self.action_mode_preview,
            self.action_mode_split,
        ]
        self.action_mode_split.setChecked(True)

    def _create_format_actions(self):
        self.action_bold = QAction("&Bold", self)
        self.action_bold.setShortcut(QKeySequence.StandardKey.Bold)
        self.action_bold.setIcon(make_text_icon("B", bold=True))
        self.action_bold.setToolTip("Bold (Ctrl+B)")
        self.action_bold.triggered.connect(self._format_bold)

        self.action_italic = QAction("&Italic", self)
        self.action_italic.setShortcut(QKeySequence.StandardKey.Italic)
        self.action_italic.setIcon(make_text_icon("I", italic=True))
        self.action_italic.setToolTip("Italic (Ctrl+I)")
        self.action_italic.triggered.connect(self._format_italic)

        self.action_code = QAction("Inline &Code", self)
        self.action_code.setIcon(make_text_icon("`", mono=True))
        self.action_code.setToolTip("Inline Code")
        self.action_code.triggered.connect(self._format_code)

        self.action_link = QAction("&Link", self)
        self.action_link.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon)
        )
        self.action_link.setToolTip("Link")
        self.action_link.triggered.connect(self._format_link)

        self.action_h1 = QAction("Heading &1", self)
        self.action_h1.setIcon(make_text_icon("H1"))
        self.action_h1.setToolTip("Heading 1")
        self.action_h1.triggered.connect(lambda: self._format_header(1))

        self.action_h2 = QAction("Heading &2", self)
        self.action_h2.setIcon(make_text_icon("H2"))
        self.action_h2.setToolTip("Heading 2")
        self.action_h2.triggered.connect(lambda: self._format_header(2))

        self.action_bullet = QAction("Bullet &List", self)
        self.action_bullet.setIcon(make_text_icon("•≡"))
        self.action_bullet.setToolTip("Bullet List")
        self.action_bullet.triggered.connect(
            lambda: self._format_line_prefix("- ")
        )

        self.action_numlist = QAction("&Numbered List", self)
        self.action_numlist.setIcon(make_text_icon("1·2"))
        self.action_numlist.setToolTip("Numbered List")
        self.action_numlist.triggered.connect(self._format_numlist)

        self.action_quote = QAction("&Quote", self)
        self.action_quote.setIcon(make_text_icon("“", italic=True))
        self.action_quote.setToolTip("Quote")
        self.action_quote.triggered.connect(lambda: self._format_line_prefix("> "))

        self.action_codeblock = QAction("Code &Block", self)
        self.action_codeblock.setIcon(make_text_icon("{ }", mono=True))
        self.action_codeblock.setToolTip("Code Block")
        self.action_codeblock.triggered.connect(self._format_codeblock)

        self.action_table = QAction("&Table", self)
        self.action_table.setIcon(make_table_icon())
        self.action_table.setToolTip("Table")
        self.action_table.triggered.connect(self._format_table)

        self.action_mermaid = QAction("&Mermaid...", self)
        self.action_mermaid.setIcon(make_mermaid_icon())
        self.action_mermaid.setToolTip("Mermaid Diagram Wizard")
        self.action_mermaid.triggered.connect(self._format_mermaid)

        self.action_highlight = QAction("Syntax &Highlighting", self)
        self.action_highlight.setCheckable(True)
        self.action_highlight.setChecked(True)
        self.action_highlight.toggled.connect(self._toggle_highlight)

        self.action_autolist = QAction("&Auto-extend Lists", self)
        self.action_autolist.setCheckable(True)
        self.action_autolist.setChecked(True)
        self.action_autolist.toggled.connect(self._toggle_autolist)

        self.action_smartchars = QAction("&Smart Markdown Chars", self)
        self.action_smartchars.setCheckable(True)
        self.action_smartchars.setChecked(True)
        self.action_smartchars.toggled.connect(self._toggle_smartchars)

        self.format_actions = [
            self.action_bold,
            self.action_italic,
            self.action_code,
            self.action_link,
            self.action_h1,
            self.action_h2,
            self.action_bullet,
            self.action_numlist,
            self.action_quote,
            self.action_codeblock,
            self.action_table,
            self.action_mermaid,
        ]

    def _create_format_bar(self):
        self.format_box = QFrame()
        self.format_box.setObjectName("formatBox")
        self.format_box.setStyleSheet(
            "#formatBox { border: 1px solid #c6ccd2; border-radius: 4px; "
            "background: #f4f5f7; }"
        )
        fb = QToolBar()
        fb.setMovable(False)
        fb.setFloatable(False)
        fb.setIconSize(QSize(18, 18))
        fb.setStyleSheet(
            "QToolBar { border: none; background: transparent; padding: 0px; margin: 0px; spacing: 0px; }"
            "QToolButton { padding: 2px 3px; border: none; border-radius: 3px; }"
            "QToolButton:hover { background: #e2e6ea; }"
            "QToolButton:pressed { background: #d3d9df; }"
        )
        for action in self.format_actions:
            fb.addAction(action)
        box_layout = QHBoxLayout(self.format_box)
        box_layout.setContentsMargins(4, 3, 4, 3)
        box_layout.setSpacing(0)
        box_layout.addWidget(fb)
        box_layout.addStretch(1)

    def _create_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.addAction(self.action_new)
        tb.addAction(self.action_open)
        tb.addAction(self.action_save)
        tb.addSeparator()

        tb.addAction(self.action_mode_edit)
        tb.addAction(self.action_mode_preview)
        tb.addAction(self.action_mode_split)

    def _create_menu(self):
        m = self.menuBar()
        file_menu = m.addMenu("&File")
        file_menu.addAction(self.action_new)
        file_menu.addAction(self.action_open)
        file_menu.addSeparator()
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)

        view_menu = m.addMenu("&View")
        view_menu.addAction(self.action_mode_edit)
        view_menu.addAction(self.action_mode_preview)
        view_menu.addAction(self.action_mode_split)
        view_menu.addSeparator()
        view_menu.addAction(self.action_highlight)
        view_menu.addAction(self.action_autolist)
        view_menu.addAction(self.action_smartchars)

        format_menu = m.addMenu("F&ormat")
        format_menu.addAction(self.action_bold)
        format_menu.addAction(self.action_italic)
        format_menu.addAction(self.action_code)
        format_menu.addAction(self.action_link)
        format_menu.addSeparator()
        format_menu.addAction(self.action_h1)
        format_menu.addAction(self.action_h2)
        format_menu.addAction(self.action_bullet)
        format_menu.addAction(self.action_numlist)
        format_menu.addAction(self.action_quote)
        format_menu.addAction(self.action_codeblock)
        format_menu.addAction(self.action_table)
        format_menu.addAction(self.action_mermaid)

    def set_mode(self, mode):
        self.mode_index = mode
        for i, action in enumerate(self.action_group):
            action.setChecked(i == mode)
        editor = self.current_editor()
        if editor:
            editor.set_mode(mode)

    def current_editor(self):
        widget = self.tabs.currentWidget()
        if isinstance(widget, MarkdownEditorWidget):
            return widget
        return None

    def _format_bold(self):
        self._wrap_current("**")

    def _format_italic(self):
        self._wrap_current("*")

    def _format_code(self):
        self._wrap_current("`")

    def _format_link(self):
        self._wrap_current("[", "](url)")

    def _format_header(self, level):
        editor = self.current_editor()
        if editor:
            editor.editor.insert_header(level)

    def _format_line_prefix(self, prefix):
        editor = self.current_editor()
        if editor:
            editor.editor.toggle_line_prefix(prefix)

    def _format_numlist(self):
        editor = self.current_editor()
        if not editor:
            return
        cursor = editor.editor.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText().replace("\u2029", "\n")
        else:
            text = cursor.block().text()
        rows = []
        n = 1
        for line in text.split("\n"):
            m = re.match(r"^(\s*)(\d+)([.)])(\s+)", line)
            if m:
                rows.append(m.group(1) + str(n) + m.group(3) + m.group(4) + line[m.end():])
            else:
                rows.append(str(n) + ". " + line)
            n += 1
        cursor.beginEditBlock()
        if cursor.hasSelection():
            cursor.insertText("\n".join(rows))
        else:
            start = cursor.block().position()
            cursor.setPosition(start)
            cursor.setPosition(
                start + len(cursor.block().text()), QTextCursor.MoveMode.KeepAnchor
            )
            cursor.insertText("\n".join(rows))
        cursor.endEditBlock()

    def _format_codeblock(self):
        editor = self.current_editor()
        if editor:
            editor.editor.insert_fence_block()

    def _format_table(self):
        editor = self.current_editor()
        if editor:
            editor.editor.insert_table()

    def _format_mermaid(self):
        dlg = MermaidWizardDialog(self)
        if dlg.exec():
            editor = self.current_editor()
            if editor and dlg.generated_source:
                editor.editor.insert_mermaid(dlg.generated_source)

    def _wrap_current(self, left, right=None):
        editor = self.current_editor()
        if editor:
            editor.editor.wrap_selection(left, right)

    def _toggle_highlight(self, checked):
        editor = self.current_editor()
        if editor:
            editor.set_highlight_enabled(checked)

    def _toggle_autolist(self, checked):
        editor = self.current_editor()
        if editor:
            editor.editor.lists_enabled = checked

    def _toggle_smartchars(self, checked):
        editor = self.current_editor()
        if editor:
            editor.editor.smart_enabled = checked

    def on_tab_changed(self, index):
        editor = self.tabs.widget(index)
        if editor:
            editor.set_mode(self.mode_index)
            editor.set_highlight_enabled(self.action_highlight.isChecked())
            editor.editor.lists_enabled = self.action_autolist.isChecked()
            editor.editor.smart_enabled = self.action_smartchars.isChecked()
            self._sync_title(editor)

    def _sync_title(self, editor):
        name = editor.file_path or "Untitled-{}".format(editor.untitled_count)
        self.setWindowTitle("{} - Markdown Editor".format(name))

    def new_tab(self):
        editor = MarkdownEditorWidget()
        editor.untitled_count = len(self.tabs)
        index = self.tabs.addTab(editor, "Untitled-{}".format(editor.untitled_count))
        self.tabs.setCurrentIndex(index)
        self._sync_title(editor)
        self.tabs.currentWidget().editor.setFocus()
        return editor

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Markdown File", "", "Markdown Files (*.md *.markdown *.txt);;All Files (*.*)"
        )
        if not path:
            return
        self.open_path(path)

    def open_path(self, path):
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if widget.file_path == path:
                self.tabs.setCurrentIndex(i)
                return widget
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            self.statusBar().showMessage("Failed to open: {}".format(e))
            return None
        editor = self.new_tab()
        editor.set_file_path(path)
        editor.set_text(text)
        self.tabs.setTabText(self.tabs.indexOf(editor), _basename(path))
        self._sync_title(editor)
        self.statusBar().showMessage("Opened {}".format(path))
        return editor

    def _load_session(self):
        files = self.settings.value("files")
        if files:
            for path in files:
                self.open_path(path)
            active = self.settings.value("active")
            if active is not None and int(active) < self.tabs.count():
                self.tabs.setCurrentIndex(int(active))
        else:
            self.new_tab()

    def closeEvent(self, event):
        files = [
            self.tabs.widget(i).file_path
            for i in range(self.tabs.count())
            if self.tabs.widget(i).file_path is not None
        ]
        self.settings.setValue("files", files)
        self.settings.setValue("active", self.tabs.currentIndex())
        event.accept()

    def save_file(self):
        editor = self.current_editor()
        if not editor:
            return False
        if editor.file_path is None:
            return self.save_file_as()
        return self._write(editor)

    def save_file_as(self):
        editor = self.current_editor()
        if not editor:
            return False
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Markdown File", "", "Markdown Files (*.md);;All Files (*.*)"
        )
        if not path:
            return False
        editor.set_file_path(path)
        self.tabs.setTabText(self.tabs.indexOf(editor), _basename(path))
        self._sync_title(editor)
        return self._write(editor)

    def _write(self, editor):
        try:
            with open(editor.file_path, "w", encoding="utf-8") as f:
                f.write(editor.text())
        except Exception as e:
            self.statusBar().showMessage("Failed to save: {}".format(e))
            return False
        self.statusBar().showMessage("Saved {}".format(editor.file_path))
        return True

    def close_tab(self, index):
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        widget.deleteLater()


def _basename(path):
    return path.replace("\\", "/").rsplit("/", 1)[-1]


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("Markdown Editor")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())