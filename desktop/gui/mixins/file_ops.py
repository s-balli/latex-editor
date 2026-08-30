"""Dosya işlemleri mixin — açma, kaydetme, yeni dosya, son açılanlar, motor algılama, dışa aktarma."""

import os
import threading

from PyQt6.QtWidgets import QFileDialog

from gui.editor import EditorWidget
from core.engine_detector import detect_engine as _detect_engine_auto
from core.exporter import export as _export
from core.log import get_logger
from PyQt6.QtCore import QCoreApplication, QObject, pyqtSignal

_ = lambda s: QCoreApplication.translate("FileOpsMixin", s)
_logger = get_logger("file_ops")


class _ExportRunner(QObject):
    """pandoc dışa aktarmayı arka plan thread'inde çalıştırır.

    export() senkron subprocess.run zinciridir (pandoc çağrı başına timeout
    40 sn; .md için birden çok çağrı). UI thread'inden çağrıldığında arayüzü
    tamamen dondurur; daemon thread + sinyalle sonucu UI'ya taşır.
    """

    done = pyqtSignal(bool, str)  # ok, hata mesajı

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None

    def start(self, tex_path: str, dest_path: str):
        def work():
            ok, err = _export(tex_path, dest_path)
            self.done.emit(ok, err)

        self._thread = threading.Thread(target=work, name="pandoc-export", daemon=True)
        self._thread.start()

    def wait(self, timeout_ms: int) -> bool:
        """İş bitene kadar bekle. True = bitti/zaten boştaydı.

        Daemon thread yorumlayıcı çıkışında KESİLİR; kapanışta beklenmezse
        hedef dosya yarım yazılmış kalabilir (bkz. MainWindow.closeEvent).
        """
        t = self._thread
        if t is None or not t.is_alive():
            return True
        t.join(timeout_ms / 1000)
        return not t.is_alive()


