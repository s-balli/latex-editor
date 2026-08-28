"""Sürümleme mixin — Ctrl+K 'Sürümle', Sürüm Geçmişi sekmesi, geri yükleme/fark.

Çekirdek core/versioning.py'dedir (dulwich). Kullanıcı hiçbir git kavramı
görmez: anlık görüntü metaforu. Klasör .git içeriyorsa olduğu gibi kullanılır.
"""

import os
import threading

from PyQt6.QtCore import QCoreApplication, QObject, pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from core import versioning
from core.log import get_logger

_ = lambda s: QCoreApplication.translate("VersionOpsMixin", s)
_logger = get_logger("version_ops")


class _SnapshotRunner(QObject):
    """Arka planda dulwich add+commit — UI thread'i kilitlemez.

    Büyük klasörlerde (ve WSL /mnt/c dosya sisteminde) snapshot saniyeler
    sürüyor; senkron koşarken Ctrl+K arayüzü tamamen donduruyordu.
    file_ops._ExportRunner deseni: daemon thread + done sinyali.
    """

    done = pyqtSignal(bool, str, object)   # ok, hata metni, entry (veya None)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None

    def start(self, root: str, msg: str, first: bool):
        def work():
            try:
                if first:
                    versioning.init_repo(root)
                entry = versioning.snapshot(root, msg)
            except Exception as e:
                _logger.error("Sürüm kaydı başarısız: %s", root, exc_info=True)
                self.done.emit(False, str(e), None)
                return
            # entry None = değişiklik yok (başarı, sürüm atlandı)
            self.done.emit(True, "", entry)

        self._thread = threading.Thread(target=work, name="version-snapshot", daemon=True)
        self._thread.start()

    def wait(self, timeout_ms: int) -> bool:
        """Kayıt bitene kadar bekle. True = bitti/zaten boştaydı.

        Daemon thread yorumlayıcı çıkışında KESİLİR: add+commit'in ortasında
        kesilmek depoyu yarım nesne/index ile bırakabilir. Kapanışta beklenir
        (bkz. MainWindow.closeEvent).
        """
        t = self._thread
        if t is None or not t.is_alive():
            return True
        t.join(timeout_ms / 1000)
        return not t.is_alive()


def classify_diff_line(line: str) -> str:
    """Birleşik fark satrının türü: 'add' | 'del' | 'hunk' | 'ctx'."""
    if line.startswith(("+++", "---")):
        return "hunk"
    if line.startswith("@@"):
        return "hunk"
    if line.startswith("+"):
        return "add"
    if line.startswith("-"):
        return "del"
    return "ctx"


def build_diff_view(diff: str, theme: dict):
    """Fark metnini satır renkli (ekle yeşil / sil kırmızı / hunk soluk)
    salt-okunur QPlainTextEdit olarak döndürür.

    Metin önce düz olarak yüklenir, sonra her satır bloğu seçilip karakter
    formatıyla renklenir: metin düz kalır, seçip kopyalama bozulmaz. (Boş
    dokümana imleçle formatlı ekleme formatları bir blok kaydırıyordu.)
    """
    from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
    from PyQt6.QtWidgets import QPlainTextEdit

    colors = {
        "add": QColor(theme.get("sem_compilable", "#4caf50")),
        "del": QColor(theme.get("sem_error", "#c62828")),
        "hunk": QColor(theme.get("fg_muted", "#888888")),
        "ctx": QColor(theme.get("fg_primary", "#dddddd")),
    }
    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.setStyleSheet(
        f"background: {theme.get('bg_primary', '#1e1e1e')};"
        f" color: {theme.get('fg_primary', '#dddddd')};"
        " font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 12px;")
    view.setPlainText(diff)

    doc = view.document()
    cur = QTextCursor(doc)
    for i in range(doc.blockCount()):
        block = doc.findBlockByNumber(i)
        fmt = QTextCharFormat()
        fmt.setForeground(colors[classify_diff_line(block.text())])
        cur.setPosition(block.position())
        cur.setPosition(block.position() + len(block.text()),
                        QTextCursor.MoveMode.KeepAnchor)
        cur.setCharFormat(fmt)
    return view


