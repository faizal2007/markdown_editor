import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QSyntaxHighlighter,
    QTextBlockUserData,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import QPlainTextEdit

ULIST_RE = re.compile(r"^([ \t]*)([-*+])([ \t]+)(.*)$")
TASK_RE = re.compile(r"^([ \t]*)([-*+])([ \t]+)\[( |x|X)\]([ \t]+)(.*)$")
OLIST_RE = re.compile(r"^([ \t]*)(\d+)([.)])([ \t]+)(.*)$")
QUOTE_RE = re.compile(r"^([ \t]*)(>)([ \t]?)(.*)$")

_CODE = r"(?P<code>`[^`\n]+`)"
_IMAGE = r"(?P<image>!\[[^\]]*\]\([^)\s]+\))"
_LINK = r"(?P<link>(?<!!)\[[^\]]*\]\([^)\s]+\))"
_BOTH = r"(?P<both>\*\*\*[^*\n]+?\*\*\*)"
_BOLD = r"(?P<bold>\*\*[^*\n]+?\*\*)"
_STRIKE = r"(?P<strike>~~[^~\n]+?~~)"
_ITALIC = r"(?P<italic>(?<!\*)\*[^*\n]+?\*(?!\*))"
INLINE_RE = re.compile(
    "|".join([_CODE, _IMAGE, _LINK, _BOTH, _BOLD, _STRIKE, _ITALIC])
)

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
ATX_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")
HR_RE = re.compile(r"^ {0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$")
INDENT_RE = re.compile(r"^(    |\t)")

STATE_FENCE = 1
STATE_INDENT = 2

_CODE_TOKEN_COLORS = {
    "Token.Keyword": "#d73a49",
    "Token.Keyword.Constant": "#d73a49",
    "Token.Keyword.Declaration": "#d73a49",
    "Token.Keyword.Type": "#cf222e",
    "Token.Name.Builtin": "#005cc5",
    "Token.Name.Builtin.Pseudo": "#005cc5",
    "Token.Name.Class": "#6f42c1",
    "Token.Name.Decorator": "#d73a49",
    "Token.Name.Exception": "#d73a49",
    "Token.Name.Function": "#6f42c1",
    "Token.Name.Namespace": "#005cc5",
    "Token.Name.Tag": "#22863a",
    "Token.Name.Attribute": "#6f42c1",
    "Token.Name.Constant": "#0550ae",
    "Token.Literal.String": "#0a3069",
    "Token.Literal.String.Doc": "#0a3069",
    "Token.Literal.String.Regex": "#0a3069",
    "Token.Literal.String.Char": "#0a3069",
    "Token.Literal.Number": "#0550ae",
    "Token.Literal.Number.Integer": "#0550ae",
    "Token.Literal.Number.Float": "#0550ae",
    "Token.Comment": "#6a737d",
    "Token.Comment.Preproc": "#6a737d",
    "Token.Operator": "#cf222e",
    "Token.Operator.Word": "#d73a49",
    "Token.Punctuation": "#24292e",
    "Token.Error": "#cf222e",
}


def _code_token_color(ttype):
    current = ttype
    while current is not None:
        key = str(current)
        if key in _CODE_TOKEN_COLORS:
            return _CODE_TOKEN_COLORS[key]
        current = getattr(current, "parent", None)
    return "#24292e"


def _code_token_bold(ttype):
    key = str(ttype)
    return key == "Token.Keyword" or key == "Token.Keyword.Type"


class CodeInfo(QTextBlockUserData):
    def __init__(self, lang):
        super().__init__()
        self.lang = lang