class FileOpsMixin:

    def _open_folder(self):
        path = QFileDialog.getExistingDirectory(self, _("Klasör Aç"))
        if not path:
            return
        # Kayıt kararlarını HİÇBİR sekme kapanmadan önce sor: döngü içinde iptal
        # edilirse bazı sekmeler çoktan kapanmış ama klasör değişmemiş yarım
        # durum kalıyordu. Kayıt başarısızsa da hiçbir şey kapanmaz.
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if isinstance(editor, EditorWidget) and editor.isModified():
                self._editor_tabs.setCurrentIndex(i)
                reply = self._save_dialog(editor.display_name)
                if reply == "cancel":
                    return
                if reply == "save":
                    if not editor.save_file():
                        return
                    if hasattr(self, "_file_watch_record_save"):
                        self._file_watch_record_save(editor.file_path)
                else:  # discard
                    editor.setModified(False)
        _logger.info("Klasör açıldı: %s", path)
        for i in range(self._editor_tabs.count() - 1, -1, -1):
            self._close_tab_safe(i)  # dirty kalmadı; iptal edilemez
        self._pdf_viewer.clear()
        self._current_pdf = ""
        self._file_tree.set_root(path)
        # Kök değişti: önceki klasörün sürüm geçmişi ekranda kalmasın
        self._refresh_history()

    def _new_file(self):
        path, _sel_filter = QFileDialog.getSaveFileName(
            self, _("Yeni Dosya"), "", _("LaTeX Dosyaları (*.tex);;Tüm Dosyalar (*)")
        )
        if not path:
            return
        editor = EditorWidget(theme=self._theme_mgr.theme)
        self._apply_editor_settings(editor)
        editor.setText("\\documentclass{article}\n\\begin{document}\n\n\\end{document}\n")
        if not editor.save_file_as(path):
            # Kayıt başarısız (hata dialogu save_file içinde gösterilir): sahte
            # yollu sekme açma, izleme/recent kaydı da yapma
            editor.deleteLater()
            return
        editor.setCursorPosition(3, 0)
        self._connect_editor_signals(editor)
        idx = self._editor_tabs.addTab(editor, editor.display_name)
        self._editor_tabs.setCurrentIndex(idx)
        self._add_tab_close_button(idx)
        self._add_recent(path)
        self._detect_engine(path)
        self._file_watch_add(path)
        editor.setFocus()

    def _open_file(self):
        paths, _sel_filter = QFileDialog.getOpenFileNames(
            self, _("Dosya Aç"), "",
            _("LaTeX Dosyaları (*.tex *.cls *.sty *.bib);;Tüm Dosyalar (*)")
        )
        for p in paths:
            self._open_file_in_editor(p)

    def _connect_editor_signals(self, editor):
        """Editör sinyallerini ana pencere işleyicilerine bağla.

        _new_file ve _open_file_in_editor aynı listeyi taşıyordu; yeni sinyal
        eklendiğinde iki yerin güncellenmesi gerekiyordu.
        """
        editor.modificationChanged.connect(lambda m, e=editor: self._update_tab_title(e))
        editor.cursorPositionChanged.connect(self._update_cursor_pos)
        editor.textChanged.connect(lambda e=editor: self._update_wordcount(e))
        editor.textChanged.connect(lambda e=editor: self._update_outline_debounced(e))
        editor.forward_search_requested.connect(self._on_forward_search)
        editor.image_paste_requested.connect(self._paste_image)
        editor.rename_label_requested.connect(self._on_rename_label)
        editor.rename_cite_requested.connect(self._on_rename_cite)
        editor.rename_bibitem_requested.connect(self._on_rename_bibitem)
        editor.goto_definition_requested.connect(self._on_goto_definition)

    def _open_file_in_editor(self, path: str, add_recent: bool = True):
        editor = self._editor_by_path(path)
        if editor is not None:
            self._editor_tabs.setCurrentWidget(editor)
            return

        editor = EditorWidget(theme=self._theme_mgr.theme)
        self._apply_editor_settings(editor)
        if editor.open_file(path):
            _logger.info("Dosya açıldı: %s", path)
            self._connect_editor_signals(editor)
            idx = self._editor_tabs.addTab(editor, editor.display_name)
            self._editor_tabs.setCurrentIndex(idx)
            self._add_tab_close_button(idx)
            if add_recent:
                # Oturum geri yüklemede add_recent=False: her açılış listeyi
                # yeniden sıralayıp kullanıcının gerçek 'Son Açılanlar'ını ezerdi
                self._add_recent(path)
            self._detect_engine(path)
            self._file_watch_add(path)

    def _detect_engine(self, path: str):
        """Dosya ve .cls içeriğinden uygun derleme motorunu algıla."""
        if not path.endswith(".tex"):
            return
        engine = _detect_engine_auto(path)
        if engine is None:
            engine = "pdflatex"

        _logger.info("Motor algılandı: %s → %s", os.path.basename(path), engine)

        editor = self._current_editor()
        if isinstance(editor, EditorWidget):
            editor._detected_engine = engine

        idx = self._engine_combo.findText(engine)
        if idx >= 0 and idx != self._engine_combo.currentIndex():
            self._engine_combo.setCurrentIndex(idx)
            self._status.showMessage(_("Motor algılandı") + ": " + engine)

    def _save_file(self):
        editor = self._current_editor()
        if editor:
            if not editor.save_file():
                self._save_file_as()
            else:
                self._file_watch_record_save(editor.file_path)

    def _save_file_as(self):
        editor = self._current_editor()
        if not editor:
            return
        try:
            path, _sel_filter = QFileDialog.getSaveFileName(
                self, _("Farklı Kaydet"), "",
                _("LaTeX Dosyaları (*.tex);;Tüm Dosyalar (*)")
            )
        except Exception as e:
            _logger.error("SaveAs dialog hatası: %s", e, exc_info=True)
            return
        if path:
            try:
                old_path = editor.file_path
                editor.save_file_as(path)
                self._editor_tabs.setTabText(self._editor_tabs.currentIndex(), editor.display_name)
                if old_path:
                    self._file_watch_remove(old_path)
                self._file_watch_add(path)
                self._file_watch_record_save(path)
            except Exception as e:
                _logger.error("Dosya kaydetme hatası: %s", e, exc_info=True)

    def _update_tab_title(self, editor):
        index = self._editor_tabs.indexOf(editor)
        if index < 0:
            return
        title = editor.display_name
        if editor.isModified():
            title = f"* {title}"
        self._editor_tabs.setTabText(index, title)

    def _add_recent(self, path: str):
        path = os.path.normpath(path)
        recent = self._settings.value("recent_files", [])
        if isinstance(recent, str):
            recent = [recent]
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:5]
        self._settings.setValue("recent_files", recent)
        self._refresh_recent_menu()

    def _refresh_recent_menu(self):
        self._recent_menu.clear()
        recent = self._settings.value("recent_files", [])
        if isinstance(recent, str):
            recent = [recent]
        if not recent:
            act = self._recent_menu.addAction(_("(boş)"))
            act.setEnabled(False)
            return
        for path in recent:
            if os.path.isfile(path):
                self._recent_menu.addAction(
                    os.path.basename(path),
                    lambda p=path: self._open_file_in_editor(p),
                )

    def _export_file(self, fmt_name: str, ext: str):
        if not getattr(self, '_pandoc_available', True):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, _("Dışa Aktarma"),
                _("pandoc yüklü değil.\n\nKurmak için:\nLinux: sudo apt install pandoc\nWindows (WSL): sudo apt install pandoc\nWindows: pandoc.org")
            )
            return

        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._status.showMessage(_("Dışa aktarılacak dosya yok"))
            return

        # Meşgul kontrolü hedef dialogundan ÖNCE: kullanıcı varış yerini seçip
        # sonra 'zaten sürüyor' uyarısı almasın
        if getattr(self, "_export_busy", False):
            self._status.showMessage(_("Dışa aktarma zaten sürüyor — bitmesini bekleyin"))
            return

        default_name = os.path.splitext(os.path.basename(editor.file_path))[0] + ext
        dest, _sel_filter = QFileDialog.getSaveFileName(
            self, _("Dışa Aktar") + " — " + fmt_name, default_name,
            fmt_name + f" (*{ext});;" + _("Tüm Dosyalar (*)")
        )
        if not dest:
            return

        # exporter.export() .tex'i DİSKTEN okur (core/exporter.py: os.path.exists
        # + _preprocess_tex), arabellekten değil. Kaydetmeden dışa aktarınca
        # kullanıcı son değişiklikleri içermeyen bir DOCX/HTML alıyor ve durum
        # çubuğu yine "Dışa aktarıldı" diyordu. Derleme yolu bunu zaten yapıyor
        # (compile_ops._compile), dışa aktarma atlamıştı.
        if not self._save_if_open(editor.file_path):
            self._status.showMessage(_("Kayıt başarısız — dışa aktarma iptal edildi"))
            return

        # pandoc zinciri arka planda çalışır; süreç bitince durum çubuğu güncellenir
        if getattr(self, "_export_runner", None) is None:
            self._export_runner = _ExportRunner()
            self._export_runner.done.connect(self._on_export_done)
        self._export_busy = True
        self._export_dest = dest
        self._status.showMessage(_("Dışa aktarılıyor") + f" ({fmt_name})...")
        self._export_runner.start(editor.file_path, dest)

    def _on_export_done(self, ok: bool, err: str):
        """Arka plan pandoc dışa aktarması bitti — durumu bildir."""
        self._export_busy = False
        dest = getattr(self, "_export_dest", "")
        if ok:
            self._status.showMessage(_("Dışa aktarıldı") + ": " + os.path.basename(dest))
            _logger.info("Export başarılı → %s", dest)
        else:
            self._status.showMessage(_("Dışa aktarma başarısız") + ": " + str(err))
            _logger.warning("Export başarısız → %s — %s", dest, err)

    def _quick_open(self):
        """Ctrl+P: bulanık filtreyle proje dosyası aç (dosya ağacı kökünde)."""
        from gui.quick_open import QuickOpenDialog
        root = self._file_tree._root
        if not root or not os.path.isdir(root):
            self._status.showMessage(_("Önce bir klasör açın"))
            return
        path = QuickOpenDialog.pick(root, self)
        if path:
            self._open_file_in_editor(path)
