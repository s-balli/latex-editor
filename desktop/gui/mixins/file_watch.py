"""Dosya izleme mixin — açık dosyaların diskte değişmesini algılar ve yeniden yükleme sunar."""

import hashlib
import os

from PyQt6.QtCore import QFileSystemWatcher, QTimer, QCoreApplication
from PyQt6.QtWidgets import QMessageBox

from gui.editor import EditorWidget
from core.log import get_logger

_ = lambda s: QCoreApplication.translate("FileWatchMixin", s)
_logger = get_logger("file_watch")


class FileWatchMixin:
    """MainWindow mixin: açık sekmelerdeki dosyaları QFileSystemWatcher ile izler,
    dış değişikliklerde kullanıcıya yeniden yükleme dialog'u gösterir."""

    def _file_watch_init(self):
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._file_watch_on_change)
        # Silindiği hâlde sekmede TUTULAN dosyaların GERİ GELMESİNİ yakalamak
        # için klasör izlemesi de gerekiyor (bkz. _silinen_izle).
        self._watcher.directoryChanged.connect(self._file_watch_on_dir_change)

        self._pending_reloads: set[str] = set()
        self._save_hashes: dict[str, str] = {}
        # Diskten silinmiş ama kullanıcı "Sekmede Tut" dediği için sekmesi
        # açık duran yollar.
        self._silinen_tutulanlar: set[str] = set()
        # Diskteki içerik DIŞARIDAN değişti ve kullanıcı "Kendiminkini Koru"
        # dedi: arabellek diskten AYRIŞTI. Otomatik kaydetme bu yolları
        # atlıyor, yoksa kullanıcının yüklemeyi REDDETTİĞİ dış değişikliği
        # (git checkout, ortak yazar, senkron istemcisi) sessizce eziyordu
        # (ölçüldü 2026-09-09). İşaret açık bir kayıtla ya da diskten
        # yeniden yüklemeyle düşüyor: ikisi de kullanıcının kararı.
        self._disk_ayristi: set[str] = set()
        # Modal "dosya değişti" dialog'u açıkken yeniden tur koşmasın:
        # dialog exec() event loop'u döndürür, debounce timer tekrar tetiklenip
        # farklı dosyalar için ikinci/üçüncü promptu üst üste yığardı
        self._reload_prompt_active = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(500)
        self._debounce_timer.timeout.connect(self._file_watch_process_queue)

    # ------------------------------------------------------------------
    # Public API — file_ops / tab_ops tarafından çağrılır
    # ------------------------------------------------------------------

    def _file_watch_add(self, path: str):
        """Dosyayı izlemeye al (sekme açıldığında çağrılır)."""
        path = os.path.normpath(path)
        if not os.path.isfile(path):
            return
        if path not in self._watcher.files():
            self._watcher.addPath(path)
        self._save_hashes[path] = self._file_hash(path)
        _logger.debug("Watch eklendi: %s", path)

    def _file_watch_remove(self, path: str):
        """Dosyayı izlemeden kaldır (sekme kapatıldığında çağrılır)."""
        if not path:
            return
        path = os.path.normpath(path)
        if path in self._watcher.files():
            self._watcher.removePath(path)
        self._save_hashes.pop(path, None)
        self._pending_reloads.discard(path)
        # Sekme kapandıysa geri gelmesini beklemenin de anlamı kalmadı.
        self._silinen_tutulanlar.discard(path)
        self._disk_ayristi.discard(path)
        self._silinen_izlemesini_toparla()
        _logger.debug("Watch kaldırıldı: %s", path)

    def _file_watch_record_save(self, path: str):
        """Kendi kaydımız sonrası hash'i güncelle — false-positive önler."""
        if not path:
            return
        path = os.path.normpath(path)
        # Açık bir kayıt (Ctrl+S, derleme öncesi kayıt) kullanıcının "benim
        # sürümüm geçerli" kararıdır: ayrışma işareti düşer.
        self._disk_ayristi.discard(path)
        if os.path.isfile(path):
            self._save_hashes[path] = self._file_hash(path)
            # Bazı platformlarda kaydetme watcher'ı kaldırır, yeniden ekle
            if path not in self._watcher.files():
                self._watcher.addPath(path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _file_hash(path: str) -> str:
        """Dosya içeriğinin MD5 hash'ini döndürür."""
        h = hashlib.md5()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()

    def _silinen_izle(self, path: str):
        """Silindiği hâlde sekmede tutulan dosyanın GERİ GELMESİNİ bekle.

        Dosya silinince `QFileSystemWatcher` yolu kendi listesinden düşürüyor
        ve o yol bir daha haber vermiyor. Dosya sonradan geri gelirse
        (`git checkout` ile dala dönmek, senkron istemcisinin dosyayı geri
        koyması, çöp kutusundan kurtarmak) kullanıcıya HİÇBİR ŞEY
        söylenmiyordu.

        ÖLÇÜLDÜ (2026-09-08), gerçek akışla: dosya siliniyor, kullanıcı
        "Sekmede Tut" diyor, iki saniye sonra dosya FARKLI içerikle geri
        geliyor -> soru çıkmıyor ve ilk Ctrl+S geri gelen içeriği sessizce
        eziyor. Aynı dosya silinmemiş olsaydı disk değişimi soru çıkaracaktı;
        yani silme, dosyayı korumasız bırakıyordu.

        (İlk ölçümüm "soru çıkıyor" demişti; orada `_process_single`ı ELLE
        çağırdığım için yol hâlâ izleme listesindeydi ve silme ile geri gelme
        milisaniyeler arayla oluyordu. Sinyalin sürdüğü gerçek akışta değil.)

        Klasör izlemesi bu iş için: dosyanın kendisi yokken izlenemiyor.
        """
        self._silinen_tutulanlar.add(path)
        dizin = os.path.dirname(path)
        if dizin and os.path.isdir(dizin) and dizin not in self._watcher.directories():
            self._watcher.addPath(dizin)

    def _silinen_izlemesini_toparla(self):
        """Artık gereği kalmayan klasör izlemelerini bırak."""
        gerekli = {os.path.dirname(p) for p in self._silinen_tutulanlar}
        for d in list(self._watcher.directories()):
            if os.path.normpath(d) not in gerekli:
                self._watcher.removePath(d)

    def _file_watch_on_dir_change(self, dizin: str):
        """Klasör değişti: beklediğimiz dosyalardan biri geri geldi mi?

        Geri gelen dosya sıradan bir "diskte değişti" olayı gibi kuyruğa
        giriyor; hash kaydı silinmiş olduğu için `_process_single` doğrudan
        soruya düşüyor ve kullanıcı diskteki hâli yükleme şansını buluyor.
        """
        dizin = os.path.normpath(dizin)
        for path in list(self._silinen_tutulanlar):
            if os.path.dirname(path) != dizin or not os.path.isfile(path):
                continue
            self._silinen_tutulanlar.discard(path)
            _logger.info("Silinen dosya geri geldi: %s", path)
            self._pending_reloads.add(path)
            self._debounce_timer.start()
        self._silinen_izlemesini_toparla()

    def _file_watch_on_change(self, path: str):
        """QFileSystemWatcher.fileChanged sinyali handler — debounce."""
        path = os.path.normpath(path)
        self._pending_reloads.add(path)
        self._debounce_timer.start()  # zaten çalışıyorsa restart

    def _file_watch_process_queue(self):
        """Debounce süresi dolunca bekleyen tüm değişiklikleri işle."""
        if self._reload_prompt_active:
            # Dialog açık: promptlar üst üste birikmesin; kuyruk duruyor,
            # dialog kapanınca sonraki tur (aşağıdaki restart ile) devralır
            self._debounce_timer.start()
            return
        paths = set(self._pending_reloads)
        self._pending_reloads.clear()

        for path in paths:
            self._process_single(path)

    def _process_single(self, path: str):
        # 1) Dosya silinmiş mi?
        if not os.path.isfile(path):
            _logger.info("Dosya silinmiş: %s", path)
            self._watcher.removePath(path)
            self._save_hashes.pop(path, None)
            # İlgili sekmeyi bul ve kullanıcıya bildir
            editor = self._editor_by_path(path)
            if editor:
                self._handle_deleted_file(editor, path)
            return

        # 2) Hash aynı mı? (kendi kaydımız → atla)
        current_hash = self._file_hash(path)
        saved_hash = self._save_hashes.get(path)
        if saved_hash and current_hash == saved_hash:
            _logger.debug("Hash aynı, atlanıyor: %s", path)
            # Bazı OS'ler dosya dokunma anında watcher'ı kaldırır
            if path not in self._watcher.files():
                self._watcher.addPath(path)
            return

        # 3) İlgili editörü bul
        editor = self._editor_by_path(path)
        if editor is None:
            _logger.debug("Editör bulunamadı, watcher'dan kaldırılıyor: %s", path)
            self._watcher.removePath(path)
            self._save_hashes.pop(path, None)
            return

        # 4) Dialog göster
        self._prompt_reload(editor, path, current_hash)

        # 5) Bazı platformlarda fileChanged sonrası watcher kaldırılır, yeniden ekle
        if os.path.isfile(path) and path not in self._watcher.files():
            self._watcher.addPath(path)

    def _modal_goster(self, cagri):
        """Modal açıkken izleme kuyruğunu durdur, sonra bırak.

        TEK KAYNAK. Kural üç yerde gerekiyor (yeniden yükleme sorusu, silinen
        dosyanın KİRLİ dalı, silinen dosyanın TEMİZ dalı) ve üçüncüsünde
        UNUTULMUŞTU. Modal `exec()` olay döngüsünü döndürüyor; o sırada gelen
        yeni `fileChanged` sinyalleri debounce timer'ını tetikliyor ve kuyruk
        YENİDEN koşup üstüne ikinci bir modal açıyor.

        ÖLÇÜLDÜ (2026-09-06): üç açık dosya silinip ilk modal açıkken diğer
        ikisinin sinyali gelince iç içe modal derinliği 2, toplam üç modal.
        Gerçek tetikleyici sıradan: dal değiştirmek ya da bir temizlik betiği
        açık dosyaları silince sinyaller arka arkaya değil, ARALIKLI geliyor.
        `_file_watch_init` bu dersi zaten yazmıştı; üçüncü dal almamıştı.
        """
        self._reload_prompt_active = True
        try:
            return cagri()
        finally:
            self._reload_prompt_active = False

    def _handle_deleted_file(self, editor: EditorWidget, path: str):
        """Dosya diskten silinmiş — sekmeyi kapat, kaydedilmemiş içeriği koru.

        Arabellek kirliyse sekme sessizce KAPATILAMAZ: setModified(False) ile
        kapatmak kullanıcının kaydedilmemiş emeğini uyarısız yok eder (dosya
        dışarıdan silinmiş olabilir: dal değiştirme, temizlik betiği, senkron
        istemcisi). _prompt_reload'daki kirli-arabellek nezaketi burada da
        geçerli; üç yol sunulur ve varsayılan içeriği kurtarandır.
        """
        fname = os.path.basename(path)

        if editor.isModified():
            dlg = QMessageBox(self)
            dlg.setWindowTitle(_("Dosya Silindi"))
            dlg.setIcon(QMessageBox.Icon.Warning)
            dlg.setText(_(
                "{fname} dosyası diskten silindi.\n\n"
                "Bu dosyada kaydedilmemiş değişiklikleriniz var; sekmeyi "
                "kapatırsanız kaybolur."
            ).format(fname=fname))
            btn_saveas = dlg.addButton(_("Farklı Kaydet..."), QMessageBox.ButtonRole.AcceptRole)
            dlg.addButton(_("Sekmede Tut"), QMessageBox.ButtonRole.RejectRole)
            btn_close = dlg.addButton(_("Sekmeyi Kapat"), QMessageBox.ButtonRole.DestructiveRole)
            dlg.setDefaultButton(btn_saveas)

            self._modal_goster(dlg.exec)

            clicked = dlg.clickedButton()
            if clicked is btn_saveas:
                idx = self._editor_tabs.indexOf(editor)
                if idx >= 0:
                    # _save_file_as aktif sekmeye bakar; hedefi öne al.
                    self._editor_tabs.setCurrentIndex(idx)
                self._save_file_as()
                # Dialog iptal edilirse kayıt olmaz: sekme kirli hâliyle açık
                # kalır (kapatmak, kurtarma teklifini boşa çıkarırdı). O hâlde
                # eski yol hâlâ sekmenin yolu, yani geri gelmesi izlenmeli.
                # Kayıt BAŞARILIYSA editörün yolu değişmiştir ve yenisini
                # `file_ops._save_file_as` zaten izlemeye almıştır.
                if os.path.normpath(editor.file_path or "") == path:
                    self._silinen_izle(path)
                _logger.info("Silinen dosya için Farklı Kaydet: %s", path)
                return
            if clicked is not btn_close:
                # "Sekmede Tut" (ve dialogun X ile kapatılması): içerik editörde
                # durur, yol korunur — Ctrl+S dosyayı eski yerine geri yazar.
                self._silinen_izle(path)
                _logger.info("Silinen dosya sekmede tutuldu: %s", path)
                return
            _logger.info("Silinen dosyanın sekmesi kaydedilmeden kapatıldı: %s", path)
        else:
            self._modal_goster(lambda: QMessageBox.information(
                self, _("Dosya Silindi"),
                _("{fname} dosyası diskten silindi.\nİlgili sekme kapatılacak.")
                .format(fname=fname)))

        idx = self._editor_tabs.indexOf(editor)
        if idx >= 0:
            editor.setModified(False)  # save prompt olmadan kapat
            self._close_tab_safe(idx)

    def _prompt_reload(self, editor: EditorWidget, path: str, new_hash: str):
        """Kullanıcıya yeniden yükleme dialog'u göster."""
        fname = os.path.basename(path)

        if editor.isModified():
            msg = _(
                "{fname} dosyası diskte değiştirildi.\n\n"
                "Kaydedilmemiş yerel değişiklikleriniz var.\n"
                "Diskteki sürümü yüklerseniz yerel değişiklikleriniz kaybolacak."
            ).format(fname=fname)
            btn_reload_text = _("Diskten Yükle")
            btn_keep_text = _("Kendiminkini Koru")
        else:
            msg = _(
                "{fname} dosyası diskte başka bir program tarafından değiştirildi."
            ).format(fname=fname)
            btn_reload_text = _("Yeniden Yükle")
            btn_keep_text = _("Yoksay")

        dlg = QMessageBox(self)
        dlg.setWindowTitle(_("Dosya Değiştirildi"))
        dlg.setText(msg)
        dlg.setIcon(QMessageBox.Icon.Question)

        btn_reload = dlg.addButton(btn_reload_text, QMessageBox.ButtonRole.AcceptRole)
        btn_keep = dlg.addButton(btn_keep_text, QMessageBox.ButtonRole.RejectRole)
        dlg.setDefaultButton(btn_keep)

        self._modal_goster(dlg.exec)

        if dlg.clickedButton() == btn_reload:
            # Cursor konumunu hatırla
            line, col = editor.getCursorPosition()
            # open_file dönüşü YOK SAYILAMAZ. Okuma başarısız olabiliyor
            # (dosya kilitli, izin yok, araya giren yazımdan dolayı ikili
            # bayt) ve o durumda arabellek OLDUĞU GİBİ kalıyor — ama hash
            # yine de diskin yeni değerine yazılıyordu. Sonuç: kullanıcı
            # "Diskten Yükle" dedi, hata diyaloğunu gördü, içerik gelmedi,
            # üstelik izleyici o disk durumunu "kullanıcıya soruldu" diye
            # işaretlediği için bir daha SORMUYORDU. Log da "yeniden
            # yüklendi" diyordu. Hash'e dokunmayınca dosya okunabilir hâle
            # geldiğinde bir sonraki değişiklikte tekrar sorulur.
            if not editor.open_file(path):
                _logger.warning("Diskten yükleme başarısız, hash korunuyor: %s", path)
                return
            # Geçerli aralığa KELEPÇELE: diskteki sürüm daha kısa olabilir
            # (dal değiştirme, geri alma, senkron istemcisi) ve QScintilla
            # aralık dışı konumu makul biçimde kırpmıyor. Ölçüldü: 6 satırlık
            # belge 2 satıra düşünce (5, 2) isteği imleci (0, 1)'e, yani
            # belgenin BAŞINA atıyordu. version_ops._restore_version aynı
            # durumda zaten kelepçeliyor; buradaki eksikti.
            line = min(line, editor.lines() - 1)
            line_text = editor.text(line).rstrip("\n")
            editor.setCursorPosition(line, min(col, len(line_text)))
            editor.ensureLineVisible(line)
            # Hash, YÜKLENEN dosyadan YENİDEN okunuyor; `new_hash` diyalog
            # AÇILMADAN ÖNCE hesaplanmıştı. Diyalog modal ve dakikalarca açık
            # kalabiliyor; o sırada dosya bir daha değişirse `open_file`
            # GÜNCEL içeriği yüklüyor ama kaydedilen hash ESKİ duruma ait
            # kalıyordu. ÜRETİLDİ (2026-09-12): arabellekte B, kayıtlı hash
            # A; arabellek diskle birebir aynı olduğu hâlde uygulama onu
            # "değişmiş" sayıyor ve kullanıcıya TEK değişiklik için İKİNCİ
            # kez soruyor. Kardeş kol ("Kendiminkini Koru") bu dersi zaten
            # biliyor ve hash'i dosyadan yeniden okuyor; asimetri buradaydı.
            #
            # Pencere sıfırlanmıyor, DARALIYOR: `open_file` ile bu okuma
            # arasında da dosya değişebilir. Sıfırlamak `open_file`ın
            # okuduğu baytları geri istemek demek, o da bu katmanda yok.
            #
            # Okuma DÜŞERSE boş kalıyor ve bu BİLEREK: boş hash "diski
            # bilmiyorum" demek ve bir sonraki değişiklikte kullanıcıya
            # tekrar sorulur. Önce buraya `or new_hash` yazmıştım, YANLIŞ
            # yöndü: `new_hash` diyalog öncesi diske ait ve disk o hâle geri
            # dönmüşse arabellek ondan FARKLI olduğu hâlde "aynı" sayılıp
            # soru hiç sorulmazdı. Bilinmeyeni bilinen saymaktansa fazladan
            # sormak yeğdir.
            self._save_hashes[path] = self._file_hash(path)
            self._disk_ayristi.discard(path)   # arabellek artık diskle aynı
            self._detect_engine(path)
            _logger.info("Dosya diskten yeniden yüklendi: %s", path)
        else:
            # Kullanıcı kendi sürümünü korumak istiyor — hash'i editor içeriğine güncelle
            # Böylece sonraki dış değişiklikte tekrar uyarı verilir
            self._save_hashes[path] = current_hash if (current_hash := self._file_hash(path)) else self._save_hashes.get(path, "")
            # "Koru" = arabelleğim kalsın; DISKI EZ demek DEĞİL. Otomatik
            # kaydetme bu yolu atlıyor (bkz. yukarıdaki not).
            if editor.isModified():
                self._disk_ayristi.add(path)
