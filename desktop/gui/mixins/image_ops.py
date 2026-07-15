"""Görsel ekleme mixin — şablon tespiti, snippet üretimi, ekleme dialogu."""

import os

from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
    QComboBox as QComboWidget,
)

from gui.editor import EditorWidget
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("ImageOpsMixin", s)


class ImageOpsMixin:

    _FIGURE_TEMPLATES = {
        "standard": _("Standart (\\begin{figure})"),
        "two_column": _("İki sütun (\\begin{figure*})"),
        "ieee_access": _("IEEE Access (\\Figure)"),
        "mnras": _("MNRAS (\\columnwidth)"),
        "elsevier": _("Elsevier CAS"),
        "frontiers": _("Frontiers"),
        "subfigure": _("Alt şekil (subfloat)"),
        "minimal": _("Sadece \\includegraphics"),
    }

    @staticmethod
    def _detect_figure_template(content: str) -> str:
        """Aktif .tex dosyasının içeriğinden figure şablonu tespit et."""
        if "\\Figure[" in content or "\\documentclass{ieeeaccess}" in content:
            return "ieee_access"
        if ("\\begin{figure*}" in content or
                "\\documentclass{IEEEtran}" in content or
                ("\\documentclass" in content and "twocolumn" in content)):
            return "two_column"
        if "\\documentclass{mnras}" in content or ("\\documentclass[" in content and "mnras" in content):
            return "mnras"
        if ("\\documentclass{cas-dc}" in content or
                "\\documentclass{cas-sc}" in content or
                ("\\documentclass[" in content and "cas-" in content)):
            return "elsevier"
        if ("\\documentclass{Frontiersin" in content or
                "\\documentclass{frontiers" in content or
                ("\\documentclass" in content and "Frontiers" in content)):
            return "frontiers"
        if "\\subfloat" in content or "\\begin{subfigure}" in content:
            return "subfigure"
        return "standard"

    @staticmethod
    def _build_figure_snippet(template: str, rel_path: str, width: str,
                              caption: str, label: str) -> str:
        if template == "ieee_access":
            return (
                f"\\Figure[t!](topskip=0pt, botskip=0pt, midskip=0pt){{{rel_path}}}\n"
                f"{{{caption}.\\label{{{label}}}}}\n"
            )
        if template == "two_column":
            return (
                "\\begin{figure*}[!t]\n"
                "    \\centering\n"
                f"    \\includegraphics[width={width}]{{{rel_path}}}\n"
                f"    \\caption{{{caption}}}\n"
                f"    \\label{{{label}}}\n"
                "\\end{figure*}\n"
            )
        if template == "mnras":
            return (
                "\\begin{figure}\n"
                "    \\centering\n"
                f"    \\includegraphics[width=\\columnwidth]{{{rel_path}}}\n"
                f"    \\caption{{{caption}}}\n"
                f"    \\label{{{label}}}\n"
                "\\end{figure}\n"
            )
        if template == "elsevier":
            return (
                "\\begin{figure}[htbp]\n"
                "    \\centering\n"
                f"    \\includegraphics[width={width}]{{{rel_path}}}\n"
                f"    \\caption{{{caption}}}\n"
                f"    \\label{{{label}}}\n"
                "\\end{figure}\n"
            )
        if template == "frontiers":
            return (
                "\\begin{figure}[h!]\n"
                "    \\begin{center}\n"
                f"        \\includegraphics[width={width}]{{{rel_path}}}\n"
                "    \\end{center}\n"
                f"    \\caption{{{caption}}}\n"
                f"    \\label{{{label}}}\n"
                "\\end{figure}\n"
            )
        if template == "subfigure":
            return (
                "\\begin{figure}[htbp]\n"
                "    \\centering\n"
                f"    \\subfloat[{caption}]{{\\includegraphics[width={width}]{{{rel_path}}}%\n"
                f"    \\label{{{label}}}}}\n"
                f"    \\caption{{{caption}}}\n"
                f"    \\label{{{label}}}\n"
                "\\end{figure}\n"
            )
        if template == "minimal":
            return f"\\includegraphics[width={width}]{{{rel_path}}}\n"
        # standard
        return (
            "\\begin{figure}[htbp]\n"
            "    \\centering\n"
            f"    \\includegraphics[width={width}]{{{rel_path}}}\n"
            f"    \\caption{{{caption}}}\n"
            f"    \\label{{{label}}}\n"
            "\\end{figure}\n"
        )

    def _insert_image(self, path: str):
        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._status.showMessage(_("Önce bir .tex dosyası açın"))
            return

        tex_dir = os.path.dirname(editor.file_path)
        rel_path = os.path.relpath(path, tex_dir).replace('\\', '/')
        name = os.path.splitext(os.path.basename(path))[0]

        auto_template = self._detect_figure_template(editor.text())

        _DEFAULT_WIDTHS = {
            "standard": "0.8\\textwidth",
            "two_column": "0.9\\textwidth",
            "ieee_access": "0.8\\textwidth",
            "mnras": "\\columnwidth",
            "elsevier": "0.9\\columnwidth",
            "frontiers": "0.8\\textwidth",
            "subfigure": "0.45\\textwidth",
            "minimal": "0.8\\textwidth",
        }
        default_width = _DEFAULT_WIDTHS.get(auto_template, "0.8\\textwidth")

        t = self._theme_mgr.theme
        bg = t["bg_primary"]
        fg = t["fg_primary"]
        border = t["border_input"]
        accent = t["accent"]
        hover = t["bg_hover"]
        pressed = t["bg_pressed"]

        ss = (
            f"QDialog {{ background: {bg}; color: {fg}; }}"
            f"QLineEdit, QComboBox {{ background: {t['bg_toolbar']}; color: {fg}; "
            f"border: 1px solid {border}; border-radius: 4px; padding: 5px 8px; }}"
            f"QLineEdit:focus, QComboBox:focus {{ border: 1px solid {accent}; }}"
            f"QComboBox QAbstractItemView {{ background: {t['bg_toolbar']}; color: {fg}; "
            f"selection-background-color: {pressed}; }}"
            f"QLabel {{ color: {fg}; }}"
            f"QPushButton {{ background: {t['bg_button']}; color: {fg}; border: 1px solid {border}; "
            f"border-radius: 4px; padding: 5px 16px; }}"
            f"QPushButton:hover {{ background: {hover}; border: 1px solid {accent}; }}"
            f"QPushButton:pressed {{ background: {pressed}; }}"
            f"QDialogButtonBox QPushButton {{ min-width: 80px; }}"
        )

        dlg = QDialog(self)
        dlg.setWindowTitle(_("Görsel Ekle"))
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(ss)
        form = QFormLayout(dlg)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 12)

        cb_template = QComboWidget()
        for key, label in self._FIGURE_TEMPLATES.items():
            cb_template.addItem(label, key)
        idx = cb_template.findData(auto_template)
        if idx >= 0:
            cb_template.setCurrentIndex(idx)
        form.addRow(_("Şablon:"), cb_template)

        le_width = QLineEdit(default_width)
        form.addRow(_("Genişlik:"), le_width)

        le_caption = QLineEdit(name)
        form.addRow(_("Caption:"), le_caption)

        le_label = QLineEdit(f"fig:{name}")
        form.addRow(_("Label:"), le_label)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        template = cb_template.currentData()
        width = le_width.text().strip() or "0.8\\textwidth"
        caption = le_caption.text().strip() or name
        label = le_label.text().strip() or f"fig:{name}"

        snippet = self._build_figure_snippet(template, rel_path, width, caption, label)

        line, col = editor.getCursorPosition()
        editor.insertAt(snippet, line, col)
        editor.setCursorPosition(line, col)
        editor.ensureLineVisible(line)
        editor.setFocus()
