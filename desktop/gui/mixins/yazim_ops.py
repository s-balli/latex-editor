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

import atexit
import lzma
import os
import re
import sys

from PyQt6.QtCore import QCoreApplication, QStandardPaths, QThread, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
                             QInputDialog, QLabel, QListWidget, QMessageBox,
                             QVBoxLayout)

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
    # İKİ dosya da şart. Eskiden yalnız `.dic`e bakılıyordu: `.aff` eksikken
    # dizin döndürülüyor ve spylls FileNotFoundError ile patlıyordu
    # (ölçüldü 2026-09-07).
    if all(os.path.isfile(os.path.join(dizin, dil + u))
           for u in (".dic", ".aff")):
        return dizin
    return ""


def _guncel_mi(cikti: str, kaynak: str) -> bool:
    """Açılmış dosya arşivin TAMAMINI taşıyor mu. ÖLÇÜT BOYUT.

    Ölçüt `scripts/sozluk_ac.py::ac` ile AYNI olmak zorunda: ikisi de aynı
    soruyu soruyor (bu ham dosya güncel mi, yoksa `.xz`den yeniden açılmalı
    mı) ve ikisi de aynı dizine yazıyor. `tests/test_yazim_gui.py` içindeki
    kapı ikisinin aynı cevabı verdiğini sınıyor.

    Burada eskiden BAŞKA bir ölçüt vardı: `.dic`in kendi sayaç satırına
    bakan bir sezgi, `.aff` için ise YALNIZ VARLIK. Asimetri ölçüldü
    (2026-09-10, taze bir sözlük dizininde):

        kırpık `.dic`  -> onarıldı
        kırpık `.aff`  -> ONARILMADI, sözlük `make_affix() missing 2
                          required positional arguments` ile hiç
                          yüklenmiyor ve durum KALICI

    Yani atlanan dosyanın başarısızlığı daha ağır: kullanıcı her "Denetle"de
    anlaşılmaz bir Python hatası görüyor ve uygulama kendini hiç toparlamıyor.
    Sezgi zaten arşivin kendisi elde olduğu için gereksizdi.
    """
    try:
        with lzma.open(kaynak, "rb") as f:
            beklenen = len(f.read())
    except (OSError, lzma.LZMAError):
        log.warning("Sözlük arşivi okunamadı: %s", kaynak, exc_info=True)
        return True                  # arşiv bozuk: ham dosyaya dokunma
    try:
        return os.path.getsize(cikti) == beklenen
    except OSError:
        return False


def _xz_ac(kaynak: str, cikti: str) -> bool:
    """`.xz` arşivini ATOMİK aç: yanına yaz, sonra yerine koy.

    Doğrudan hedefe yazmak yarıda kesilince KIRPIK dosya bırakıyor ve eski
    kod onu "var" sayıp bir daha hiç açmıyordu. ÖLÇÜLDÜ (2026-09-07): yarısı
    yazılmış tr_TR.dic spylls'e HATASIZ yükleniyor ve `lookup("kelime")`
    False dönüyor, yani doğru kelimeler yanlış işaretleniyor. Kullanıcı
    hiçbir uyarı görmüyor, üstelik durum kalıcı.

    Uygulama aynı kuralı `EditorWidget._write_atomic`ta zaten yazıyor.
    """
    gecici = cikti + ".tmp"
    try:
        with lzma.open(kaynak, "rb") as f:
            veri = f.read()
        with open(gecici, "wb") as f:
            f.write(veri)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, cikti)
        log.info("Sözlük açıldı: %s", cikti)
        return True
    except (OSError, lzma.LZMAError):
        # Salt okunur dizin ya da bozuk arşiv: özellik kapalı kalır,
        # uygulama çalışmaya devam eder.
        log.warning("Sözlük açılamadı: %s", kaynak, exc_info=True)
        try:
            os.remove(gecici)
        except OSError:
            pass
        return False