class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, document=None):
        super().__init__(document)
        self._fence_char = None
        self._fence_len = 0
        self._close_re = None
        self._prev_text = ""
        self._lexer_cache = {}
        self._token_fmts = {}

        def fmt(color, bold=False, italic=False, bg=None, mono=False, strike=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            if italic:
                f.setFontItalic(True)
            if strike:
                f.setFontStrikeOut(True)
            if bg:
                f.setBackground(QColor(bg))
            if mono:
                f.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            return f

        self.f_heading = fmt("#7000ff", bold=True)
        self.f_bold = fmt("#c2255c", bold=True)
        self.f_italic = fmt("#1971c2", italic=True)
        self.f_strike = fmt("#868e96", strike=True)
        self.f_both = fmt("#c2255c", bold=True, italic=True)
        self.f_code = fmt("#e8590c", bg="#fff4e6", mono=True)
        self.f_inline_code = fmt("#d9480f", bg="#fff4e6", mono=True)
        self.f_link = fmt("#0c8599")
        self.f_image = fmt("#2b8a3e")
        self.f_quote = fmt("#868e96", italic=True)
        self.f_list = fmt("#6741d9", bold=True)
        self.f_task = fmt("#2b8a3e", bold=True)
        self.f_hr = fmt("#adb5bd")
        self.f_marker = fmt("#868e96", bold=True)
        self.f_plain = QTextCharFormat()

    def highlightBlock(self, text):
        self.setFormat(0, len(text), self.f_plain)
        pstate = self.previousBlockState()

        if pstate == STATE_FENCE and self._close_re:
            if self._close_re.match(text):
                self.setFormat(0, len(text), self.f_code)
                self.setCurrentBlockState(-1)
                self._fence_char = None
                self._fence_len = 0
                self._close_re = None
                self._prev_text = text
                return
            self.setFormat(0, len(text), self.f_code)
            self._highlight_fence_content(text)
            self.setCurrentBlockState(STATE_FENCE)
            self._prev_text = text
            return

        if pstate == STATE_FENCE:
            self._fence_char = None
            self._fence_len = 0
            self._close_re = None

        if text.strip() == "":
            self.setCurrentBlockState(STATE_INDENT if pstate == STATE_INDENT else -1)
            self._prev_text = text
            return

        m = FENCE_RE.match(text)
        if m:
            marker = m.group(1)
            self.setFormat(0, len(text), self.f_code)
            self._fence_char = marker[0]
            self._fence_len = len(marker)
            self._close_re = re.compile(
                r"^[ \t]*" + re.escape(marker[0]) + ("{%d,}" % len(marker))
            )
            lang = ""
            rest = text[m.end():].strip()
            if rest:
                lang = rest.split()[0]
            self.currentBlock().setUserData(CodeInfo(lang))
            self.setCurrentBlockState(STATE_FENCE)
            self._prev_text = text
            return

        m = INDENT_RE.match(text)
        if m and (pstate == STATE_INDENT or self._prev_text.strip() == ""):
            self.setFormat(0, len(text), self.f_code)
            self.setCurrentBlockState(STATE_INDENT)
            self._prev_text = text
            return

        m = ATX_RE.match(text)
        if m:
            self.setFormat(m.start(1), m.end(1), self.f_marker)
            rest_start = m.end(1)
            self.highlight_inline(text, rest_start, self.f_heading)
            self.setCurrentBlockState(-1)
            self._prev_text = text
            return

        if HR_RE.match(text):
            self.setFormat(0, len(text), self.f_hr)
            self.setCurrentBlockState(-1)
            self._prev_text = text
            return

        m = QUOTE_RE.match(text)
        if m:
            end = m.end(2)
            self.setFormat(0, end, self.f_marker)
            self.highlight_inline(text, end, self.f_quote)
            self.setCurrentBlockState(-1)
            self._prev_text = text
            return

        m = TASK_RE.match(text)
        if m:
            self.setFormat(0, m.end(1), self.f_list)
            self.setFormat(m.start(2), m.end(2), self.f_list)
            self.setFormat(m.start(4), m.end(4), self.f_task)
            self.highlight_inline(text, m.end(5), self.f_plain)
            self.setCurrentBlockState(-1)
            self._prev_text = text
            return

        m = ULIST_RE.match(text)
        if m:
            self.setFormat(0, m.end(2), self.f_list)
            self.highlight_inline(text, m.end(3), self.f_plain)
            self.setCurrentBlockState(-1)
            self._prev_text = text
            return

        m = OLIST_RE.match(text)
        if m:
            self.setFormat(0, m.end(2), self.f_list)
            self.highlight_inline(text, m.end(4), self.f_plain)
            self.setCurrentBlockState(-1)
            self._prev_text = text
            return

        self.highlight_inline(text, 0, self.f_plain)
        self.setCurrentBlockState(-1)
        self._prev_text = text

    def _highlight_fence_content(self, text):
        opener = self._fence_opener()
        lang = opener.userData().lang if opener is not None else ""
        lexer = self._get_lexer(lang) if lang else None
        if lexer is None:
            return

        code_parts = []
        b = opener.next()
        doc = self.document()
        while b.isValid() and b != doc.end():
            t = b.text()
            if self._close_re and self._close_re.match(t):
                break
            code_parts.append(t)
            b = b.next()
        code = "\n".join(code_parts)
        if not code:
            return

        try:
            tokens = list(lexer.get_tokens_unprocessed(code))
        except Exception:
            return

        code_start = opener.position() + len(opener.text()) + 1
        line_start = self.currentBlock().position() - code_start
        line_len = len(text)
        line_end = line_start + line_len
        for idx, ttype, value in tokens:
            tstart = idx
            tend = idx + len(value)
            if tend <= line_start or tstart >= line_end:
                continue
            rel = max(tstart, line_start) - line_start
            length = min(tend, line_end) - max(tstart, line_start)
            if length > 0:
                self.setFormat(rel, length, self._token_format(ttype))

    def _fence_opener(self):
        b = self.currentBlock()
        while b.isValid():
            ud = b.userData()
            if isinstance(ud, CodeInfo):
                return b
            b = b.previous()
        return None

    def _get_lexer(self, lang):
        if lang in self._lexer_cache:
            return self._lexer_cache[lang]
        try:
            from pygments.lexers import get_lexer_by_name
            from pygments.util import ClassNotFound
        except ImportError:
            self._lexer_cache[lang] = None
            return None
        try:
            lexer = get_lexer_by_name(lang, stripnl=False)
        except ClassNotFound:
            lexer = None
        self._lexer_cache[lang] = lexer
        return lexer

    def _token_format(self, ttype):
        key = str(ttype)
        if key not in self._token_fmts:
            f = QTextCharFormat()
            f.setForeground(QColor(_code_token_color(ttype)))
            if _code_token_bold(ttype):
                f.setFontWeight(QFont.Weight.Bold)
            self._token_fmts[key] = f
        return self._token_fmts[key]

    def highlight_inline(self, text, start, base_fmt):
        self.setFormat(start, len(text) - start, base_fmt)
        for m in INLINE_RE.finditer(text, start):
            kind = m.lastgroup
            if kind in ("bold", "both"):
                self.setFormat(m.start(), m.end() - m.start(), self.f_bold if kind == "bold" else self.f_both)
            elif kind == "italic":
                self.setFormat(m.start(), m.end() - m.start(), self.f_italic)
            elif kind == "strike":
                self.setFormat(m.start(), m.end() - m.start(), self.f_strike)
            elif kind == "code":
                self.setFormat(m.start(), m.end() - m.start(), self.f_inline_code)
            elif kind == "link":
                self.setFormat(m.start(), m.end() - m.start(), self.f_link)
            elif kind == "image":
                self.setFormat(m.start(), m.end() - m.start(), self.f_image)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(11)
        self.setFont(font)
        self.lists_enabled = True
        self.smart_enabled = True

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.lists_enabled and self._continue_block():
                return
        elif event.text() and event.text()[0] in "*`~":
            if self.smart_enabled and self._smart_char(event.text()[0]):
                return
        super().keyPressEvent(event)

    def _continue_block(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        block = cursor.block()
        text = block.text()
        col = cursor.positionInBlock()

        m = TASK_RE.match(text)
        if m:
            marker_end = m.end(5)
            if col < marker_end:
                return False
            tail = text[col:]
            if not m.group(6).strip() and not tail.strip():
                cont = m.group(1)
            else:
                cont = "%s%s%s[%s]%s" % (
                    m.group(1), m.group(2), m.group(3), m.group(4), m.group(5),
                )
            return self._insert_continuation(cursor, cont)

        m = ULIST_RE.match(text)
        if m:
            marker_end = m.end(3)
            if col < marker_end:
                return False
            tail = text[col:]
            if not m.group(4).strip() and not tail.strip():
                cont = m.group(1)
            else:
                cont = "%s%s " % (m.group(1), m.group(2))
            return self._insert_continuation(cursor, cont)

        m = OLIST_RE.match(text)
        if m:
            marker_end = m.end(4)
            if col < marker_end:
                return False
            tail = text[col:]
            if not m.group(5).strip() and not tail.strip():
                cont = m.group(1)
            else:
                n = int(m.group(2)) + 1
                cont = "%s%d%s " % (m.group(1), n, m.group(3))
            return self._insert_continuation(cursor, cont)

        m = QUOTE_RE.match(text)
        if m:
            marker_end = m.end(3) if m.group(3) else m.end(2)
            if col < marker_end:
                return False
            tail = text[col:]
            if not m.group(4).strip() and not tail.strip():
                cont = m.group(1)
            else:
                cont = "%s> " % m.group(1)
            return self._insert_continuation(cursor, cont)

        return False

    def _insert_continuation(self, cursor, cont):
        cursor.beginEditBlock()
        cursor.insertText("\n" + cont)
        cursor.endEditBlock()
        return True

    def _smart_char(self, c):
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        block = cursor.block()
        text = block.text()
        col = cursor.positionInBlock()
        before = text[col - 1] if col > 0 else ""
        before2 = text[col - 2] if col > 1 else ""
        after = text[col] if col < len(text) else ""

        if c == "*":
            if before != "*":
                if after == "*":
                    return self._skip_char()
                return False
            if after == "*" or (before2 and (before2.isalnum())):
                return False
            cursor.insertText("***")
            cur = self.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.Left)
            cur.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cur)
            return True

        if c == "`":
            if before == "`" or after == "`":
                if after == "`" and before != "`":
                    return self._skip_char()
                return False
            cursor.insertText("``")
            cur = self.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cur)
            return True

        if c == "~":
            if before != "~":
                if after == "~":
                    return self._skip_char()
                return False
            if after == "~" or (before2 and before2.isalnum()):
                return False
            cursor.insertText("~~~")
            cur = self.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.Left)
            cur.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cur)
            return True

        return False

    def _skip_char(self):
        cursor = self.textCursor()
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.KeepAnchor,
            1,
        )
        cursor.removeSelectedText()
        return True

    def wrap_selection(self, left, right=None):
        right = left if right is None else right
        cursor = self.textCursor()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            sel = cursor.selectedText().replace("\u2029", "\n")
            cursor.beginEditBlock()
            cursor.insertText(left + sel + right)
            cursor.setPosition(start + len(left))
            cursor.setPosition(
                start + len(left) + len(sel), QTextCursor.MoveMode.KeepAnchor
            )
            cursor.endEditBlock()
            self.setTextCursor(cursor)
        else:
            cursor.insertText(left + right)
            cursor.movePosition(
                QTextCursor.MoveOperation.Left,
                QTextCursor.MoveMode.MoveAnchor,
                len(right),
            )
            self.setTextCursor(cursor)

    def toggle_line_prefix(self, prefix):
        cursor = self.textCursor()
        sb = self.document().findBlock(cursor.selectionStart())
        eb = self.document().findBlock(cursor.selectionEnd())
        lines = []
        b = sb
        while True:
            t = b.text()
            lines.append(t[len(prefix):] if t.startswith(prefix) else prefix + t)
            if b == eb:
                break
            b = b.next()
        cursor.beginEditBlock()
        cursor.setPosition(sb.position())
        cursor.setPosition(eb.position() + len(eb.text()), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText("\n".join(lines))
        cursor.endEditBlock()

    def insert_mermaid(self, source):
        cursor = self.textCursor()
        offset = 0
        if cursor.hasSelection():
            start = cursor.selectionStart()
        else:
            start = cursor.position()
        if start != cursor.block().position():
            offset = 1
        block = "```mermaid\n" + source.rstrip("\n") + "\n```"
        cursor.beginEditBlock()
        if offset:
            cursor.setPosition(start)
            cursor.insertText("\n")
        cursor.insertText(block)
        pos = start + offset + len("```mermaid\n")
        cursor.setPosition(pos)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def insert_table(self, cols=3, rows=2):
        cursor = self.textCursor()
        header = "| " + " | ".join("Column {}".format(i + 1) for i in range(cols)) + " |"
        divider = "| " + " | ".join(["---"] * cols) + " |"
        body = "\n".join("| " + " | ".join(["Cell"] * cols) + " |" for _ in range(rows))
        table = header + "\n" + divider + "\n" + body
        offset = 0
        if cursor.hasSelection():
            start = cursor.selectionStart()
        else:
            start = cursor.position()
        if start != cursor.block().position():
            table = "\n" + table
            offset = 1
        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.insertText(table)
        first_cell_start = start + offset + 2
        first_cell_end = first_cell_start + len("Column 1")
        cursor.setPosition(first_cell_start)
        cursor.setPosition(first_cell_end, QTextCursor.MoveMode.KeepAnchor)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def insert_fence_block(self):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            sel = cursor.selectedText().replace("\u2029", "\n")
            cursor.insertText("```\n" + sel + "\n```")
            cursor.setPosition(start + 4)
            cursor.setPosition(start + 4 + len(sel), QTextCursor.MoveMode.KeepAnchor)
        else:
            cursor.insertText("```\n\n```")
            cursor.movePosition(QTextCursor.MoveOperation.Up)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def insert_header(self, level):
        cursor = self.textCursor()
        block = cursor.block()
        marker = "#" * level + " "
        original = block.text()
        new_text = marker + original if not original.startswith(marker) else original[len(marker):]
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
        )
        prefix_len = len(new_text) - len(original)
        cursor.insertText(new_text)
        pos = cursor.position() - prefix_len if prefix_len > 0 else cursor.position()
        cursor.setPosition(pos)
        cursor.endEditBlock()
        self.setTextCursor(cursor)