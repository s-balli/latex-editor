"""Yazım denetimi mixin: "Denetle" komutu, Yazım sekmesi, kullanıcı sözlüğü.

Çekirdek core/yazim.py'dedir (Qt'süz, LaTeX farkındalıklı tarayıcı + spylls).
Burada yalnız arayüz bağlantısı var.

TASARIM: denetim CANLI DEĞİL, komutla çalışır.
  - Kullanıcı istemeden sözlük yüklenmez. ÖLÇÜLDÜ: tr_TR yüklemesi 3.5 sn ve
    9.3 MB; her açılışta yapmak kabul edilemez.
  - Ekranda kendiliğinden hiçbir şey değişmez. Canlı dalgalı çizgi ayrı bir
    aşama ve Türkçe için tartışmalı (ölçülen gürültü %2-5; ekranın onda biri
    altı çizili olsa kullanıcı ilk gün kapatır).

Sözlük yükleme AYRI İŞ PARÇACIĞINDA: 3.5 sn arayüzü dondurur.
"""

import os
import sys

from PyQt6.QtCore import QCoreApplication, QStandardPaths, QThread, pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from core.log import get_logger

_ = lambda s: QCoreApplication.translate("MainWindow", s)   # noqa: E731
log = get_logger(__name__)


def yazim_kullanilabilir() -> bool:
    """spylls kurulu mu (yani özellik hiç gösterilmeli mi).

    Menü öğesi ve panel sekmesi BUNA BAĞLI. `spylls` bir bağımlılık olarak
    eklenmeden paketlenirse özellik hiç görünmez; görünüp tıklanınca hata
    vermesindense hiç olmaması dürüst.

    Import maliyeti ölçüldü: 82 ms (sözlük YÜKLEMESİ değil, yalnız sınıfın
    import'u). Sözlük yüklemesi 3.5 sn ve o yalnız kullanıcı isteyince olur.
    """
    try:
        from core.yazim import SPYLLS_VAR
        return bool(SPYLLS_VAR)
    except ImportError:                                  # pragma: no cover
        return False


def sozluk_dizini() -> str:
    """tr_TR.dic/.aff'in bulunduğu dizin.

    derle.sh çözümüyle aynı kalıp (bkz. core/compiler.py:_find_derle_sh):
    PyInstaller ile paketlenmişse önce _MEIPASS'a, sonra exe'nin yanına bakılır.
    """
    kok = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))                     # desktop/
    adaylar = [os.path.join(os.path.dirname(kok), "sozlukler")]
    if getattr(sys, "frozen", False):
        adaylar.insert(0, os.path.join(getattr(sys, "_MEIPASS", ""),
                                       "sozlukler"))
        adaylar.insert(1, os.path.join(os.path.dirname(sys.executable),
                                       "sozlukler"))
    for a in adaylar:
        if os.path.isdir(a):
            return a
    return adaylar[-1]


def _sozluk_dizini_gerekli_mi(dil: str) -> str:
    """Bu dil için BİZİM dizinimiz mi kullanılacak, spylls'inki mi.

    en_US spylls paketinin İÇİNDE geliyor (551 KB), biz taşımıyoruz; ona
    dizin verilirse `<dizin>/en_US.dic` aranıp bulunamıyor ve yükleme
    patlıyordu. tr_TR ise yalnız bizde var.

    Körü körüne dizin vermek yerine dosya VARLIĞINA bakılıyor: sözlük
    eklenirse kod değişmeden çalışır.
    """
    dizin = sozluk_dizini()
    _sikistirilmisi_ac(dizin, dil)
    if os.path.isfile(os.path.join(dizin, dil + ".dic")):
        return dizin
    return ""


def _sikistirilmisi_ac(dizin: str, dil: str) -> None:
    """Ham sözlük yoksa `.xz`den aç.

    Sözlük depoda SIKIŞTIRILMIŞ duruyor (ham `.dic` 8.6 MB, deponun bütün
    geçmişi 3.45 MB idi). Paketlenmiş uygulamada `.spec` yapım sırasında
    açtığı için ham dosyalar zaten var ve buraya hiç girilmiyor.

    Ama KAYNAKTAN çalıştıran biri için ham dosya YOK: taze bir kopyada
    `sozlukler/` içinde yalnız `.xz` bulunuyor, `_sozluk_dizini_gerekli_mi`
    boş dönüyor ve yükleme anlaşılmaz bir hata diyaloğuyla düşüyordu.
    """
    hedef = os.path.join(dizin, dil + ".dic")
    if os.path.isfile(hedef):
        return
    import lzma
    for ad in (dil + ".dic", dil + ".aff"):
        kaynak = os.path.join(dizin, ad + ".xz")
        cikti = os.path.join(dizin, ad)
        if not os.path.isfile(kaynak) or os.path.isfile(cikti):
            continue
        try:
            with lzma.open(kaynak, "rb") as f:
                veri = f.read()
            with open(cikti, "wb") as f:
                f.write(veri)
            log.info("Sözlük açıldı: %s", cikti)
        except OSError:
            # Salt okunur dizin ya da bozuk arşiv: özellik kapalı kalır,
            # uygulama çalışmaya devam eder.
            log.warning("Sözlük açılamadı: %s", kaynak, exc_info=True)
            return


