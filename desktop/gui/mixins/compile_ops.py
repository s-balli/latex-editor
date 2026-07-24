"""Derleme mixin — derle, durdur, otomatik derle, derleme callback'leri."""

import os
import shutil

from PyQt6.QtCore import Qt

from gui.editor import EditorWidget
from core.engine_detector import can_compile as _can_compile
from core.log import get_logger
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("CompileOpsMixin", s)
_logger = get_logger("compile")


class CompileOpsMixin:

    def _compile(self):
        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._status.showMessage(_("Derlenecek dosya yok"))
            return
        ok, msg = _can_compile(editor.file_path)
        if not ok:
            self._output_panel.clear()
            self._output_panel.show_cannot_compile(msg)
            self._status.showMessage(msg)
            return
        if editor.isModified():
            if not editor.save_file():
                self._status.showMessage(_("Kayıt başarısız — derleme iptal"))
                return
            self._file_watch_record_save(editor.file_path)
        engine = self._engine_combo.currentText()
        self._output_panel.clear()
        _logger.info("Derleme başladı: %s (%s)", os.path.basename(editor.file_path), engine)
        self._compiler.compile(editor.file_path, engine)

    def _compile_file(self, path: str):
        """Dosya ağacından sağ tıkla derle."""
        path = os.path.normpath(path)
        ok, msg = _can_compile(path)
        if not ok:
            self._output_panel.clear()
            self._output_panel.show_cannot_compile(msg)
            self._status.showMessage(msg)
            return
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if isinstance(editor, EditorWidget) and editor.file_path == path:
                if editor.isModified():
                    if not editor.save_file():
                        self._status.showMessage(_("Kayıt başarısız — derleme iptal"))
                        return
                    self._file_watch_record_save(path)
                break
        engine = self._engine_combo.currentText()
        self._output_panel.clear()
        self._compiler.compile(path, engine)

    def _stop_compile(self):
        self._compiler.stop()
        self._progress.hide()
        self._status.showMessage(_("Derleme durduruldu"))

    def _on_esc(self):
        if self._find_bar and self._find_bar.isVisible():
            self._find_bar.hide()
        else:
            self._stop_compile()

    def _on_save_and_compile(self):
        editor = self._current_editor()
        if not editor:
            return
        self._save_file()
        # Kayıt başarısız olduysa (hâlâ dirty veya dosya yolu yoksa) derleme yapma
        if editor.isModified() or not editor.file_path:
            return
        if self._auto_compile:
            self._compile()

    def _on_compile_started(self):
        self._status.showMessage(_("Derleniyor..."))
        self._progress.show()
        self.setCursor(Qt.CursorShape.WaitCursor)

    def _on_compile_finished(self, result):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._progress.hide()

        if result.success:
            _logger.info("Derleme başarılı (%.1fs) — %s", result.duration, result.pdf_path)
        else:
            _logger.warning("Derleme başarısız (%.1fs) — %d hata", result.duration, len(result.errors))

        err_count = len(result.errors)
        warn_count = len(result.warnings)
        # failed: derleme hatalı (exit != 0) VEYA PDF üretilemedi/açılamadı
        failed = not result.success
        status_msg = ""  # boşsa sonradan genel mesaj atanır
        pdf_shown = False

        # PDF'i success'ten bağımsız yükle (varsa) — hatada da kısmi önizleme göster.
        # result.pdf_path yalnızca bu derlemenin ürettiği taze PDF için set edilir
        # (compiler.py mtime kontrolü yapar); bayat/eski PDF buraya gelmez.
        if result.pdf_path and os.path.exists(result.pdf_path):
            if os.path.getsize(result.pdf_path) > 0:
                if not self._pdf_viewer.load_pdf(result.pdf_path):
                    failed = True
                    status_msg = _("PDF acilamadi — motoru degistirip tekrar deneyin")
                else:
                    pdf_shown = True
                    self._current_pdf = result.pdf_path
                    gz_src = os.path.splitext(result.pdf_path)[0] + ".synctex.gz"
                    if os.path.exists(gz_src):
                        try:
                            os.makedirs(self._synctex_dir, exist_ok=True)
                            shutil.move(gz_src, os.path.join(self._synctex_dir, os.path.basename(gz_src)))
                        except OSError as e:
                            _logger.warning("synctex.gz taşınamadı: %s", e)
            elif result.success:
                # başarı bekleniyordu ama PDF boş çıktı
                failed = True
                status_msg = _("PDF oluşturuldu ama boş — motoru değiştirip tekrar deneyin")

        # Başarısız derlemede taze PDF yüklenemediyse eski (koddan farklı) PDF'i
        # ekranda bırakma — tutarsız önizleme yanıltıcı olur. Temizle.
        if failed and not pdf_shown:
            self._pdf_viewer.clear()
            self._current_pdf = ""

        if not status_msg:
            if failed:
                status_msg = _("Basarisiz") + f" — {err_count} " + _("hata") + f" ({result.duration:.1f}s)"
            else:
                status_msg = _("Basarili") + f" ({result.duration:.1f}s)"
                if warn_count:
                    status_msg += f" | {warn_count} " + _("uyari")
        self._status.showMessage(status_msg)

        self._output_panel.show_result(result)

        if failed:
            current = self._engine_combo.currentText()
            other = "pdflatex" if current == "lualatex" else "lualatex"
            self._output_panel.show_engine_hint(current, other)

    def _toggle_auto(self):
        self._auto_compile = not self._auto_compile
        self._update_auto_label_theme(self._theme_mgr.theme)

    def _update_auto_label_theme(self, t: dict):
        if self._auto_compile:
            self._auto_label.setText("  ● " + _("Otomatik Derle") + "  ")
            self._auto_label.setStyleSheet(
                f"color: {t['accent_progress']}; font-weight: bold; padding: 3px 8px; "
                "border: 1px solid transparent; border-radius: 4px;"
            )
        else:
            self._auto_label.setText("  ○ " + _("Manuel") + "  ")
            self._auto_label.setStyleSheet(
                f"color: {t['fg_muted']}; font-weight: bold; padding: 3px 8px; "
                "border: 1px solid transparent; border-radius: 4px;"
            )
