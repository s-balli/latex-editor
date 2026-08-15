# LaTeX Editor

[![CI](https://img.shields.io/github/actions/workflow/status/s-balli/latex-editor/ci.yml?branch=main&label=CI)](https://github.com/s-balli/latex-editor/actions)
[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/github/v/release/s-balli/latex-editor?label=version&color=green)](https://github.com/s-balli/latex-editor/releases)
[![Downloads](https://img.shields.io/github/downloads/s-balli/latex-editor/total)](https://github.com/s-balli/latex-editor/releases)

> 🌐 **Landing page:** https://s-balli.github.io/latex-editor/

> **English:** README.md (you are here) | **Türkçe:** [README.tr.md](README.tr.md)

A LaTeX editor & compiler desktop app (PyQt6). Combines Notepad++-style editing with a built-in PDF preview, syntax highlighting, SyncTeX, multi-theme and multi-language support. Windows (via WSL for TeX Live) and Linux (AppImage). Licensed under GPL-3.0. A dormant experimental web version (FastAPI + React/Monaco) lives under `web/` but is **not distributed**.

---

 ## Screenshot

![Main window](./docs/assets/01.png)

### SyncTeX in action

Ctrl+Click a line in the editor → the PDF jumps to it, even across pages. Ctrl+Click the PDF → the editor jumps back to that source line.

![SyncTeX: click source line ↔ jump to PDF](./docs/assets/ss1.gif)

---

## Download

| Platform | File | Requirement |
|----------|------|-------------|
| **Windows** | `LaTeX_Editor_v*_Windows.exe` (portable) | [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) + TeX Live |
| **Linux** | `LaTeX_Editor_v*_Linux_x86_64.AppImage` | TeX Live |

➜ **[Download (Releases) page](https://github.com/s-balli/latex-editor/releases)**

> ⚠️ **Important:** The app only includes the GUI. The LaTeX compiler (`lualatex`/`pdflatex`/`xelatex`) must be installed separately via **TeX Live** — on Windows through **WSL**, on Linux via `apt`. See [Requirements](#requirements) section for details.

---

## Version History

### v1.0.8 — AppImage XeLaTeX Fix
- **Bugfix (Linux/AppImage)**: XeLaTeX failed inside the AppImage with `GLIBCXX_3.4.32 not found` — the bundled (older) `libstdc++` leaked into system binaries via `LD_LIBRARY_PATH`. The compile chain (`derle.sh`), pandoc export and SyncTeX now strip the bundled library paths before spawning system tools
- **659 unit tests**

### v1.0.7 — Quick Open, Rename & Auto Audit
- **Editor**: quick open (Ctrl+P): fuzzy-filtered file picker over the project folder (.tex/.bib/.cls/.sty); type, navigate with arrow keys, Enter opens
- **Editor**: F2 on a `\cite` key or a `.bib` entry renames the bibliography key across the document, the `\input` chain and the `.bib` entry itself; `\bibitem` entries (manual thebibliography) are also supported (multi-key `\cite{a,b}` segments handled; single undo step in open tabs; duplicates blocked). F2 on labels keeps working as before
- **Editor**: optional post-compile reference audit (Build menu toggle): findings are appended to the output panel after each compile without clearing compile errors; clickable as before; a one-line summary (zero categories omitted) is appended to the status bar next to the compile result
- **656 unit tests**

### v1.0.6 — Completions, Reference Audit, Rename & XeLaTeX
- **Editor**: settings dialog (View > Editor Settings): tab width, editor font size and word wrap; persisted across sessions and applied to open tabs and new ones
- **Engine**: XeLaTeX support: third engine in the toolbar/combos, `--xelatex` flag in `derle.sh`, magic-comment & package-based detection (`mathspec`, `xeCJK`, `xltxtra`, `requires XeLaTeX`), and a missing-engine hint suggesting `sudo apt-get install texlive-xetex`
- **Editor**: `\input{` / `\include{` completion: suggests `.tex` files from the project (relative paths, extension-free), subdirectories included
- **Editor**: `\includegraphics{` completion: suggests image files (`png/jpg/jpeg/pdf/eps`) from the project, same path convention as image paste/drag-drop (relative to the main file, extension kept); optional `[width=...]` argument aware
- **Editor**: F2 on a `\label`/`\ref` renames the key across the document and the `\input` chain (multi-key `\cref{a,b}` segments handled; open tabs get a single undo step, disk files are rewritten atomically; duplicate names blocked)
- **Editor**: reference audit (Edit > Check References): undefined `\ref`/`\cite` keys, unused `.bib` entries and unused `\label`s, computed locally without compiling; multi-file (`\input`) aware, respects comments and `\nocite{*}`; findings are clickable (jump to the usage line, the `.bib` entry or the label)
- **615 unit tests**

### v1.0.5 — Goto-Definition, Error Markers & Editor Improvements
- **Editor**: document-aware completion for `\ref`/`\eqref`/`\pageref` and `\cite`/`\citep`/`\citet` (and similar): suggests `\label` keys from the document (and the `\input` chain) and `.bib` entry keys; `\cite{key1,key2}` multi-key supported
- **Editor**: paste an image from the clipboard (Ctrl+V): saves to `media/` and inserts a `\begin{figure}` block (reuses the drag-drop dialog)
- **Editor**: compile errors flagged in the gutter; F4 / Shift+F4 to jump between errors (multi-file aware)
- **Editor**: Alt+click on `\ref`/`\cite` to go to its definition (`\label`, `.bib`, or `\bibitem` entry); Alt+click a `.bib` entry to jump to where it is `\cite`d in the article. Multi-file `\input` and multi-key `\cite` aware
- **Editor perf**: faster typing in large documents (syntax lexer and `\begin`/`\end` highlight hot paths optimized)
- **Bugfix**: editing inside a multi-line `verbatim` / `\[...\]` block no longer loses correct highlighting
- **549 unit tests**

### v1.0.4 — Editor & Export Improvements
- **Editor**: `\[...\]` / `\(...\)` math highlighting, Ctrl+Space + environment-name completion, matched `\begin`/`\end` highlighting, smart indentation, comment/verbatim-aware completion, dynamic line-number margin
- **File safety**: atomic save (no truncation on crash) and UTF-8 / legacy-Turkish encoding detection (no silent corruption)
- **Export**: abstract & title now included in all formats; bibliography resolved in HTML/DOCX/TXT/Markdown; Plain Text is now real plain text; docx Word-compatibility fixes
- **480+ unit tests**

### v1.0.3 — Compatibility Fix
- **PDF bookmarks**: compatibility with the pypdfium2 outline API change (`PdfBookmark` → `PdfOutlineItem`)
- **Linux packaging**: AppImage `.zsync` delta-update file and naming fixes

### v1.0.2 — Release Infrastructure
- **Dependencies**: pinned versions for reproducible builds
- **Linux packaging**: AppImage convention-compliant naming + `updateinformation` for delta updates
- **Docs**: dynamic release badges, version-agnostic references

### v1.0.1 — Engine & Compile Improvements
- **Engine selection**: `% !TEX program` magic comment support (e.g. `% !TEX program = pdflatex`)
- **Compile watchdog**: 120s timeout, stuck compiles are cancelled
- **Rerun loop**: re-compiles until cross-references resolve (max 5 passes)
- **Bibliography**: suggests install command when `biber`/`bibtex` is missing
- **Bugfix**: warning-context `l.NNN` lines no longer reported as compile errors

### v1.0.0 — First Public Release
- **Public launch**: First public release
- **License**: GPL-3.0 (PyQt6 GPL-compatible)
- **Distribution**: GitHub Releases — Windows portable `.exe` + Linux `.AppImage` (auto-built via GitHub Actions)
- **Auto-update check**: Via Help menu or on startup, checks GitHub Releases API for new versions
- **480+ unit tests**: engine_detector, input_parser, log_parser, paths, latex_utils, exporter, derle_sh, i18n, imports, autopair, latex_lexer, pdf_indicator, wordcount, updater, synctex_live
- **Features**: Syntax highlighting, PDF preview, SyncTeX, 7 themes, multi-language (TR/EN), auto pairing, PDF bookmarks/search/selection, presentation mode, two-page view, smart engine detection, image drag & drop

---

## Features

- **LaTeX syntax highlighting** — commands, comments, math, environments
- **PDF preview** — live PDF view in side panel, zoom
- **Auto-compile** — Ctrl+S to save and compile; after compiling, the PDF auto-scrolls to the cursor position (SyncTeX)
- **`% !TEX root` support** — in multi-file projects, compile from a child (chapter) file; the root document is found and compiled automatically
- **Triple engine support** — lualatex (default), pdflatex and xelatex
- **Project management** — folder open, file tree, multi-file tabs
- **Error display** — compile errors and warnings in separate tabs
- **7 themes** — Dark, Light, Solarized Light, Dracula, Monokai, Nord, Gruvbox
- **Multi-language** — Turkish and English UI, add new language by translating .ts file
- **PDF bookmarks** — section/heading structure in side panel
- **PDF search** — Ctrl+F text search, highlighting, navigation
- **PDF text selection** — drag to select, Ctrl+C to copy
- **Fit to page** — fit to width or full page auto-zoom
- **Two-page view** — side-by-side pages

---

## Desktop App

### Requirements

#### Windows

- **Python 3.12+** — [python.org](https://www.python.org/downloads/)
- **pip** package manager (comes with Python)

#### WSL (for LaTeX compilation)

```bash
sudo apt-get update
sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
  texlive-latex-extra texlive-latex-recommended texlive-lang-european texlive-luatex texlive-xetex \
  texlive-fonts-extra texlive-science texlive-bibtex-extra texlive-font-utils \
  texlive-extra-utils biber texlive-publishers texlive-humanities texlive-pstricks pandoc
```

### Installation

#### Option 1: Exe (Recommended)

No Python installation required. Copy `LaTeX Editor.exe` from `dist/` to any folder and double-click to run. `derle.sh` is embedded in the exe, no need to copy separately.

**Size:** ~63 MB (includes PyQt6, pypdfium2, send2trash)

**To build the exe:**

Double-click `desktop/Exe Olustur.bat`. `dist/LaTeX Editor.exe` will be created.

Or from PowerShell (single line, specify standalone Python path if using Anaconda):
```powershell
cd desktop
& "C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe" -m PyInstaller --onefile --windowed --name "LaTeX Editor" --add-data "..\core;core" --add-data "gui;gui" --add-data "syntax;syntax" main.py
```

**UPX-compressed exe (smaller size):**

Double-click `desktop/Sikistirilmis Exe Olustur.bat`. UPX compresses the exe to reduce size.

UPX installation:
1. Download latest from [UPX Releases](https://github.com/upx/upx/releases)
2. Extract `upx/` folder under `desktop/upx/` (`desktop/upx/upx.exe`)
3. Run `Sikistirilmis Exe Olustur.bat`

Without UPX, the bat file creates a normal exe without compression.

Result: `dist/LaTeX Editor.exe` (Windows) or `dist/LaTeX Editor` (Linux/macOS)

#### Option 2: From Source

**Install Python packages:**

```bash
pip install PyQt6 PyQt6-QScintilla pypdfium2 send2trash
```

Export: `sudo apt-get install pandoc` (WSL/Linux) or [pandoc.org](https://pandoc.org/installing.html) (Windows)

> **Note:** If using Anaconda, you need standalone Python:
> ```
> C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe -m pip install PyQt6 PyQt6-QScintilla pypdfium2 send2trash
> ```

**Launch the app:**

Double-click `desktop/LaTeX Editor.bat`. Or from PowerShell:
```
cd desktop
& "C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe" main.py
```

### Distribution to Another Computer

To run on another computer:

| Required | Description |
|----------|-------------|
| `LaTeX Editor.exe` | Single file, no Python needed |
| **WSL** | WSL must be enabled on Windows 10/11 |
| **TeX Live** | Inside WSL: `sudo apt-get update && sudo apt-get install texlive-base texlive-binaries texlive-latex-base texlive-latex-extra texlive-latex-recommended texlive-lang-european texlive-luatex texlive-xetex texlive-fonts-extra texlive-science texlive-bibtex-extra texlive-font-utils texlive-extra-utils biber texlive-publishers texlive-humanities texlive-pstricks pandoc` |
| **pandoc** | For export: `sudo apt-get install pandoc` inside WSL |

Installation steps:
1. Enable WSL: `wsl --install` (PowerShell, as administrator)
2. Open the Ubuntu app (or run `wsl` in PowerShell) and run the command above to install TeX Live
3. Copy `LaTeX Editor.exe` to desktop, double-click

### Linux

#### Option 1: AppImage (Recommended)

No Python or dependency installation required.

**1. Download AppImage:**
```bash
chmod +x LaTeX_Editor_v*_Linux_x86_64.AppImage
./LaTeX_Editor_v*_Linux_x86_64.AppImage
```

**2. Install TeX Live (for compilation):**

```bash
sudo apt-get update
sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
  texlive-latex-extra texlive-latex-recommended texlive-lang-european \
  texlive-luatex texlive-xetex texlive-fonts-extra texlive-science texlive-bibtex-extra \
  texlive-font-utils texlive-extra-utils biber texlive-publishers \
  texlive-humanities texlive-pstricks libxcb-cursor0 pandoc
```

> **Note:** Instead of `texlive-full` (~7 GB), only required packages are installed (~1.5 GB). Remove packages you don't need:

| Package | Size | Required for |
|---------|------|--------------|
| `texlive-base` | ~50 MB | Basic LaTeX (required) |
| `texlive-binaries` | ~30 MB | lualatex, pdflatex (required) |
| `texlive-latex-base` | ~20 MB | Basic packages (required) |
| `texlive-latex-recommended` | ~40 MB | Common packages |
| `texlive-latex-extra` | ~200 MB | Extra packages (tcolorbox, minted etc.) |
| `texlive-luatex` | ~30 MB | LuaLaTeX support |
| `texlive-xetex` | ~20 MB | XeLaTeX support |
| `texlive-fonts-extra` | ~300 MB | Extra fonts |
| `texlive-science` | ~50 MB | algorithm, siunitx etc. |
| `texlive-bibtex-extra` + `biber` | ~30 MB | Bibliography |
| `texlive-publishers` | ~40 MB | IEEE, Elsevier templates |
| `texlive-humanities` | ~10 MB | phonrule etc. |
| `texlive-pstricks` | ~30 MB | PSTricks graphics |
| `texlive-lang-european` | ~20 MB | European languages incl. Turkish |
| `texlive-font-utils` | ~5 MB | Font conversion tools |
| `texlive-extra-utils` | ~5 MB | Extra tools |
| `libxcb-cursor0` | ~1 MB | PyQt6 mouse cursor support |

**Minimum installation** (basic compilation only):
```bash
sudo apt-get update
sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
  texlive-latex-recommended texlive-luatex texlive-xetex libxcb-cursor0
```

**To build AppImage:**
```bash
cd desktop
./build_appimage.sh
```

Result: `dist/LaTeX_Editor_v*_Linux_x86_64.AppImage`

#### Option 2: From Source

Install Python and TeX Live:
```bash
sudo apt-get install python3 python3-pip texlive-base texlive-binaries texlive-latex-base \
  texlive-latex-extra texlive-latex-recommended texlive-lang-european texlive-luatex texlive-xetex \
  texlive-fonts-extra texlive-science texlive-bibtex-extra texlive-font-utils \
  texlive-extra-utils biber texlive-publishers texlive-humanities texlive-pstricks libxcb-cursor0 pandoc

pip install PyQt6 PyQt6-QScintilla pypdfium2 send2trash
```

Run:
```bash
cd desktop
python3 main.py
```

### macOS

Install Python and MacTeX:
```bash
brew install python
brew install --cask mactex
pip3 install PyQt6 PyQt6-QScintilla pypdfium2 send2trash
```

Run:
```bash
cd desktop
python3 main.py
```

---

## Web App (Experimental — Not Distributed)

> ⚠️ **The web version is experimental/dormant.** ~14 versions behind, not distributed and not included in GitHub Releases. Source code is kept under `web/` for reference. Active development is only on desktop (`desktop/`).

Browser-based LaTeX editor. FastAPI backend + React/Monaco frontend.

### Backend

```bash
pip install fastapi uvicorn
python -m web.backend.run
```

Backend runs at `http://localhost:8000`.

### Frontend

```bash
cd web/frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

### Features

- Monaco editor with LaTeX syntax highlighting (Monarch tokenizer)
- 162 command autocompletion (triggered on `\`)
- WebSocket for real-time compile output
- PDF.js for PDF preview, zoom
- Auto engine detection (fontspec→lualatex, inputenc→pdflatex)
- Tab-based file management, session persistence (localStorage)
- VS Code-style dark theme, menu bar, status bar
- Warning click to navigate to file/line

---

## Usage

### Basic Workflow

1. Press **Open Folder** or `Ctrl+O` → select folder with .tex files
2. **Double-click** `.tex` file in file tree → opens in editor
3. **Ctrl+S** to save → auto-compile starts
4. **PDF** updates in right panel

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+S` | Save + Auto-Compile |
| `Ctrl+B` | Compile |
| `Ctrl+N` | New File |
| `Ctrl+O` | Open Folder |
| `Ctrl+Shift+O` | Open File (Desktop) |
| `Ctrl+Shift+S` | Save As (Desktop) |
| `Ctrl+W` | Close Tab (Web) |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+F` | Find (Editor or PDF) |
| `Ctrl+H` | Find and Replace |
| `Ctrl+C` | Copy (if text selected in PDF) |
| `Ctrl+/` | Toggle Comment |
| `Ctrl+G` | Go to Line |
| `Esc` | Stop Compile / Exit Presentation |
| `F5` | Presentation Mode (PDF) |
| `Ctrl+Q` | Quit (Desktop) |
| `Ctrl+Mouse Wheel` | PDF Zoom |
| `Ctrl+Click (Editor)` | SyncTeX: Show location in PDF |
| `Ctrl+Click (PDF)` | SyncTeX: Go to source code |

### Engine Selection

Select engine from toolbar dropdown:

| Engine | Use case |
|--------|----------|
| **lualatex** (default) | Articles, general documents. High font quality, Overleaf-compatible |
| **pdflatex** | ASYU/IEEE templates, Beamer presentations |

#### When to Use pdflatex?

- **ASYU, IEEE, IEEEtran templates**: These templates use Type 1 fonts like `ptm` (Times). Turkish characters don't render with `lualatex`.
- **Beamer presentations**: Turkish content written in ASCII, `pdflatex` is sufficient.
- Font and color quality is lower with `pdflatex`. Prefer `lualatex` for Overleaf articles.

#### Local vs Overleaf Page Difference

There may be a 1-page difference between local compilation and Overleaf. Reason: different TeX Live versions (local: 2023, Overleaf: 2025). Small differences in font metric calculations push page breaks to different places. Content is identical.

### PDF Preview

- Zoom with **+/-** buttons or **Ctrl+Mouse Wheel**
- **Fit to width/page** buttons for auto-zoom
- **Two-page** toggle for side-by-side view
- Page navigation: **< >** buttons
- **Bookmarks** panel for section/heading navigation
- **Ctrl+F** for PDF text search, highlight results
- Drag to select text, **Ctrl+C** to copy, double-click to select word
- **Invert** button to invert PDF colors (for dark mode reading)
- **F5** for presentation mode — fullscreen, page-by-page navigation
- Default zoom: 75%

### Auto-Compile

Toggle auto-compile by clicking **● Auto** in the toolbar. In Auto mode, Ctrl+S both saves and compiles. In Manual mode, it only saves; use Ctrl+B to compile.

---

## Test

480+ unit tests. No PyQt6 dependency, pure pytest.

```bash
# Install pytest (first time)
pip install pytest

# Run all tests
python3 -m pytest tests/ -v

# Single file
python3 -m pytest tests/test_log_parser.py -v

# Short summary
python3 -m pytest tests/ -q
```

Coverage:

| Module | Test count | Functions covered |
|--------|------------|-------------------|
| `engine_detector` | 47 | engine detection, compilable check, comment cleaning, .cls detection |
| `input_parser` | 24 | \input/\include resolution, path traversal protection, cyclic refs, dir grouping |
| `log_parser` | 26 | error/warning/suggestion parse, line numbers, engine suggestion, file refs |
| `paths` | 20 | Windows/WSL path conversions, roundtrip |
| `latex_utils` | 18 | Comment cleaning, strip_comments |
| `exporter` | 32 | Pandoc export, error scenarios |
| `derle.sh` | 23 | derle.sh integration tests (lualatex/pdflatex) |
| `i18n` | 25 | Translation infrastructure, import safety, startup flow |
| `imports` | 3 | Module import tests (parametrized, syntax validation) |
| `autopair` | 12 | Auto pairing, \begin/\end closing |
| `latex_lexer` | 5 | Syntax highlighting |
| `pdf_indicator` | 9 | Stale PDF indicator, freshness check |
| `wordcount` | 11 | Word counting, math exclusion |
| `updater` | 24 | Version comparison, GitHub API, cache, network errors |
| `log` | 6 | Logger init, file handler, multi-logger |
| `compiler` | 11 | derle.sh path resolution, frozen mode, engine setup |

---

## Terminal Usage

`derle.sh` can be used independently from the terminal. Works with any editor like VS Code, Vim, nano.

### Basic Usage

```bash
# Compile single file (lualatex)
bash derle.sh file.tex

# Compile with pdflatex
bash derle.sh file.tex --pdflatex

# Compile all .tex files in folder
bash derle.sh *.tex

# Folder argument
bash derle.sh /project/folder/
```

### Watch Mode

Automatically recompiles when file is saved. Useful when working with another editor (VS Code, Vim etc.).

```bash
# Auto-compile on file change
bash derle.sh file.tex --watch

# Watch + pdflatex combination
bash derle.sh file.tex --watch --pdflatex
```

Stop watch mode with `Ctrl+C`. Duration shown after each compile.

### Parameters

| Parameter | Description |
|-----------|-------------|
| `--pdflatex` | Use pdfLaTeX instead of LuaLaTeX |
| `--watch` | Watch for file changes, auto-recompile (single file) |
| `--shell-escape` | Force `-shell-escape` flag (minted package auto-detected) |

### Compilation Features

- Bibliography: BibTeX and BibLaTeX (biber) auto-detected
- Index: `makeindex` runs automatically if `.idx` file exists
- Multi-pass: 2nd and 3rd compile auto-triggered if TOC/references changed
- Missing package detection: Catches missing TeX package and shows `apt-get` command

### Terminal + External Editor Workflow

When working from terminal instead of the app:
1. **Start watch in WSL terminal:** `bash derle.sh file.tex --watch`
2. **Edit .tex file** with Notepad++ or VS Code and save
3. **Open PDF in SumatraPDF** — auto-refreshes on file change

> SumatraPDF doesn't lock PDF and auto-shows changes. Adobe Acrobat and Edge lock the PDF file.

## Technical Details

### Compilation Flow

1. Python GUI (Windows) → calls `wsl bash derle.sh file.tex`
2. `derle.sh` → compiles in `mktemp -d`, processes bibliography/index, multi-pass, copies PDF to source folder
3. GUI → renders PDF with `pypdfium2`, displays in right panel

### Why WSL

TeX Live is installed in WSL, so compilation happens on the WSL side. GUI runs on Windows, calls script via `wsl.exe` for compilation. This way, no separate Windows TeX Live installation is needed.

### Compatibility

The project is developed and tested with **TeX Live 2023** (Ubuntu 24.04 LTS repo version). All templates are compatible with this version. Overleaf uses newer TeX Live, so there may be a 1-page difference (content is identical).

### Why a Second Compile May Be Needed

First compile generates table of contents (.toc) and cross-reference files. If these files exist, a second compile is done to fill in TOC/references. If no auxiliary files are generated, the second compile is skipped.

## Pre-Compilation Preparation

Files downloaded from Overleaf may require the following changes.

### 1. iftex Block (Turkish Character Support)

**Old:**
```latex
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
```

**New:**
```latex
\usepackage{iftex}
\ifluatex
  \usepackage{fontspec}
\else
  \usepackage[utf8]{inputenc}
  \usepackage[T1]{fontenc}
\fi
```

### 2. Watermark Fix

`everypage` package skips pages with `tcolorbox` breakable boxes. `eso-pic` works reliably on every page.

**Old (`everypage`):**
```latex
\usepackage{everypage}
\AddEverypageHook{...}
```

**New (`eso-pic`):**
```latex
\usepackage{eso-pic}
\AddToShipoutPictureFG{...}
```

### Auto-Fix Script

If you have multiple `.tex` files, the following script applies iftex + eso-pic changes to all of them:

```bash
#!/bin/bash
# Usage: bash fix.sh /mnt/c/Users/user/Desktop/abc/

FOLDER="$1"

for file in "$FOLDER"/*.tex; do
    echo "Processing: $file"

    # fontspec + iftex change
    sed -i '/\\usepackage\[utf8\]{inputenc}/{
        s/\\usepackage\[utf8\]{inputenc}/\\usepackage{iftex}\n\\ifluatex\n  \\usepackage{fontspec}\n\\else\n  \\usepackage[utf8]{inputenc}/
    }' "$file"

    sed -i '/\\usepackage\[T1\]{fontenc}/a\\\\fi' "$file"

    # Watermark: everypage -> eso-pic
    sed -i 's/\\usepackage{everypage}/\\usepackage{eso-pic}/' "$file"
    sed -i 's/\\AddEverypageHook{/\\AddToShipoutPictureFG{/' "$file"

    echo "Done: $file"
done
```

> Back up your files before running the script.

## Troubleshooting

### "Python has stopped working" error

Anaconda Python incompatibility with PyQt6. Use standalone Python:
```
cd desktop
"C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe" main.py
```

### Compilation fails

Make sure TeX Live is installed in WSL:
```bash
wsl which lualatex
```

### PDF not showing

PDF is shown automatically after successful compilation. Check if `.pdf` file exists in the file tree.

## Dependencies

### Desktop

| Package | Version | Description |
|---------|---------|-------------|
| PyQt6 | >=6.6 | GUI framework |
| PyQt6-QScintilla | >=2.14 | Code editor component |
| pypdfium2 | >=4.20 | PDF render (PDFium-based) |
| send2trash | >=1.8 | Send files to trash |

### Web

| Package | Description |
|---------|-------------|
| FastAPI | Backend framework |
| uvicorn | ASGI server |
| React | Frontend framework |
| Monaco Editor | Code editor |
| Zustand | State management |
| PDF.js | PDF render |

## Project Structure

```
latex-editor/
├── .github/workflows/        # CI + Release (GitHub Actions)
│   ├── ci.yml               # pytest on every push
│   └── release.yml          # tag v* → exe + AppImage
├── core/                     # Shared (desktop + web)
│   ├── derle.sh             # Shared LaTeX compilation script
│   ├── compiler.py          # Desktop compilation engine
│   ├── log_parser.py        # Error/warning parser
│   ├── engine_detector.py   # Engine detection + compilability check
│   ├── input_parser.py      # \input/\include dependency resolver
│   ├── exporter.py          # Pandoc export
│   ├── latex_utils.py       # Shared LaTeX utility functions
│   ├── paths.py             # Platform path conversion (Windows/WSL)
│   ├── log.py               # Centralized logging (platform-aware, rotating)
│   ├── i18n.py              # Internationalization (desktop + web shared)
│   ├── updater.py           # GitHub Releases API update check
│   └── version.py           # Central version source
├── desktop/                  # Desktop app (PyQt6)
│   ├── main.py              # Entry point
│   ├── requirements.txt     # pip dependencies
│   ├── build_appimage.sh    # Linux AppImage build script
│   ├── LaTeX Editor.spec    # PyInstaller Windows spec
│   ├── latex-editor-linux.spec  # PyInstaller Linux spec
│   ├── gui/
│   │   ├── main_window.py   # Main window — layout, theme, event filter, state
│   │   ├── stylesheet.py    # Theme CSS generator (static function)
│   │   ├── editor.py        # QScintilla LaTeX editor
│   │   ├── pdf_viewer.py    # PDF viewer (composition + mixins)
│   │   ├── pdf_render.py    # Pure render function (pypdfium2 → QPixmap)
│   │   ├── pdf_links.py     # Pure link resolution (ctypes abstraction)
│   │   ├── file_tree.py     # Project file tree
│   │   ├── output_panel.py  # Compile output panel
│   │   ├── outline.py       # Document outline (\section hierarchy)
│   │   ├── find_replace.py  # Find/replace panel
│   │   ├── synctex.py       # SyncTeX forward/reverse search
│   │   ├── theme.py         # Central theme definitions (7 themes)
│   │   ├── mixins/          # MainWindow responsibility separation (mixin pattern)
│   │   │   ├── file_ops.py    # File open/save/new, recent files, engine detection
│   │   │   ├── file_watch.py  # Detect external file changes
│   │   │   ├── tab_ops.py     # Tab management, wordcount, outline update
│   │   │   ├── edit_ops.py    # Undo, redo, find, replace, comment, go to line
│   │   │   ├── compile_ops.py # Compile, stop, auto-compile
│   │   │   ├── image_ops.py   # Image insert, template detection, snippet generation
│   │   │   └── synctex_ops.py # SyncTeX forward/reverse search
│   │   └── pdf_viewer_mixins/  # PdfViewer responsibility separation (mixin pattern)
│   │       ├── _render.py       # PDF load, page render, placeholder, two-page
│   │       ├── _ui_setup.py     # Toolbar, theme, save, fit buttons
│   │       ├── _navigation.py   # Page navigation, zoom, fit to page
│   │       ├── _presentation.py # Presentation mode (fullscreen)
│   │       ├── _events.py       # Event filter + link click + text selection
│   │       ├── _synctex.py      # SyncTeX coordinate conversion
│   │       ├── _highlight.py    # Highlighting
│   │       ├── _bookmarks.py    # PDF bookmarks (TOC)
│   │       ├── _search.py       # PDF text search
│   │       └── _selection.py    # PDF text selection/copy
│   ├── syntax/
│   │   └── latex_lexer.py   # LaTeX syntax highlighting
│   ├── translations/        # .ts (source) + .qm (compiled) translation files
│   ├── linux/               # AppRun, .desktop, icons
│   └── *.bat                # Windows build/launcher scripts
├── scripts/
│   └── update_translations.sh  # .ts generate + .qm compile script
├── web/                      # Web app — experimental/dormant (FastAPI + React)
│   ├── backend/
│   │   ├── services/
│   │   │   ├── compiler.py   # WebSocket-based compilation service
│   │   │   └── file_system.py # File system operations
│   │   └── run.py            # Backend entry point
│   └── frontend/
│       └── src/
│           ├── components/   # React components
│           ├── hooks/        # Custom hooks
│           ├── store/        # Zustand state management
│           └── utils/        # LaTeX command list, utilities
├── tests/                    # Unit tests (pytest, 326 tests)
├── .github/ISSUE_TEMPLATE/  # Bug report & feature request templates
├── LICENSE                   # GPL-3.0
├── CONTRIBUTING.md           # Contributing guide
└── README.md
```

---

## License

GPL-3.0 — see [LICENSE](LICENSE).

PyQt6 and PyQt6-QScintilla are GPL-3.0 licensed; therefore the app is licensed under GPL-3.0.
