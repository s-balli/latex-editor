"""Derleme çıktı paneli — hatalar, uyarılar, ham log."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTabWidget,
    QListWidget, QListWidgetItem, QPlainTextEdit, QMenu,
)

from core.error_hints import get_hint
from core.log_parser import CompileResult
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("OutputPanel", s)


# İpucu kimliği → kullanıcıya gösterilecek açıklama (error_hints'teki
# kalıpların sunum katmanı; .ts'e girebilmesi için literal _() dizgeleri).
# FONKSİYON: çeviri ÇAĞRI anında yapılmalı — modül import'u sırasında
# değerlenen sözlük, çevirici yüklenmeden donardı (İngilizce arayüzde
# bile Türkçe kalırdı).
def _hint_templates() -> dict:
    return {
        "undefined_control": _("Tanımsız komut{cmd}: yazım hatası olabilir ya da komutu sağlayan paket yüklenmemiş (\\usepackage gerekebilir)"),
        "missing_math": _("Matematik modu dışında _ ^ veya özel karakter kullanılmış; $...$ veya \\[...\\] içine alın"),
        "invalid_character": _("Geçersiz karakter — genelde Word'den kopyalanan akıllı tırnak/tire; düz \" ve - kullanın"),
        "brace_mismatch": _("Eksik/fazla süslü parantez; bu satırdan geriye doğru { } eşleşmesini kontrol edin"),
        "double_subscript": _("Aynı terimde iki alt/üst simge; a_{bc} gibi gruplayın"),
        "env_undefined": _("Tanımsız ortam {env}: \\newenvironment ile tanımlanmamış ya da paketi yüklenmemiş"),
        "file_ended_scanning": _("Bir komut/ortam kapanmamış (eksik } veya \\end{...}); dosyanın sonuna doğru kontrol edin"),
        "emergency_stop": _("Derleyici beklenmedik durdu; genelde eksik dosya veya kapanmamış blok. Log sekmesindeki son satırlara bakın"),
        "counter_too_large": _("Sayaç sınırı aşıldı (çok sayıda dipnot/liste öğesi); enumitem paketini kullanın"),
        "misplaced_noalign": _("tabular komutu yanlış yerde; \\toprule/\\midrule yalnız tabular içinde satır başında kullanılır"),
        "citation_undefined": _("Kaynakça anahtarı çözülmedi: tekrar derleyin (iki geçe gerekir) veya Düzenle > Referansları Denetle ile anahtarı kontrol edin"),
        "reference_undefined": _("Çapraz referans çözülmedi: tekrar derleyin; \\label tanımlı mı diye Referansları Denetle'ye bakın"),
        "rerun_needed": _("Tekrar derleyin: çapraz referanslar ve kaynakça iki derleme geçesinde çözülür"),
        "duplicate_label": _("Aynı \\label iki kez kullanılmış; F2 ile birini yeniden adlandırın"),
    }


class OutputPanel(QWidget):
    error_clicked = pyqtSignal(str, int)  # file_path, line_number
    # Sürüm geçmişi eylemleri: (aksiyon, sha) — "restore" | "diff"
    version_action = pyqtSignal(str, str)
    # Ortam Denetimi satırına tıklandı (bağlamsal tetik)
    env_check_requested = pyqtSignal()

    # Doktor satırının UserRole işareti: (dosya, satır) demetiyle karışmasın
    _ENV_DOCTOR_TAG = "__env_doctor__"

    def __init__(self, parent=None, *, theme: dict = None):
        super().__init__(parent)
        self._theme = theme or {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        t = self._theme

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {t['border_normal']}; background: {t['bg_primary']}; border-top: 2px solid {t['tab_active_border']}; }}"
            f"QTabBar::tab {{ background: {t['bg_toolbar']}; color: {t['fg_muted']}; padding: 5px 14px;"
            f"border: 1px solid transparent; border-bottom: none;"
            f"border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 1px; }}"
            f"QTabBar::tab:hover {{ color: {t['fg_label']}; background: {t['bg_hover_alt']}; }}"
            f"QTabBar::tab:selected {{ background: {t['bg_primary']}; color: {t['fg_bright']}; border: 1px solid {t['border_normal']}; }}"
        )

        list_base = (
            f"QListWidget {{ background: {t['bg_primary']}; font-family: Consolas, 'DejaVu Sans Mono', Menlo, monospace; font-size: 12px; border: none; }}"
            f"QListWidget::item {{ padding: 4px 6px; border-bottom: 1px solid {t['bg_item_hover']}; }}"
            f"QListWidget::item:hover {{ background: {t['bg_item_hover']}; }}"
            f"QListWidget::item:selected {{ background: {t['bg_pressed']}; }}"
        )

        # Hatalar sekmesi
        self._error_list = QListWidget()
        self._error_list.setStyleSheet(f"{list_base} color: {t['sem_error']};")
        self._error_list.itemClicked.connect(self._on_error_click)
        self._error_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._error_list.customContextMenuRequested.connect(self._on_list_context_menu)
        self._error_tab_index = self._tabs.addTab(self._error_list, _("Hatalar"))

        # Uyarılar sekmesi
        self._warn_list = QListWidget()
        self._warn_list.setStyleSheet(f"{list_base} color: {t['sem_warning']};")
        self._warn_list.itemClicked.connect(self._on_result_click)
        self._warn_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._warn_list.customContextMenuRequested.connect(self._on_list_context_menu)
        self._warn_tab_index = self._tabs.addTab(self._warn_list, _("Uyarılar"))

        # Öneriler sekmesi
        self._suggest_list = QListWidget()
        self._suggest_list.setStyleSheet(f"{list_base} color: {t['sem_suggestion']};")
        self._suggest_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._suggest_list.customContextMenuRequested.connect(self._on_list_context_menu)
        self._suggest_list.itemClicked.connect(self._on_result_click)
        self._suggest_tab_index = self._tabs.addTab(self._suggest_list, _("Öneriler"))

        # Ham log sekmesi
        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setStyleSheet(
            f"QPlainTextEdit {{ background: {t['bg_primary']}; color: {t['fg_primary']}; font-family: Consolas, 'DejaVu Sans Mono', Menlo, monospace; font-size: 11px; border: none; }}"
        )
        self._log_tab_index = self._tabs.addTab(self._log_text, "Log")

        # Sürüm geçmişi sekmesi (Sürümle/Ctrl+K; derleme çıktısı değildir,
        # clear() temizlemez — yalnız show_history yeniler)
        self._history_list = QListWidget()
        self._history_list.setStyleSheet(
            f"{list_base} color: {t['fg_primary']};")
        self._history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._history_list.customContextMenuRequested.connect(self._on_history_menu)
        self._history_tab_index = self._tabs.addTab(self._history_list, _("Sürüm Geçmişi"))

        layout.addWidget(self._tabs)
        self.setMaximumHeight(200)

    def clear(self):
        self._error_list.clear()
        self._warn_list.clear()
        self._suggest_list.clear()
        self._log_text.clear()
        self._tabs.setTabText(self._error_tab_index, _("Hatalar"))
        self._tabs.setTabText(self._warn_tab_index, _("Uyarılar"))
        self._tabs.setTabText(self._suggest_tab_index, _("Öneriler"))

    @classmethod
    def _hint_text(cls, hint) -> str:
        """error_hints.get_hint sonucunu gösterilecek metne çevir (yoksa '')."""
        if not hint:
            return ""
        hint_id, params = hint
        tmpl = _hint_templates().get(hint_id)
        if not tmpl:
            return ""
        cmd = params.get("cmd", "")
        return tmpl.format(
            cmd=f" ({cmd})" if cmd else "",
            env=params.get("env", ""),
        )

    def show_result(self, result: CompileResult):
        self.clear()

        # Hatalar
        for err in result.errors:
            text = _("Satır {n}: {msg}").format(n=err.line_number, msg=err.message) if err.line_number else err.message
            hint = self._hint_text(get_hint(err.message, err.context))
            if hint:
                text += "\n    → " + hint
            item = QListWidgetItem(text)
            if hint:
                item.setToolTip(hint)
            item.setData(Qt.ItemDataRole.UserRole, (err.file_path, err.line_number))
            self._error_list.addItem(item)
        self._tabs.setTabText(self._error_tab_index, _("Hatalar ({n})").format(n=len(result.errors)))

        # Uyarılar
        for w in result.warnings:
            line_info = _("Satır {n}: ").format(n=w.line_number) if w.line_number else ""
            text = f"{line_info}[{w.warning_type}] {w.message}" if w.warning_type else f"{line_info}{w.message}"
            hint = self._hint_text(get_hint(w.message))
            if hint:
                text += "\n    → " + hint
            item = QListWidgetItem(text)
            if hint:
                item.setToolTip(hint)
            item.setData(Qt.ItemDataRole.UserRole, (w.file_path, w.line_number))
            self._warn_list.addItem(item)
        self._tabs.setTabText(self._warn_tab_index, _("Uyarılar ({n})").format(n=len(result.warnings)))

        # Öneriler
        for s in result.suggestions:
            text = s.message
            if s.install_command:
                text += f"\n    {s.install_command}"
            item = QListWidgetItem(text)
            self._suggest_list.addItem(item)
        # Bağlamsal tetik: kurulum komutu taşıyan öneri varsa (eksik paket,
        # motor, WSL, Pygments...) tek tıkla Ortam Denetimi'ne götüren satır.
        # Motor değiştirme önerisi ortam sorunu değildir; satır çıkmaz.
        if any(s.install_command for s in result.suggestions):
            doctor = QListWidgetItem("⚙ " + _("Ortam Denetimi'ni Aç..."))
            doctor.setData(Qt.ItemDataRole.UserRole, self._ENV_DOCTOR_TAG)
            self._suggest_list.addItem(doctor)
        suggest_count = self._suggest_list.count()
        self._tabs.setTabText(self._suggest_tab_index, _("Öneriler ({n})").format(n=suggest_count))

        # Ham çıktı — etiketleri çevir
        raw = result.raw_output
        for src, dst in self._get_tag_map().items():
            if src != dst:
                raw = raw.replace(src, dst)
        self._log_text.setPlainText(raw)

        # Öncelik: öneriler > hatalar > uyarılar
        if result.suggestions:
            self._tabs.setCurrentIndex(self._suggest_tab_index)
        elif result.errors:
            self._tabs.setCurrentIndex(self._error_tab_index)
        elif result.warnings:
            self._tabs.setCurrentIndex(self._warn_tab_index)

    def show_audit(self, warnings: list[tuple[str, str, int]],
                   suggestions: list[tuple[str, str, int]]):
        """Referans denetimi bulgularını tıklanabilir öğeler olarak göster.

        Öğeler (metin, dosya, satır) üçlüsü; warnings Uyarılar, suggestions
        Öneriler sekmesine gider. İkisi de boşsa tek satır 'sorun yok' mesajı
        Öneriler'de gösterilir. Tıklanınca error_clicked sinyali ile editöre
        atlanır (satır > 0 olan öğeler).
        """
        self.clear()
        for text, path, line in warnings:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, (path, line))
            self._warn_list.addItem(item)
        for text, path, line in suggestions:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, (path, line))
            self._suggest_list.addItem(item)
        if not warnings and not suggestions:
            self._suggest_list.addItem(QListWidgetItem(_("Sorun bulunamadı — tüm \\ref/\\cite anahtarları tanımlı.")))
        self._tabs.setTabText(self._warn_tab_index, _("Uyarılar ({n})").format(n=len(warnings)))
        self._tabs.setTabText(self._suggest_tab_index, _("Öneriler ({n})").format(n=len(suggestions)))
        self._tabs.setCurrentIndex(self._warn_tab_index if warnings else self._suggest_tab_index)

    def append_audit(self, warnings: list[tuple[str, str, int]],
                     suggestions: list[tuple[str, str, int]]):
        """Referans denetimi bulgularını mevcut panel sonuçlarının ÜZERİNE ekle.

        Derleme sonrası otomatik denetim için; show_audit paneli temizlerken bu
        temizlemez ve sekme odağını değiştirmez (derleme hataları öncelikli
        kalır). Sekme başlıklarındaki sayılar güncellenir.
        """
        for text, path, line in warnings:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, (path, line))
            self._warn_list.addItem(item)
        for text, path, line in suggestions:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, (path, line))
            self._suggest_list.addItem(item)
        self._tabs.setTabText(self._warn_tab_index, _("Uyarılar ({n})").format(n=self._warn_list.count()))
        self._tabs.setTabText(self._suggest_tab_index, _("Öneriler ({n})").format(n=self._suggest_list.count()))

    def show_history(self, entries):
        """Sürüm geçmişi sekmesini doldur (core.versioning.VersionEntry listesi).

        Öğe metni: 'gg.aa hh:mm · mesaj · N dosya'; sha UserRole'de taşınır.
        Sağ tık menüsünden version_action(aksiyon, sha) sinyali çıkar.
        """
        import time as _time

        self._history_list.clear()
        for e in entries:
            when = _time.strftime("%d.%m.%Y %H:%M", _time.localtime(e.timestamp))
            item = QListWidgetItem(f"{when} · {e.message} · {e.nfiles} {_('dosya')}")
            item.setData(Qt.ItemDataRole.UserRole, e.sha)
            item.setToolTip(f"{e.short} · {e.message}")
            self._history_list.addItem(item)

    def _on_history_menu(self, pos):
        item = self._history_list.itemAt(pos)
        if item is None:
            return
        sha = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        act_restore = menu.addAction(_("Açık dosyayı bu sürümden geri yükle"))
        act_diff = menu.addAction(_("Açık dosyanın farklarını göster"))
        act_copy = menu.addAction(_("Açık dosyanın bu sürümdeki hâlini kopyala"))
        act_drop = None
        if self._history_list.row(item) == 0:
            menu.addSeparator()
            act_drop = menu.addAction(_("Bu sürümü sil (en yeni)"))
        menu.addSeparator()
        act_drop_all = menu.addAction(_("Tüm geçmişi sil"))
        action = menu.exec(self._history_list.mapToGlobal(pos))
        if action == act_restore:
            self.version_action.emit("restore", sha)
        elif action == act_diff:
            self.version_action.emit("diff", sha)
        elif action == act_copy:
            self.version_action.emit("copy", sha)
        elif act_drop is not None and action == act_drop:
            self.version_action.emit("drop", sha)
        elif action == act_drop_all:
            self.version_action.emit("drop_all", sha)

    def show_engine_hint(self, current: str, others: list[str]):
        """Başarısız derlemede motor değiştirme önerisini ekle ve tab'ı aç."""
        hint = QListWidgetItem(
            _("Derleme başarısız oldu. Şu an {current} kullanılıyor.\n    → Araç çubuğundan motoru {other} olarak değiştirip tekrar deneyin.").format(
                current=current, other=" veya ".join(others))
        )
        hint.setForeground(QColor(self._theme["sem_hint"]))
        self._suggest_list.insertItem(0, hint)
        suggest_count = self._suggest_list.count()
        self._tabs.setTabText(
            self._suggest_tab_index, _("Öneriler ({n})").format(n=suggest_count))
        self._tabs.setCurrentIndex(self._suggest_tab_index)

    def show_cannot_compile(self, msg: str):
        """Derlenemeyecek dosya uyarısını öneriler tab'ında göster."""
        item = QListWidgetItem(msg)
        item.setForeground(QColor(self._theme["sem_hint"]))
        self._suggest_list.addItem(item)
        self._tabs.setTabText(self._suggest_tab_index, _("Öneriler ({n})").format(n=self._suggest_list.count()))
        self._tabs.setCurrentIndex(self._suggest_tab_index)

    # derle.sh ve compiler.py çıktılarındaki Türkçe etiketlerin çeviri tablosu
    _TAG_MAP = None

    @classmethod
    def _get_tag_map(cls):
        if cls._TAG_MAP is None:
            cls._TAG_MAP = {
                "[derleniyor]": "[" + _("derleniyor") + "]",
                "[basarili]": "[" + _("basarili") + "]",
                "[basarisiz]": "[" + _("basarisiz") + "]",
                "[uyari]": "[" + _("uyari") + "]",
                "[hata]": "[" + _("hata") + "]",
                "[bilgi]": "[" + _("bilgi") + "]",
            }
        return cls._TAG_MAP

    def append_output(self, text: str):
        for src, dst in self._get_tag_map().items():
            if src != dst:
                text = text.replace(src, dst)
        cursor = self._log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self._log_text.setTextCursor(cursor)

    def _on_error_click(self, item: QListWidget):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            file_path, line = data
            if line and line > 0:
                self.error_clicked.emit(file_path or "", line)

    def _on_result_click(self, item: QListWidget):
        """Uyarı/Öneri öğesine tıkla → (dosya, satır)'a atla (satır > 0 ise)."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data == self._ENV_DOCTOR_TAG:
            self.env_check_requested.emit()
            return
        if data:
            file_path, line = data
            if line and line > 0:
                self.error_clicked.emit(file_path or "", line)

    def _on_list_context_menu(self, pos):
        list_widget = self.sender()
        if not isinstance(list_widget, QListWidget):
            return
        item = list_widget.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        copy_action = menu.addAction(_("Kopyala"))
        action = menu.exec(list_widget.mapToGlobal(pos))
        if action == copy_action:
            QApplication.clipboard().setText(item.text())

    def apply_theme(self, t: dict):
        self._theme = t
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {t['border_normal']}; background: {t['bg_primary']}; border-top: 2px solid {t['tab_active_border']}; }}"
            f"QTabBar::tab {{ background: {t['bg_toolbar']}; color: {t['fg_muted']}; padding: 5px 14px;"
            f"border: 1px solid transparent; border-bottom: none;"
            f"border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 1px; }}"
            f"QTabBar::tab:hover {{ color: {t['fg_label']}; background: {t['bg_hover_alt']}; }}"
            f"QTabBar::tab:selected {{ background: {t['bg_primary']}; color: {t['fg_bright']}; border: 1px solid {t['border_normal']}; }}"
        )
        list_base = (
            f"QListWidget {{ background: {t['bg_primary']}; font-family: Consolas, 'DejaVu Sans Mono', Menlo, monospace; font-size: 12px; border: none; }}"
            f"QListWidget::item {{ padding: 4px 6px; border-bottom: 1px solid {t['bg_item_hover']}; }}"
            f"QListWidget::item:hover {{ background: {t['bg_item_hover']}; }}"
            f"QListWidget::item:selected {{ background: {t['bg_pressed']}; }}"
        )
        self._error_list.setStyleSheet(f"{list_base} color: {t['sem_error']};")
        self._warn_list.setStyleSheet(f"{list_base} color: {t['sem_warning']};")
        self._suggest_list.setStyleSheet(f"{list_base} color: {t['sem_suggestion']};")
        self._log_text.setStyleSheet(
            f"QPlainTextEdit {{ background: {t['bg_primary']}; color: {t['fg_primary']}; font-family: Consolas, 'DejaVu Sans Mono', Menlo, monospace; font-size: 11px; border: none; }}"
        )
        for i in range(self._error_list.count()):
            self._error_list.item(i).setForeground(QColor(t["sem_error"]))
        for i in range(self._warn_list.count()):
            self._warn_list.item(i).setForeground(QColor(t["sem_warning"]))
        for i in range(self._suggest_list.count()):
            self._suggest_list.item(i).setForeground(QColor(t["sem_hint"]))
