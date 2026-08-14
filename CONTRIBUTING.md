# Contributing

Contributions are welcome! This guide covers building, testing, and submitting changes.

## Development Setup

### Prerequisites

- **Python 3.12+**
- **PyQt6** and dependencies:
  ```bash
  pip install PyQt6 PyQt6-QScintilla pypdfium2 Pillow send2trash pytest
  ```
- **TeX Live** (for compilation testing — optional, tests auto-skip if missing):
  ```bash
  sudo apt-get install texlive-base texlive-binaries texlive-latex-base \
    texlive-latex-recommended texlive-luatex texlive-xetex pandoc
  ```

### Run from source

```bash
cd desktop
python3 main.py
```

### Run tests

```bash
# All tests
python3 -m pytest tests/ -q

# Specific module
python3 -m pytest tests/test_log_parser.py -v

# With verbose output
python3 -m pytest tests/ -v
```

Tests are pure pytest — no PyQt6 GUI required (offscreen mode for import tests):
```bash
QT_QPA_PLATFORM=offscreen python3 -m pytest tests/ -q
```

## Architecture

- **`core/`** — shared logic (compiler, log parser, engine detector, i18n, updater)
- **`desktop/`** — PyQt6 GUI application
  - `gui/main_window.py` — main window (composition + mixin pattern)
  - `gui/mixins/` — MainWindow responsibility separation (file_ops, tab_ops, edit_ops, compile_ops, image_ops, synctex_ops, file_watch)
  - `gui/pdf_viewer_mixins/` — PdfViewer responsibility separation
- **`tests/`** — unit tests (pytest)

## Building

### Windows (exe)

```bash
cd desktop
python -m PyInstaller "LaTeX Editor.spec" --clean --noconfirm
```

Result: `dist/LaTeX Editor.exe`

### Linux (AppImage)

```bash
cd desktop
./build_appimage.sh
```

Result: `dist/LaTeX_Editor_v{VERSION}_Linux_x86_64.AppImage`

## Translations

Translation files are in `desktop/translations/`. To update:

```bash
bash scripts/update_translations.sh
```

This runs `pylupdate6` to extract strings, then `lrelease` to compile `.qm` files.

To add a new language:
1. Edit `LANGS` in `scripts/update_translations.sh`
2. Run the script
3. Translate the new `.ts` file
4. Run again to compile `.qm`

## Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes with a clear message
4. Run tests: `python3 -m pytest tests/ -q`
5. Push to your fork: `git push origin feature/my-feature`
6. Open a Pull Request

### Commit style

- Use clear, descriptive commit messages
- Reference issues: `Fix #123: description`
- Keep commits focused — one feature/fix per commit

### Code style

- Follow existing patterns (mixin architecture, `_` prefix for private methods)
- No comments unless explaining non-obvious logic
- Add tests for new functionality

## Reporting Issues

Use the issue templates:
- **Bug report**: Include OS, version, steps to reproduce, log output
- **Feature request**: Describe the problem and proposed solution

## License

By contributing, you agree that your contributions will be licensed under GPL-3.0.