def _sikistirilmisi_ac(dizin: str, dil: str) -> None:
    """Ham sözlük yoksa ya da BOZUKSA `.xz`den aç.

    Sözlük depoda SIKIŞTIRILMIŞ duruyor (ham `.dic` 8.6 MB, deponun bütün
    geçmişi 3.45 MB idi). Paketlenmiş uygulamada `.spec` yapım sırasında
    açtığı için ham dosyalar zaten var ve buraya hiç girilmiyor.

    Ama KAYNAKTAN çalıştıran biri için ham dosya YOK: taze bir kopyada
    `sozlukler/` içinde yalnız `.xz` bulunuyor, `_sozluk_dizini_gerekli_mi`
    boş dönüyor ve yükleme anlaşılmaz bir hata diyaloğuyla düşüyordu.

    Karar dosya BAŞINA ve İKİ DOSYA için aynı ölçütle veriliyor
    (`_guncel_mi`). Eskiden tek bakış `.dic` VAR MI idi ve iki hâl kalıcı
    olarak bozuk kalıyordu (ölçüldü 2026-09-07, ikisi de yeniden
    açılmıyordu):
      kırpık `.dic`   -> sözlük hatasız yükleniyor, doğru kelimeler yanlış
      `.aff` eksik    -> FileNotFoundError
    Sonra `.dic` için sağlamlık soruluyor ama `.aff` için yalnız varlığa
    bakılıyordu; kırpık `.aff` de kalıcı olarak bozuk kalıyordu (ölçüldü
    2026-09-10, bkz. `_guncel_mi`).

    `.xz` YOKSA hiçbir şey yapılmıyor: onarılacak kaynak yok. Paketlenmiş
    uygulamada durum tam bu (`.spec` yalnız ham iki dosyayı alıyor, arşivi
    almıyor), yani orada bu işlev hiçbir maliyet üretmiyor.
    """
    for ad in (dil + ".dic", dil + ".aff"):
        cikti = os.path.join(dizin, ad)
        kaynak = cikti + ".xz"
        if not os.path.isfile(kaynak):
            continue
        if _guncel_mi(cikti, kaynak):
            continue
        if not _xz_ac(kaynak, cikti):
            return


def kullanici_sozlugu_yolu(dil: str) -> str:
    """Kullanıcının eklediği kelimeler.

    Log dizininin komşusu DEĞİL: log GenericDataLocation'da
    (`%LOCALAPPDATA%\\LatexEditor`), bu ise AppLocalDataLocation'da ve o
    uygulamanın ADINI yola katıyor (bkz. core/log.py). ÖLÇÜLDÜ (2026-09-29,
    v1.1.2 exe): `%LOCALAPPDATA%\\LaTeX Editor\\LatexEditor\\sozluk-tr_TR.txt`.
    Yol yine de kararlı: yalnız çalışma anında soruluyor, ad main.py'de
    ondan önce veriliyor. Taşınırsa eski dosya taşınmalı, yoksa kullanıcının
    kelimeleri kaybolur.
    """
    kok = os.path.normpath(os.path.join(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation),
        "LatexEditor"))
    return os.path.join(kok, "sozluk-%s.txt" % dil)


class YazimYukleThread(QThread):
    """Sözlüğü arka planda yükler. ÖLÇÜLDÜ: tr_TR boş makinede 3.5 sn,
    işlemci doluyken 7-8 sn (2026-10-04). Kesilemiyor; kapanışta bkz.
    `YazimOpsMixin._cleanup_yazim`."""
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


# Kapanışta BİTMEMİŞ sözlük yüklemeleri: pencereden ayrılıp burada tutuluyor
# ve süreç çıkarken bekleniyor (bkz. `YazimOpsMixin._cleanup_yazim`). PDF
# çizim işçisi aynı kalıbı kullanıyor (pdf_render_worker._alive_workers).
_KAPANIS_BEKLEMESI_MS = 3000
_kapanista_bitmeyen: list = []


def _cikista_yuklemeleri_bekle():
    for t in _kapanista_bitmeyen:
        t.wait(30000)


