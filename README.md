# Markdown Editor

A lightweight Markdown editor built with **PyQt6**. It supports multiple open tabs, raw editing with live markdown formatting, a rendered preview, and split/edit/preview view modes.

## Features

- **View modes**
  - **Edit** — raw Markdown source only
  - **Preview** — rendered view only
  - **Split** — raw Markdown and live-rendered preview side by side; the preview updates automatically as you type (debounced 300 ms)

- **Multiple tabs** with Open / Save / Save As (`Ctrl+N`, `Ctrl+O`, `Ctrl+S`), closable and reorderable tabs
- **Session restore** — files that were open when you quit are reopened on the next launch (last active tab restored)

- **Auto-detected formatting in the editor** (the raw Markdown syntax is always preserved)
  - Live syntax highlighting: headings, bold, italic, strikethrough, inline code, fenced and indented code blocks, blockquotes, bullet/ordered/task lists, links, images, horizontal rules
  - Fenced code blocks get per-language token coloring via Pygments (```` ```python ````, etc.)

- **Automatic writing aids in the editor**
  - Enter auto-continues `- ` / `* ` / `+ ` / `1. ` (auto-increments) / `> ` / `- [ ] ` lines; Enter on an empty item ends the list. Works with indentation and mid-line splits.
  - Smart typing: `**`, `` ` ``, and `~~` auto-close with the cursor placed between the markers

- **Formatting toolbar** (icon box below the main toolbar) plus **Format menu**
  - Bold (`Ctrl+B`), Italic (`Ctrl+I`), Inline Code, Link
  - Heading 1/2, Bullet List, Numbered List, Quote, Code Block, Table — all wrap or prefix the current selection while keeping the Markdown source intact

- **Mermaid diagram wizard** (Format toolbar / Format menu → Mermaid...)
  - Step-by-step wizard for Flowchart, Sequence, Class, ER, Pie, and Gantt diagrams with a live preview as you build
  - Pre-generated mermaid source is inserted as a ```` ```mermaid ```` block in the editor
  - Mermaid diagrams in the markdown preview render as live SVG diagrams

- **Rendered preview** (Chromium via QtWebEngine)
  - Markdown rendered with Python-Markdown (fenced code, tables, TOC, codehilite/Pygments)
  - Syntax-colored code blocks with a continuous background color (no more white line breaks)
  - External links open in the system browser

- **View menu toggles**
  - Syntax Highlighting
  - Auto-extend Lists
  - Smart Markdown Chars

## Requirements

- Python 3.9+ (tested on Python 3.14 / Windows)
- PyQt6
- PyQt6-WebEngine
- Python-Markdown (`markdown`)
- Pygments

## Setup

```powershell
python -m venv venv
venv\Scripts\python -m pip install PyQt6 PyQt6-WebEngine markdown Pygments
```

## Run

```powershell
venv\Scripts\python main.py
```

## Build a standalone executable

The project includes a PyInstaller spec (`MarkdownEditor.spec`) that produces a single windowed `MarkdownEditor.exe` with Pygments lexers bundled and the `web/` asset folder (Chromium preview page + bundled `mermaid.min.js`) included, so syntax highlighting and Mermaid rendering keep working in the frozen app.

```powershell
venv\Scripts\python -m pip install pyinstaller
venv\Scripts\pyinstaller --noconfirm MarkdownEditor.spec
```

The executable is written to `dist\MarkdownEditor.exe`.

## Project layout

| File                | Purpose                                             |
|---------------------|-----------------------------------------------------|
| `main.py`           | Application window, tabs, toolbar, menus, rendering |
| `markdown_edit.py`  | `CodeEditor` widget and `MarkdownHighlighter`       |
| `mermaid_wizard.py` | Mermaid wizard dialog and diagram generators        |
| `web/`              | Preview renderer page + bundled `mermaid.min.js`    |
| `MarkdownEditor.spec` | PyInstaller build configuration                    |