def kullanici_sozlugu_yolu(dil: str) -> str:
    """Kullanıcının eklediği kelimeler. Log dizininin komşusu (aynı klasör)."""
    kok = os.path.normpath(os.path.join(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation),
        "LatexEditor"))
    return os.path.join(kok, "sozluk-%s.txt" % dil)


class YazimYukleThread(QThread):
    """Sözlüğü arka planda yükler. ÖLÇÜLDÜ: tr_TR 3.5 sn."""
    yuklendi = pyqtSignal(object)      # Denetleyici
    hata = pyqtSignal(str)

    def __init__(self, dil, ikinci_dil, parent=None):
        super().__init__(parent)
        self._dil = dil
        self._ikinci = ikinci_dil

    def run(self):
        try:
            from core.yazim import Denetleyici
            d = Denetleyici(dil=self._dil,
                            sozluk_dizini=_sozluk_dizini_gerekli_mi(self._dil),
                            kullanici_sozlugu=kullanici_sozlugu_yolu(self._dil))
            d.yukle()
            if self._ikinci and self._ikinci != self._dil:
                ik = Denetleyici(
                    dil=self._ikinci,
                    sozluk_dizini=_sozluk_dizini_gerekli_mi(self._ikinci))
                ik.yukle()
                d.ikincil = ik
            self.yuklendi.emit(d)
        except Exception as e:                            # noqa: BLE001
            log.warning("yazım sözlüğü yüklenemedi: %s", e)
            self.hata.emit(str(e))