atexit.register(_cikista_yuklemeleri_bekle)


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
        self._output_panel.yazim_bulgusu_secildi.connect(
            self._on_yazim_bulgusu_secildi)
        self._output_panel.yazim_sozlugu_istendi.connect(
            self._yazim_sozlugunu_ac)

    # -- menü --
    def _yazim_denetle(self):
        """Menü/kısayol: Yazım sekmesini açıp denetimi başlat.

        Dili belgeden çıkarıp seçiciye yazıyor; kullanıcı yine değiştirebilir.
        """
        ed = self._current_editor()
        if ed is not None:
            from core.yazim import belgeden_dil
            # Belgenin kendi bildirimi önce; bölüm dosyasında dil (babel,
            # polyglossia) KÖK belgede duruyor (bkz. edit_ops._proje_tabani).
            # ÖLÇÜLDÜ (2026-09-23, İngilizce tez, `% !TEX root` yok): bölümde
            # seçici tr_TR kaldı, İngilizce metin Türkçe sözlükle denetlendi.
            dil = belgeden_dil(ed.text())
            if not dil and ed.file_path:
                dil = belgeden_dil(self._proje_tabani(ed)[1])
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
        self._output_panel.show_yazim(bulgular, ed.file_path or "", toplam, metin)

    # -- sağ tık --
    def _on_yazim_oneri(self, kelime: str, dosya: str = ""):
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
            self._yazim_degistir(kelime, secim, dosya)

    def _yazim_degistir(self, eski: str, yeni: str, dosya: str = ""):
        """Seçilen öneriyi belgede uygula, YALNIZ tarayıcının kelime saydığı
        yerlerde.

        Eskiden düz `metin.replace(eski, yeni)` yapılıyordu ve `str.replace`
        kelime sınırı tanımıyor. Ölçüldü, üçü de belgeyi bozuyordu:
          `sec` -> `seç`  : `\\section` -> `\\seçtion`, belge DERLENEMEZ oluyor
          `ver` -> `veri` : `Universite` -> `Univerisite`, doğru kelime bozuluyor
          `ab`  -> `ap`   : `$x = ab + 1$` içindeki matematik bozuluyor
        Oysa tarayıcı komutların, matematiğin ve verbatim'in içini bilerek hiç
        denetlemiyor; oralarda bulgu zaten hiç oluşmuyor.

        Hedef belge `dosya` ile geliyor, `_current_editor()` DEĞİL. Ölçüldü
        (2026-09-07): A.tex denetlenip B.tex sekmesine geçildikten sonra
        panelde duran bulguya sağ tık -> "Öneriler..." -> düzeltme B.tex'e
        yazıldı, A.tex'e hiç dokunulmadı ve durum çubuğu "değiştirildi" dedi.
        Bulgu listesi sekme değişiminde temizlenmiyor (derlemeyi de aşıyor),
        yani bu yol sıradan kullanımda açık. `dosya` boşken eski davranış
        sürüyor: doğrudan çağıran testler ve konumsuz kullanımlar için.

        SATIR/SÜTUN yine ulaşmıyor, o yüzden "hepsini değiştir" davranışı
        korunuyor; değişen tek şey, artık yalnız DÜZ METİN geçişlerinin ve
        yalnız DOĞRU BELGEDE değişmesi.

        Aksan makrosuyla yazılmış geçişler (`M\\"{u}hendislik`) atlanıyor:
        özgün metindeki uzunluk çözülmüş kelimeden farklı, ofsetle kesmek
        onları bozardı. Bozmaktansa dokunmamak doğru.

        Değişim `_replace_in_editor` üzerinden gidiyor, `setText` ile DEĞİL.
        Ölçüldü (2026-09-07): `setText` belgenin bütün geri alma geçmişini
        siliyor (`isUndoAvailable` True -> False), yani yalnız öneri değil,
        kullanıcının o oturumda yazdığı HER ŞEY geri alınamaz oluyor; üstelik
        imleç belgenin sonuna, görünüm de en başa atlıyordu.
        """
        ed = self._editor_by_path(dosya) if dosya else self._current_editor()
        if ed is None:
            # Bulgu bayat: denetimden sonra sekme kapanmış olabilir. Sessizce
            # cari belgeye yazmak yanlış belgeyi bozardı.
            self._status.showMessage(
                _("Bulgunun geldiği belge açık değil: {name}").format(
                    name=os.path.basename(dosya) or dosya), 4000)
            return
        if dosya:
            # Değişiklik GÖRÜNÜR olsun: sol tık da hedef sekmeye geçiyor.
            self._editor_tabs.setCurrentWidget(ed)
        from core.yazim import kelimeleri_cikar
        metin = ed.text()
        yerler = [k.ofset for k in kelimeleri_cikar(metin)
                  if k.kelime == eski
                  and metin[k.ofset:k.ofset + len(eski)] == eski]
        if not yerler:
            # Bulgu bayat olabilir (kullanıcı arada kelimeyi kendisi
            # düzeltmiş/silmiş). Sessizce dönmek "öneriyi seçtim, hiçbir şey
            # olmadı"ya benziyordu; ölçüldü, durum çubuğuna tek satır bile
            # düşmüyordu.
            self._status.showMessage(
                _("'{e}' belgede bulunamadı, değiştirilmedi").format(e=eski),
                4000)
            return
        self._replace_in_editor(ed, [(o, o + len(eski)) for o in yerler],
                                yeni, imleci_koru=True)
        self._status.showMessage(
            _("'{e}' -> '{y}' değiştirildi").format(e=eski, y=yeni), 4000)
        self._yazim_calistir()

    def _on_yazim_sozluge_ekle(self, kelime: str):
        if self._yazim_denetleyici is None:
            return
        if self._yazim_denetleyici.kullaniciya_ekle(kelime):
            self._status.showMessage(
                _("'{k}' sözlüğe eklendi").format(k=kelime), 4000)
        else:
            # `kullaniciya_ekle` yazamadığında False dönüyor (salt okunur
            # profil, dolu disk); bu kol sessizdi. Kullanıcı kelimeyi
            # ekliyor, kelime bulgularda KALIYOR ve sebebini öğrenemiyordu.
            self._status.showMessage(
                _("'{k}' sözlüğe eklenemedi, kullanıcı sözlüğü yazılamıyor")
                .format(k=kelime), 6000)
        self._yazim_calistir()

    def _on_yazim_bulgusu_secildi(self, dosya: str, satir: int, sutun: int,
                                  kelime: str):
        """Bulguya tıklandı: satıra değil KELİMEYE git ve onu seç.

        Eskiden satıra gidiliyordu ve imleç 1. sütunda kalıyordu; uzun bir
        paragraf satırında kullanıcı kelimeyi gözle arıyordu. Liste
        kurulduktan sonra satır değişmiş olabilir: kelime o satırda sütuna en
        yakın geçişte aranıyor. Aksan makrosuyla yazılmış kelime
        (`M\\"{u}hendislik`) metinde bu biçimde geçmiyor; o zaman imleç
        sütuna konuyor.
        """
        self._goto_line(dosya, satir)
        ed = self._editor_by_path(dosya) if dosya else self._current_editor()
        if ed is None or satir < 1 or satir > ed.lines():
            return
        metin = ed.text(satir - 1).rstrip("\r\n")
        yerler = [m.start() for m in re.finditer(re.escape(kelime), metin)] \
            if kelime else []
        if not yerler:
            ed.setCursorPosition(satir - 1, min(sutun, len(metin)))
            return
        bas = min(yerler, key=lambda i: abs(i - sutun))
        ed.setSelection(satir - 1, bas, satir - 1, bas + len(kelime))

    def _yazim_sozlugunu_ac(self, dil: str):
        """Kişisel sözlükteki kelimeleri göster; seçilenleri çıkar.

        "Sözlüğe ekle"nin tersi. Eklenen kelime bulgulardan düşüyor, yani
        yanlışlıkla eklenen bir kelimeyi geri almanın arayüzde yolu yoktu
        (dosyayı elle bulup düzenlemek gerekiyordu, bkz.
        `kullanici_sozlugu_yolu`). Sözlük yüklü değilse büyük sözlük
        YÜKLENMİYOR: yalnız kullanıcının dosyası okunuyor.
        """
        from core.yazim import Denetleyici

        d = self._yazim_denetleyici
        if d is None or d.dil != dil:
            d = Denetleyici(dil=dil, kullanici_sozlugu=kullanici_sozlugu_yolu(dil))
        dlg = QDialog(self)
        dlg.setWindowTitle(_("Kişisel Sözlük"))
        dlg.setMinimumWidth(360)
        kutu = QVBoxLayout(dlg)
        liste = QListWidget()
        liste.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        liste.addItems(d.kullanici_kelimeleri())
        kutu.addWidget(QLabel(_("Eklediğiniz kelimeler ({dil}):").format(dil=dil)))
        kutu.addWidget(liste)
        yol = QLabel(_("Dosya: {yol}").format(yol=d.kullanici_sozlugu))
        yol.setWordWrap(True)
        kutu.addWidget(yol)
        dugmeler = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        cikar = dugmeler.addButton(_("Çıkar"),
                                   QDialogButtonBox.ButtonRole.ActionRole)
        cikar.setEnabled(False)
        liste.itemSelectionChanged.connect(
            lambda: cikar.setEnabled(bool(liste.selectedItems())))
        dugmeler.rejected.connect(dlg.reject)
        cikarilan = []

        def _cikar():
            for oge in liste.selectedItems():
                kelime = oge.text()
                if not d.kullanicidan_cikar(kelime):
                    self._status.showMessage(
                        _("'{k}' sözlükten çıkarılamadı, kullanıcı sözlüğü "
                          "yazılamıyor").format(k=kelime), 6000)
                    return
                liste.takeItem(liste.row(oge))
                cikarilan.append(kelime)

        cikar.clicked.connect(_cikar)
        kutu.addWidget(dugmeler)
        dlg.exec()
        if not cikarilan:
            return
        self._status.showMessage(
            _("{n} kelime sözlükten çıkarıldı").format(n=len(cikarilan)), 4000)
        if d is self._yazim_denetleyici:
            # Denetim bu sözlükle yapıldı: tazele, çıkarılan kelime geri gelsin.
            self._yazim_calistir()

    def _cleanup_yazim(self):
        """Kapanışta sözlük yüklemesini bekle; bitmezse pencereden ayır.

        Yarıda kalan QThread çökmeye yol açıyor (bu depoda yaşandı: GC
        sırasında SIGABRT). Bekleme sınırlı ama yükleme kesilemiyor ve
        süresi beklemeyi aşıyordu. ÖLÇÜLDÜ (2026-10-04): işlemci doluyken
        tr_TR 7-8 sn; "Denetle"den hemen sonra kapanınca 3 sn beklenip
        vazgeçiliyor, çıkışta pencere silinirken çalışan iş parçacığı da
        siliniyordu: "QThread: Destroyed while thread is still running",
        süreç Aborted (WSL'de yeniden üretildi; 1 sn'lik yüklemede temiz).
        Ayrılan iş parçacığı modülde tutulup çıkışta bekleniyor, yani pencere
        bekletilmeden kapanıyor. Sonucunu artık kimse beklemediği için
        sinyalleri kesiliyor. `quit()` yok: `run()` olay döngüsü işletmiyor.
        """
        t = getattr(self, "_yazim_thread", None)
        if t is None or not t.isRunning() or t.wait(_KAPANIS_BEKLEMESI_MS):
            return
        for sinyal in (t.yuklendi, t.hata):
            try:
                sinyal.disconnect()
            except TypeError:
                pass                            # bağlı alıcı yok
        t.setParent(None)
        _kapanista_bitmeyen.append(t)
