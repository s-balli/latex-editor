"""Derleme mixin — derle, durdur, otomatik derle, derleme callback'leri."""

import os
import shutil

from PyQt6.QtCore import Qt

from gui.editor import EditorWidget
from core.engine_detector import can_compile as _can_compile, detect_engine as _detect_engine, detect_root as _detect_root
from core.log_parser import resolve_error_path
from core.log import get_logger
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("CompileOpsMixin", s)
_logger = get_logger("compile")


class CompileOpsMixin:

    def _save_if_open(self, path: str) -> bool:
        """``path`` açık sekmedeyse ve değiştiyse kaydet (kök belge kaydı dahil).

        Dosya açık değilse True (kayılacak bir şey yok). Kayıt başarısız olursa
        False döner; çağıran derlemeyi iptal eder.
        """
        editor = self._editor_by_path(path)
        if editor is None:
            return True
        if editor.isModified():
            if not editor.save_file():
                return False
            if hasattr(self, "_file_watch_record_save"):
                self._file_watch_record_save(editor.file_path)
        return True

    def _resolve_compile_target(self, path: str) -> tuple[str, str]:
        """Derlenecek hedefi çözümle: (hedef_yolu, hata_mesajı).

        Dosya doğrudan derlenemiyorsa (% \\begin{document} yok) '% !TEX root'
        magic comment'ından kök belge aranır (TeXstudio uzlaşımı). Bulunursa
        hedef köktür; o da yoksa hata mesajı dolu döner.
        """
        ok, msg = _can_compile(path)
        if ok:
            return path, ""
        root = _detect_root(path)
        if root:
            _logger.info("Alt dosya → kök belge: %s → %s", os.path.basename(path), os.path.basename(root))
            return root, ""
        return "", msg

    def _compile(self):
        # Meşgul guard'I durum değişikliklerinden ÖNCE: sürmekte olan derleme
        # varken paneli temizleyip hedefi/imleç bağlamını yenisiyle ezsek,
        # biten derlemenin hataları yanlış dizine çözülürdü (compile() False
        # döner ama çağrıdan önceki atamalar çoktan yapılmış olurdu).
        if self._compiler.is_busy():
            self._status.showMessage(_("Derleme sürüyor; bitmesini bekleyin veya Esc ile durdurun"))
            return
        self._compile_cursor_ctx = None  # önceki derlemenin imleç bağlamı bayat
        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._status.showMessage(_("Derlenecek dosya yok"))
            return
        target, msg = self._resolve_compile_target(editor.file_path)
        if not target:
            self._output_panel.clear()
            self._output_panel.show_cannot_compile(msg)
            self._status.showMessage(msg)
            return
        if not self._save_if_open(editor.file_path) or not self._save_if_open(target):
            self._status.showMessage(_("Kayıt başarısız — derleme iptal"))
            return
        # Alt dosyadan kök derlendiyse motoru kökün içeriği belirler
        engine = self._engine_combo.currentText()
        if target != editor.file_path:
            engine = _detect_engine(target) or engine
        # Derleme sonrası otomatik ileri-arama için imleç konumunu hatırla;
        # SyncTeX girdi-dosyası bazlı olduğu için alt dosya konumu da geçerlidir
        line, col = editor.getCursorPosition()
        self._compile_cursor_ctx = (editor.file_path, line + 1, col + 1)
        self._output_panel.clear()
        _logger.info("Derleme başladı: %s (%s)", os.path.basename(target), engine)
        self._compile_target = target
        self._compiler.compile(target, engine)

    def _compile_file(self, path: str):
        """Dosya ağacından sağ tıkla derle; alt dosyaysa % !TEX root köküne yönlendir."""
        if self._compiler.is_busy():
            self._status.showMessage(_("Derleme sürüyor; bitmesini bekleyin veya Esc ile durdurun"))
            return
        self._compile_cursor_ctx = None
        path = os.path.normpath(path)
        target, msg = self._resolve_compile_target(path)
        if not target:
            self._output_panel.clear()
            self._output_panel.show_cannot_compile(msg)
            self._status.showMessage(msg)
            return
        if not self._save_if_open(path) or not self._save_if_open(target):
            self._status.showMessage(_("Kayıt başarısız — derleme iptal"))
            return
        engine = self._engine_combo.currentText()
        if target != path:
            engine = _detect_engine(target) or engine
        editor = self._editor_by_path(path)
        if editor is not None:
            line, col = editor.getCursorPosition()
            self._compile_cursor_ctx = (path, line + 1, col + 1)
        self._output_panel.clear()
        _logger.info("Derleme başladı: %s (%s)", os.path.basename(target), engine)
        self._compile_target = target
        self._compiler.compile(target, engine)

    def _stop_compile(self):
        self._compiler.stop()
        self._progress.hide()
        # stop() artık sonuç yaymıyor, dolayısıyla _on_compile_finished'in
        # yaptığı imleç geri alma da çalışmıyor: burada yapılmalı.
        self.setCursor(Qt.CursorShape.ArrowCursor)
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
                    status_msg = _("PDF açılamadı — motoru değiştirip tekrar deneyin")
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

        # Derleme sonrası otomatik ileri-arama (TeXstudio alışkanlığı): imlecin
        # olduğu yere PDF kaydırılır, kullanıcı çıktısını olduğu yerda doğrular.
        # Yalnız başarılı derlemede; hatalı derlemede odak hatalardadır. quiet
        # mod: "Başarılı" durum mesajı SyncTeX mesajıyla ezilmez.
        ctx = getattr(self, "_compile_cursor_ctx", None)
        if ctx and not failed and pdf_shown:
            self._on_forward_search(ctx[0], ctx[1], ctx[2], quiet=True)

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
            others = [e for e in ("lualatex", "pdflatex", "xelatex") if e != current]
            self._output_panel.show_engine_hint(current, others)

        self._refresh_error_markers()
        self._maybe_auto_audit()

    # --- Derleme sonrası otomatik referans denetimi (Derle menüsü anahtarı) ---

    @staticmethod
    def _auto_audit_enabled(settings) -> bool:
        return settings.value("compile/auto_audit", False) in (True, "true", "True")

    def _toggle_auto_audit(self, checked: bool):
        self._settings.setValue("compile/auto_audit", bool(checked))
        self._status.showMessage(
            _("Derleme sonrası referans denetimi açıldı") if checked
            else _("Derleme sonrası referans denetimi kapatıldı")
        )

    def _maybe_auto_audit(self):
        """Derleme bitince (anahtar açıksa) referans denetimini panelin sonuna ekle.

        Derlenen ana dosya diskten okunur (derleme öncesi kaydedilmiş hali).
        Bulgular Uyarılar/Öneriler listelerine eklenir; derleme sonucu ve sekme
        odağı korunur. edit_ops._collect_audit_items'i kullanır.
        """
        if not self._auto_audit_enabled(self._settings):
            return
        target = getattr(self, "_compile_target", "")
        if not target or not os.path.isfile(target):
            return
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            return
        warnings, suggestions, c = self._collect_audit_items(content, target)
        if warnings or suggestions:
            self._output_panel.append_audit(warnings, suggestions)
            # Derleme durum mesajını ezmeden sonuna tek satır özet ekle.
            # currentMessage olmayan stub'larda (test) boş tabanla ilerle.
            cur = getattr(self._status, "currentMessage", None)
            base = cur() if callable(cur) else ""
            summary = self._audit_summary(c)
            self._status.showMessage((base + "  ·  " + summary) if base else summary)

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
        # Kalıcı: motor seçimi ve referans denetimi anahtarı zaten hatırlanıyordu,
        # bu değil. Kullanıcı büyük belgede Manuel'e geçiyor, ertesi gün uygulama
        # yine Otomatik açılıyor ve ilk Ctrl+S'te arayüz derlemeye takılıyordu.
        self._settings.setValue("compile/auto_compile", self._auto_compile)
        act = getattr(self, "_auto_compile_action", None)
        if act is not None and act.isChecked() != self._auto_compile:
            act.setChecked(self._auto_compile)
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