class VersionOpsMixin:

    def _version_root(self) -> str:
        tree = getattr(self, "_file_tree", None)
        return getattr(tree, "_root", "") or ""

    def _save_all_open(self) -> bool:
        """Açık kirli sekmeleri kaydet (anlık görüntü diskteki hâli alır)."""
        from gui.editor import EditorWidget
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if isinstance(editor, EditorWidget) and editor.isModified():
                if not editor.save_file():
                    return False
                if hasattr(self, "_file_watch_record_save"):
                    self._file_watch_record_save(editor.file_path)
        return True

    # --- Sürümle (Ctrl+K) ---

    # QSettings anahtarı: hangi klasörler için depo uyarısı onaylandı.
    _REPO_ACK_KEY = "versioning/acked_roots"

    def _repo_ack_roots(self) -> list:
        val = self._settings.value(self._REPO_ACK_KEY, [])
        if isinstance(val, str):       # QSettings tek elemanlı listeyi str verir
            return [val]
        return list(val or [])

    def _confirm_repo_use(self, root: str) -> bool:
        """Yabancı/iç içe depoda ilk sürümlemede onay al. True = devam et.

        Editör depoyu ayırt etmediği için 'Sürümle' kullanıcının GERÇEK git
        deposuna, gerçek dalına commit atabilir. Klasör başına bir kez sorulur
        (onay QSettings'te tutulur); editörün kendi yarattığı depolarda hiç
        sorulmaz, yani normal kullanımda ek tıklama yok.
        """
        st = versioning.repo_status(root)
        if not (st.foreign or st.nested):
            return True
        if os.path.normpath(root) in {os.path.normpath(p) for p in self._repo_ack_roots()}:
            return True

        if st.nested:
            text = _(
                "Bu klasör, '{parent}' git deposunun içinde.\n\n"
                "Sürümleme burada İÇ İÇE bir depo (.git) oluşturur; üst depo "
                "bu klasörü tek bir girdi olarak görür ve içeriği izlenmez."
            ).format(parent=st.parent_repo)
        else:
            nerede = (_("Uzak bağlantılar: ") + ", ".join(st.remotes)) if st.remotes \
                else _("Bu depo bu editör tarafından oluşturulmamış.")
            text = _(
                "Bu klasör zaten bir git deposu.\n\n"
                "Sürümleme AYRI bir geçmiş tutmaz: kayıtlar mevcut deponuza, "
                "bulunduğunuz dala işlenir. 'Sürüm Geçmişi' sekmesindeki silme "
                "işlemleri de bu gerçek depoyu etkiler.\n\n{nerede}"
            ).format(nerede=nerede)

        dlg = QMessageBox(self)
        dlg.setWindowTitle(_("Sürümleme — Mevcut Git Deposu"))
        dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setText(text)
        btn_ok = dlg.addButton(_("Anladım, Devam Et"), QMessageBox.ButtonRole.AcceptRole)
        dlg.addButton(_("Vazgeç"), QMessageBox.ButtonRole.RejectRole)
        dlg.setDefaultButton(btn_ok)
        dlg.exec()
        if dlg.clickedButton() is not btn_ok:
            self._status.showMessage(_("Sürümleme iptal edildi"))
            return False

        acked = self._repo_ack_roots()
        acked.append(os.path.normpath(root))
        self._settings.setValue(self._REPO_ACK_KEY, acked)
        _logger.info("Mevcut git deposunda sürümleme onaylandı: %s", root)
        return True

    def _snapshot(self):
        root = self._version_root()
        if not root or not os.path.isdir(root):
            self._status.showMessage(_("Önce bir klasör açın"))
            return
        if not versioning.DULWICH_AVAILABLE:
            self._status.showMessage(
                _("Sürümleme için 'dulwich' paketi gerekli") + " (pip install dulwich)")
            return
        # Onay ÖNCE: vazgeçen kullanıcının açık sekmeleri diske yazılmış olmasın
        # (Ctrl+K'nın tek yan etkisi kayıt bile olsa, iptal 'hiçbir şey olmadı'
        # demeli).
        if not self._confirm_repo_use(root):
            return

        if not self._save_all_open():
            self._status.showMessage(_("Kayıt başarısız — sürümleme iptal"))
            return

        first = not versioning.is_repo(root)
        default_msg = _("Başlangıç sürümü") if first else ""
        msg, ok = QInputDialog.getText(self, _("Sürümle"), _("Sürüm adı:"), text=default_msg)
        if not ok:
            return
        msg = msg.strip() or (_("Başlangıç sürümü") if first else _("Güncelleme"))

        # dulwich add+commit arka planda: büyük klasörde saniyeler sürer,
        # senkron koşarken Ctrl+K arayüzü kilitleniyordu. İş sürerken ikinci
        # snapshot reddedilir (yarışık/çift kayıt önlenir).
        if getattr(self, "_snapshot_busy", False):
            self._status.showMessage(_("Sürüm alınıyor; bitmesini bekleyin"))
            return
        if getattr(self, "_snapshot_runner", None) is None:
            self._snapshot_runner = _SnapshotRunner()
            self._snapshot_runner.done.connect(self._on_snapshot_done)
        self._snapshot_busy = True
        self._status.showMessage(_("Sürüm alınıyor") + "...")
        self._snapshot_runner.start(root, msg, first)

    def _on_snapshot_done(self, ok: bool, error: str, entry):
        """Arka plan snapshot'ı bitti — durumu bildir, geçmişi yenile."""
        self._snapshot_busy = False
        if not ok:
            self._status.showMessage(_("Sürüm kaydı başarısız") + f": {error}")
            return
        if entry is None:
            self._status.showMessage(_("Değişiklik yok — sürüm atlandı"))
            return
        self._status.showMessage(
            _("Sürüm kaydedildi") + f": {entry.short} · {entry.nfiles} " + _("dosya"))
        _logger.info("Sürüm kaydedildi: %s (%d dosya)",
                     entry.short, entry.nfiles)
        self._refresh_history(select_tab=True)

    # --- Geçmiş ---

    def _show_history(self):
        if not self._version_root():
            self._status.showMessage(_("Önce bir klasör açın"))
            return
        self._refresh_history(select_tab=True)

    def _refresh_history(self, select_tab: bool = False):
        root = self._version_root()
        try:
            entries = versioning.history(root) if root else []
        except Exception:
            _logger.error("Geçmiş okunamadı: %s", root, exc_info=True)
            entries = []
        self._output_panel.show_history(entries)
        if select_tab:
            self._output_panel._tabs.setCurrentIndex(
                self._output_panel._history_tab_index)

    # --- Geçmiş eylemleri (panel sinyali) ---

    def _on_version_action(self, action: str, sha: str):
        root = self._version_root()
        if not root:
            self._status.showMessage(_("Önce bir klasör açın"))
            return

        # Silme eylemleri açık dosya istemez (klasör bazlıdır); geri yükleme,
        # fark ve kopyala hangi dosyaya uygulanacağını bilmek için dosya ister.
        if action in ("restore", "diff", "copy"):
            editor = self._current_editor()
            if not editor or not editor.file_path:
                self._status.showMessage(_("Açık dosya yok"))
                return
            rel = os.path.relpath(editor.file_path, root).replace(os.sep, "/")
            if action == "diff":
                self._show_version_diff(root, sha, rel)
            elif action == "restore":
                self._restore_version(root, sha, rel, editor)
            else:
                self._copy_version_content(root, sha, rel, editor)
        elif action == "drop":
            self._drop_version(root)
        elif action == "drop_all":
            self._drop_all_history(root)

    def _show_version_diff(self, root: str, sha: str, rel: str):
        try:
            diff = versioning.file_diff(root, sha, rel)
        except Exception:
            _logger.error("Fark okunamadı: %s@%s", rel, sha, exc_info=True)
            self._status.showMessage(_("Fark okunamadı"))
            return
        if not diff:
            self._status.showMessage(_("Bu sürümle arasında fark yok"))
            return

        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(_("Fark") + f": {rel} @ {sha[:7]}")
        dlg.resize(720, 480)
        v = QVBoxLayout(dlg)
        theme = getattr(getattr(self, "_theme_mgr", None), "theme", None) or {}
        view = build_diff_view(diff, theme)
        v.addWidget(view)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        v.addWidget(btns)
        dlg.exec()

    def _copy_version_content(self, root: str, sha: str, rel: str, editor):
        """Sürümdeki dosya içeriğini panoya kopyala (dosyaya dokunmadan).

        Tam geri yükleme istemeden eski bir paragrafı alıp yapıştırmak için.
        """
        from PyQt6.QtWidgets import QApplication

        try:
            data = versioning.file_bytes(root, sha, rel)
        except Exception:
            data = None
            _logger.error("Sürümden okunamadı: %s@%s", rel, sha, exc_info=True)
        if data is None:
            self._status.showMessage(_("Dosya bu sürümde bulunamadı"))
            return
        # panoya metin gerekir; dosyanın kendi kodlamasıyla çöz
        try:
            text = data.decode(editor._encoding or "utf-8")
        except (UnicodeDecodeError, LookupError):
            text = data.decode("utf-8", "replace")
        QApplication.clipboard().setText(text)
        self._status.showMessage(
            _("Bu sürümdeki içerik panoya kopyalandı") + f": {rel} @ {sha[:7]}")

    @staticmethod
    def _foreign_repo_note(root: str) -> str:
        """Yabancı depoda silme dialoglarına eklenecek uyarı (yoksa "")."""
        st = versioning.repo_status(root)
        if not st.foreign:
            return ""
        note = "\n\n" + _("DİKKAT: Bu, editörün değil sizin git deponuz.")
        if st.remotes:
            note += " " + _("Uzak bağlantılar: ") + ", ".join(st.remotes) + "."
        return note

    def _drop_version(self, root: str):
        """En yeni sürümü geçmişten sil (dosyalara dokunmaz)."""
        answer = QMessageBox.question(
            self, _("Sürümü Sil"),
            _("En yeni sürüm geçmişten silinir; dosyalarınız değişmez. Devam?")
            + self._foreign_repo_note(root),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            dropped = versioning.drop_last(root)
        except Exception:
            dropped = False
            _logger.error("Sürüm silinemedi: %s", root, exc_info=True)
        if not dropped:
            self._status.showMessage(
                _("Silinemedi — tek sürüm kaldı ya da sürümleme kapalı"))
            return
        self._status.showMessage(_("En yeni sürüm silindi"))
        _logger.info("En yeni sürüm geçmişten silindi: %s", root)
        self._refresh_history(select_tab=True)

    def _drop_all_history(self, root: str):
        """Tüm sürüm geçmişini sil (.git geri dönüşüm kutusuna gider).

        Proje dosyalarına dokunmaz; yanlış silmede klasör geri getirilebilir.
        """
        # Yabancı depoda bu işlem kullanıcının TÜM git geçmişini (dallar, etiketler,
        # remote yapılandırması) çöp kutusuna yollar; onay metni bunu söylemeli.
        st = versioning.repo_status(root)
        if st.foreign:
            metin = _(
                "Bu klasördeki .git klasörü — yani SİZİN git deponuz — çöp "
                "kutusuna taşınacak.\n\nTüm dallar, etiketler ve uzak bağlantı "
                "ayarları gider; proje dosyalarınız yerinde kalır. Geri almak "
                "için çöp kutusundan kurtarmanız gerekir."
            )
            if st.remotes:
                metin += "\n\n" + _("Uzak bağlantılar: ") + ", ".join(st.remotes)
            metin += "\n\n" + _("Devam etmek istediğinize emin misiniz?")
        else:
            metin = _("TÜM sürüm geçmişi silinecek (dosyalarınız silinmez). "
                      "Devam etmek istediğinize emin misiniz?")
        answer = QMessageBox.question(
            self, _("Tüm Geçmişi Sil"), metin,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            # Yanlışlıkla Enter'a basıp gerçek depoyu silmeyi zorlaştır.
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not versioning.drop_all(root):
            self._status.showMessage(_("Silinecek geçmiş yok"))
            return
        self._status.showMessage(
            _("Tüm geçmiş silindi — yeni sürümlemede yeniden başlar"))
        _logger.info("Tüm sürüm geçmişi silindi: %s", root)
        self._refresh_history(select_tab=True)

    def _restore_version(self, root: str, sha: str, rel: str, editor):
        from gui.editor import EditorWidget

        answer = QMessageBox.question(
            self, _("Sürümden Geri Yükle"),
            _("{f} dosyası seçilen sürüme döndürülecek. Kaydedilmemiş "
              "değişiklikler kaybolur.").format(f=rel),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            data = versioning.file_bytes(root, sha, rel)
        except Exception:
            data = None
            _logger.error("Sürümden okunamadı: %s@%s", rel, sha, exc_info=True)
        if data is None:
            self._status.showMessage(_("Dosya bu sürümde bulunamadı"))
            return
        # HAM bayt yazımı: decode/encode döngüsü kodlamayı bozar (cp1254
        # Türkçe dosyada karakterler bozulur, PDF yanlış derlenirdi)
        line, col = editor.getCursorPosition()
        EditorWidget._write_atomic(editor.file_path, data)
        # Yazım doğrudan diske yapıldı: watcher hash'ini güncelle. Güncellenmezse
        # 500ms sonra 'dosya diskte değişti' yeniden yükleme dialogu çıkardı —
        # geri yüklemenin kendisi yaptığı değişiklik için.
        if hasattr(self, "_file_watch_record_save"):
            self._file_watch_record_save(editor.file_path)
        editor.open_file(editor.file_path)
        # open_file (setText) imleci dosya sonuna atıyor; konumu koru,
        # eski sürüm daha kısaysa geçerli aralığa kelepçele
        line = min(line, editor.lines() - 1)
        line_text = editor.text(line).rstrip("\n")
        editor.setCursorPosition(line, min(col, len(line_text)))
        editor.ensureLineVisible(line)
        self._status.showMessage(
            _("Geri yüklendi") + f": {rel} @ {sha[:7]}")
        _logger.info("Sürümden geri yüklendi: %s @ %s", rel, sha[:7])
