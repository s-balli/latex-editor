"""Görsel ekleme mixin — şablon tespiti, snippet üretimi, ekleme dialogu."""

import os
import re

from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
    QComboBox as QComboWidget,
)

from PyQt6.QtCore import QCoreApplication

from core.latex_tables import escape_cell
from core.latex_utils import label_key, strip_comments

_ = lambda s: QCoreApplication.translate("ImageOpsMixin", s)

# \documentclass[seçenekler]{sınıf} — grup 1 seçenekler, grup 2 sınıf adı
_RE_DOCCLASS = re.compile(r'\\documentclass\s*(\[[^\]]*\])?\s*\{([^}]*)\}')


class ImageOpsMixin:

    @staticmethod
    def _figure_templates() -> dict:
        # Çeviri ÇAĞRI anında yapılmalı: sınıf gövdesinde/Python import'u
        # sırasında değerlenen sözlük, çevirici yüklenmeden donup kalırdı
        # (İngilizce arayüzde bile Türkçe görünürdü).
        return {
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
        """Aktif .tex dosyasının içeriğinden figure şablonu tespit et.

        Sınıf/seçenek aramaları YALNIZ \\documentclass bildirimi üzerinde
        yapılır, belgenin tamamında değil. Eskiden "\\documentclass geçiyor VE
        metinde 'Frontiers' geçiyor" gibi denetimler vardı: kaynakçasında
        "Frontiers in Neuroscience" geçen düz bir article, Frontiers şablonuyla
        görsel ekliyordu. Aynı zayıflık 'twocolumn', 'cas-', 'mnras' için de
        vardı. Belgede gerçekten kullanılan komutlara (\\Figure[, figure*,
        \\subfloat) bakan denetimler yerinde: onlar niyeti doğrudan gösteriyor.

        YORUMLAR ÖNCE AYIKLANIYOR. Dergi şablonları alternatif bildirimi
        yoruma alınmış olarak dağıtıyor ve `search` İLK eşleşmeyi alıyordu,
        yani yorumdakini. Ölçüldü (2026-09-06): `% \\documentclass[twocolumn]`
        satırı üstte olan düz bir article "two_column", yorumdaki
        `%\\documentclass{mnras}` ise "mnras" tespit ediliyordu. Aynı
        gerekçe içerik denetimleri için de geçerli: yoruma alınmış bir
        `\\begin{figure*}` örneği kullanım değil.

        `core.engine_detector` aynı bildirime bakarken `strip_comments`i
        zaten çağırıyordu; iki yer ayrışmıştı.
        """
        content = strip_comments(content)
        m = _RE_DOCCLASS.search(content)
        bildirim = m.group(0) if m else ""
        sinif = m.group(2).strip() if m else ""

        if "\\Figure[" in content or sinif == "ieeeaccess":
            return "ieee_access"
        if ("\\begin{figure*}" in content or sinif == "IEEEtran"
                or "twocolumn" in bildirim):
            return "two_column"
        if sinif == "mnras" or "mnras" in bildirim:
            return "mnras"
        if sinif in ("cas-dc", "cas-sc") or "cas-" in bildirim:
            return "elsevier"
        if sinif.lower().startswith("frontiers") or "frontiers" in bildirim.lower():
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
            # \subfloat içinde AYRI bir \label YOK: eskiden aynı anahtar iki
            # kez basılıyordu (biri burada, biri \caption'dan sonra) ve LaTeX
            # her derlemede "Label multiply defined" uyarıyordu — üstelik
            # uygulamanın kendi log_parser'ında bu uyarının deseni var, yani
            # editör ürettiği kodu kendisi işaretliyordu. Etiket figürün
            # tamamına ait; tek yerde, \caption'dan sonra duruyor.
            return (
                "\\begin{figure}[htbp]\n"
                "    \\centering\n"
                f"    \\subfloat[{caption}]{{\\includegraphics[width={width}]{{{rel_path}}}}}\n"
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
        try:
            rel_path = os.path.relpath(path, tex_dir).replace('\\', '/')
        except ValueError:
            # Windows'ta farklı sürücüler arasında göreli yol kurulamaz → mutlak yol
            rel_path = path.replace('\\', '/')
        name = os.path.splitext(os.path.basename(path))[0]

        # Dosya adı DOĞRUDAN LaTeX'e giriyordu ve editör derlenmeyen bir
        # belge üretiyordu. Ölçüldü (2026-09-06, pdflatex): `sonuc_grafik.png`
        # eklemek `\caption{sonuc_grafik}` yazıyor ve derleme "! Missing $
        # inserted." ile duruyor; `kar%orani.png` de "! File ended while
        # scanning use of \@xdblarg." veriyor. Aynı ders tablo sihirbazında
        # bir kez alınmıştı (`escape_cell`, 21ca9ab), görsel yoluna geçmemiş.
        #
        # Caption TİPOGRAFİK metin, kaçırılıyor. Etiket ANAHTAR, kaçırılmıyor
        # sadeleştiriliyor (bkz. `label_key` gerekçesi). Yalnız VARSAYILANLAR
        # dönüştürülüyor: kullanıcı alana `\textbf{...}` yazarsa o metin
        # onundur, kaçırmak niyetini bozardı.
        caption_var = escape_cell(name)
        label_var = "fig:" + label_key(name)

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
        for key, label in self._figure_templates().items():
            cb_template.addItem(label, key)
        idx = cb_template.findData(auto_template)
        if idx >= 0:
            cb_template.setCurrentIndex(idx)
        form.addRow(_("Şablon:"), cb_template)

        le_width = QLineEdit(default_width)
        form.addRow(_("Genişlik:"), le_width)

        le_caption = QLineEdit(caption_var)
        form.addRow(_("Caption:"), le_caption)

        le_label = QLineEdit(label_var)
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
        caption = le_caption.text().strip() or caption_var
        label = le_label.text().strip() or label_var

        snippet = self._build_figure_snippet(template, rel_path, width, caption, label)

        line, col = editor.getCursorPosition()
        editor.insertAt(snippet, line, col)
        editor.setCursorPosition(line, col)
        editor.ensureLineVisible(line)
        editor.setFocus()

        # YOL kaçırılamaz: `graphicx` dosyanın birebir adını istiyor, `\%`
        # yazmak dosyayı bulunamaz yapar. Ama sessiz de kalınmamalı, çünkü
        # bu satır derlenmiyor. Ölçüldü (2026-09-06, pdflatex): yol içinde
        #   %  -> "! File ended while scanning use of \Gin@ii."
        #   #  -> "! Illegal parameter number in definition of \@tempb."
        # Boşluk, `& $ ^ ~ { }` ise sorunsuz derleniyor, o yüzden listede yok.
        # Kullanıcı hatayı derleme kütüğünde görmeden önce sebebini öğreniyor.
        sorunlu = [k for k in ("%", "#") if k in rel_path]
        if sorunlu:
            self._status.showMessage(
                _("Dosya adındaki {} LaTeX'te görsel yolu olarak "
                  "kullanılamıyor; dosyayı yeniden adlandırın")
                .format(" ve ".join(sorunlu)))

    def _paste_image(self):
        """Ctrl+V ile panodaki resmi media/'a kaydet ve görsel ekleme akışına sok.

        Drag-drop ile aynı _insert_image akışını paylaşır (dialog + figure
        bloğu). .tex'e sadece snippet ekler; resim ayrı bir PNG dosyası olur.
        """
        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._status.showMessage(_("Önce bir .tex dosyası açın"))
            return
        from PyQt6.QtWidgets import QApplication
        img = QApplication.clipboard().image()
        if img.isNull():
            return  # panoda resim yok; metin yapıştırma editörde zaten yapıldı
        media_dir = os.path.join(os.path.dirname(editor.file_path), "media")
        try:
            os.makedirs(media_dir, exist_ok=True)
        except OSError:
            # `exist_ok` yalnız zaten DİZİN varsa affediyor; `media` adında
            # bir DOSYA varsa FileExistsError atıyor. Salt okunur klasör,
            # izin reddi ve dolu disk de buraya düşüyor.
            #
            # Bu bir Qt SLOTU (editor.image_paste_requested). Ölçüldü:
            # PyQt6'da slot içindeki yakalanmamış istisna süreci öldürüyor ve
            # bu uygulamada global excepthook yok, yani öbür sekmelerdeki
            # kaydedilmemiş iş de giderdi. Hemen aşağıdaki `img.save`
            # başarısızlığı zaten aynı mesajı veriyor; yeni bir kullanıcı
            # metni eklemeye gerek yok.
            self._status.showMessage(_("Panodaki resim kaydedilemedi"))
            return
        n = 1
        while True:
            path = os.path.join(media_dir, f"image_{n}.png")
            if not os.path.exists(path):
                break
            n += 1
        if not img.save(path, "PNG"):
            self._status.showMessage(_("Panodaki resim kaydedilemedi"))
            return
        self._insert_image(path)
