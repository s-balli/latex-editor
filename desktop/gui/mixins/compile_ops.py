"""Derleme mixin — derle, durdur, otomatik derle, derleme callback'leri."""

import os
import shutil

from PyQt6.QtCore import Qt

from gui.editor import EditorWidget
from core.engine_detector import can_compile as _can_compile
from core.log_parser import resolve_error_path
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
        self._compile_target = editor.file_path
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
        self._compile_target = path
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
        self._last_errors = []
        self._err_index = -1
        editor = self._current_editor()
        if isinstance(editor, EditorWidget):
            editor.clear_error_markers()

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

        # Hata satırlarını çözümle ve sakla (panel + gutter işareti + F4 ortak
        # liste). Çözümleme show_result'tan ÖNCE: panel tıklayınca da çok
        # dosyalı child hataların doğru dosyaya gitmesi için. (file, line)
        # bazında dedup: TikZ gibi bir hata onlarca cascade hatayı aynı satıra
        # atfedebilir; F4 her konuma bir kez atlamalı (panel yine tüm mesajları gösterir).
        base = os.path.dirname(self._compile_target or "")
        seen = set()
        self._last_errors = []
        for e in result.errors:
            if e.line_number > 0:
                e.file_path = resolve_error_path(e.file_path, base)
                key = (e.file_path, e.line_number)
                if key not in seen:
                    seen.add(key)
                    self._last_errors.append(e)
        self._err_index = -1

        self._output_panel.show_result(result)

        if failed:
            current = self._engine_combo.currentText()
            other = "pdflatex" if current == "lualatex" else "lualatex"
            self._output_panel.show_engine_hint(current, other)

        self._refresh_error_markers()

    def _refresh_error_markers(self):
        """Mevcut editörün gutter'ına son derlemenin hata satırlarını koy.

        currentChanged (sekme değişince) ve F4 atlamasından sonra da çağrılır;
        böylece hangi dosya aktifse onun hataları işaretlenir.
        """
        editor = self._current_editor()
        if not isinstance(editor, EditorWidget):
            return
        editor.clear_error_markers()
        for e in getattr(self, "_last_errors", []):
            if e.file_path == editor.file_path:
                editor.add_error_marker(e.line_number)

    def _goto_next_error(self):
        self._goto_error(step=1)

    def _goto_prev_error(self):
        self._goto_error(step=-1)

    def _goto_error(self, step: int):
        errs = getattr(self, "_last_errors", None)
        if not errs:
            self._status.showMessage(_("Hata yok"))
            return
        n = len(errs)
        if self._err_index < 0:
            self._err_index = 0 if step > 0 else n - 1
        else:
            self._err_index = (self._err_index + step) % n
        e = errs[self._err_index]
        if not e.file_path or not os.path.isfile(e.file_path):
            self._status.showMessage(_("Hata konumu bulunamadı"))
            return
        self._goto_line(e.file_path, e.line_number)
        self._refresh_error_markers()
        self._status.showMessage(_("Satır") + f" {e.line_number}: {e.message}")

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