class YazimOpsMixin:
    """Yazım denetimi arayüz bağlantısı."""

    def _init_yazim(self):
        self._yazim_denetleyici = None
        self._yazim_anahtar = None          # (dil, ikinci), yüklü olanın
        self._yazim_thread = None
        self._output_panel.yazim_denetle_requested.connect(
            self._on_yazim_denetle_requested)
        self._output_panel.yazim_oneri_requested.connect(self._on_yazim_oneri)
        self._output_panel.yazim_sozluge_ekle.connect(
            self._on_yazim_sozluge_ekle)

    # -- menü --
    def _yazim_denetle(self):
        """Menü/kısayol: Yazım sekmesini açıp denetimi başlat.

        Dili belgeden çıkarıp seçiciye yazıyor; kullanıcı yine değiştirebilir.
        """
        ed = self._current_editor()
        if ed is not None:
            from core.yazim import belgeden_dil
            dil = belgeden_dil(ed.text())
            if dil:
                self._output_panel.yazim_dili_ayarla(dil)
        self._output_panel._on_yazim_denetle()

    # -- panelden gelen istek --
    def _on_yazim_denetle_requested(self, dil: str, ikinci: bool):
        ed = self._current_editor()
        if ed is None:
            self._output_panel.show_yazim([], "", 0)
            return
        ikinci_dil = ("en_US" if dil == "tr_TR" else "tr_TR") if ikinci else ""
        anahtar = (dil, ikinci_dil)

        if self._yazim_denetleyici is not None and self._yazim_anahtar == anahtar:
            self._yazim_calistir()
            return

        if self._yazim_thread is not None and self._yazim_thread.isRunning():
            return                                  # zaten yükleniyor
        self._output_panel.yazim_mesgul(_("sözlük yükleniyor..."))
        self._yazim_anahtar = anahtar
        self._yazim_thread = YazimYukleThread(dil, ikinci_dil, self)
        self._yazim_thread.yuklendi.connect(self._on_yazim_yuklendi)
        self._yazim_thread.hata.connect(self._on_yazim_hata)
        self._yazim_thread.start()

    def _on_yazim_yuklendi(self, denetleyici):
        self._yazim_denetleyici = denetleyici
        self._output_panel.yazim_mesgul("")
        self._yazim_calistir()

    def _on_yazim_hata(self, mesaj: str):
        self._yazim_anahtar = None
        self._output_panel.yazim_mesgul("")
        # spylls yoksa ya da sözlük dosyası bulunamadıysa: sessizce yutma,
        # kullanıcı "Denetle"ye bastı ve bir şey beklemekte.
        QMessageBox.warning(
            self, _("Yazım Denetimi"),
            _("Sözlük yüklenemedi.\n\n{hata}\n\nSözlük dizini: {dizin}")
            .format(hata=mesaj, dizin=sozluk_dizini()))

    def _yazim_calistir(self):
        ed = self._current_editor()
        if ed is None or self._yazim_denetleyici is None:
            return
        from core.yazim import kelimeleri_cikar
        metin = ed.text()
        # TEK tarama. Eskiden `denetle(metin)` kendi içinde tarıyor, sonraki
        # satır yalnız kelime saymak için AYNI taramayı baştan yapıyordu:
        # 73 KB'lık bir bölümde 62 ms boşa gidiyordu (ölçüldü, 2.11x).
        kelimeler = kelimeleri_cikar(metin)
        bulgular = self._yazim_denetleyici.denetle_kelimeler(
            kelimeler, buyuk_atla=True)
        toplam = sum(1 for k in kelimeler if len(k.kelime) >= 3)
        self._output_panel.show_yazim(bulgular, ed.file_path or "", toplam)

    # -- sağ tık --
    def _on_yazim_oneri(self, kelime: str):
        if self._yazim_denetleyici is None:
            return
        # Öneri üretimi YAVAŞ (ölçüldü: 0.1-1.2 sn/kelime), o yüzden yalnız
        # istendiğinde ve tek kelime için.
        self._status.showMessage(_("Öneriler aranıyor..."))
        try:
            oneriler = self._yazim_denetleyici.oneriler(kelime)
        finally:
            self._status.clearMessage()
        if not oneriler:
            QMessageBox.information(self, _("Yazım Denetimi"),
                                    _("'{k}' için öneri bulunamadı.")
                                    .format(k=kelime))
            return
        secim, tamam = QInputDialog.getItem(
            self, _("Yazım Denetimi"),
            _("'{k}' yerine:").format(k=kelime), oneriler, 0, False)
        if tamam and secim:
            self._yazim_degistir(kelime, secim)

    def _yazim_degistir(self, eski: str, yeni: str):
        """Seçilen öneriyi belgede uygula, YALNIZ tarayıcının kelime saydığı
        yerlerde.

        Eskiden düz `metin.replace(eski, yeni)` yapılıyordu ve `str.replace`
        kelime sınırı tanımıyor. Ölçüldü, üçü de belgeyi bozuyordu:
          `sec` -> `seç`  : `\\section` -> `\\seçtion`, belge DERLENEMEZ oluyor
          `ver` -> `veri` : `Universite` -> `Univerisite`, doğru kelime bozuluyor
          `ab`  -> `ap`   : `$x = ab + 1$` içindeki matematik bozuluyor
        Oysa tarayıcı komutların, matematiğin ve verbatim'in içini bilerek hiç
        denetlemiyor; oralarda bulgu zaten hiç oluşmuyor.

        Konum bilgisi buraya ULAŞMIYOR (panel sinyali yalnız kelimeyi taşıyor),
        o yüzden "hepsini değiştir" davranışı korunuyor; değişen tek şey,
        artık yalnız DÜZ METİN geçişlerinin değişmesi.

        Aksan makrosuyla yazılmış geçişler (`M\\"{u}hendislik`) atlanıyor:
        özgün metindeki uzunluk çözülmüş kelimeden farklı, ofsetle kesmek
        onları bozardı. Bozmaktansa dokunmamak doğru.
        """
        ed = self._current_editor()
        if ed is None:
            return
        from core.yazim import kelimeleri_cikar
        metin = ed.text()
        yerler = [k.ofset for k in kelimeleri_cikar(metin)
                  if k.kelime == eski
                  and metin[k.ofset:k.ofset + len(eski)] == eski]
        if not yerler:
            return
        # Sondan başa: her değişim kendinden SONRAKİ ofsetleri kaydırır.
        for o in reversed(yerler):
            metin = metin[:o] + yeni + metin[o + len(eski):]
        ed.setText(metin)
        self._status.showMessage(
            _("'{e}' -> '{y}' değiştirildi").format(e=eski, y=yeni), 4000)
        self._yazim_calistir()

    def _on_yazim_sozluge_ekle(self, kelime: str):
        if self._yazim_denetleyici is None:
            return
        if self._yazim_denetleyici.kullaniciya_ekle(kelime):
            self._status.showMessage(
                _("'{k}' sözlüğe eklendi").format(k=kelime), 4000)
        self._yazim_calistir()

    def _cleanup_yazim(self):
        """Kapanışta iş parçacığını bekle. Yarıda kalan QThread çökmeye yol
        açıyor (bu depoda yaşandı: GC sırasında SIGABRT)."""
        t = getattr(self, "_yazim_thread", None)
        if t is not None and t.isRunning():
            t.quit()
            t.wait(3000)
