"""Dosya/klasör oluşturma, yeniden adlandırma: Qt'süz saf katman.

Ayrım `core/project_search.py` ile aynı: karar ve dosya sistemi işi burada,
menü/dialog/çeviri `gui/file_tree.py` tarafında. Böylece adlandırma kuralları
GUI kurmadan sınanabiliyor.

AD KURALLARI NEDEN WINDOWS'A GÖRE (her platformda):
Bu editör Windows'ta çalışıp WSL'de derliyor; projeler iki dünya arasında
gidip geliyor ve git ile paylaşılıyor. Linux'ta `rapor<1>.tex` yaratmak
serbest ama o dosya Windows'ta AÇILAMIYOR. Bu yüzden kurallar iki tarafın
KESİŞİMİ: her yerde en dar küme uygulanıyor. Aksi hâlde hata, dosyayı
yaratan makinede değil karşı taraftaki makinede patlıyor.
"""

import os
import re

# Editörün KAYNAK sayıp açtığı uzantılar. TEK KAYNAK: klasör ağacı, hızlı aç,
# projede ara, "Birlikte Aç" ve sürükle-bırak hepsi buradan alır.
#
# ALTI ayrı kopya vardı (file_tree ×2, main_window ×2, quick_open,
# project_search) ve altısı da aynıydı, yani canlı hata yoktu; kırılma bir
# sonraki uzantı eklendiğinde geliyordu. Ölçüldü 2026-09-06: kopyalardan
# BİRİNE `.ltx` eklemek üç yüzeyi ayrıştırıyor ("Birlikte Aç" açıyor, hızlı
# aç listelemiyor, projede ara aramıyor, ağaç düzenlenebilir saymıyor).
# Depo bu dersi bir kez almıştı ama yalnız iki yüzeyi bağlamıştı
# (bkz. main_window._OPENABLE_EXT yorumu). Kopyalardan biri
# (file_tree._EXTENSIONS) zaten ölüydü: tanımlı, hiç okunmuyor.
#
# Demet (küme değil): `str.endswith` demet istiyor (quick_open).
KAYNAK_UZANTILARI = (".tex", ".cls", ".sty", ".bib")

# Windows'ta dosya adında yasak karakterler. Ayraçlar (/ \) ayrıca yasak:
# bu modül TEK bir klasör içinde iş yapıyor, ad yol taşıyamaz.
_YASAK_KARAKTER = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows aygıt adları. Uzantı EKLENSE de rezerve: "CON.tex" de açılamaz.
_AYGIT_ADLARI = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)

# Çoğu dosya sisteminin ad sınırı: 255. BİRİMİ ÖNEMLİ ve iki tarafta farklı:
# ext4/APFS 255 BAYT, NTFS 255 UTF-16 KOD BİRİMİ sayıyor.
#
# Eskiden yalnız `len(ad)` (karakter) bakılıyordu ve buradaki yorum gerekçeyi
# TERS kurmuştu ("karakter sınırı daha dar olanı seçiyor"). Ölçüldü, tersi
# doğru: 128 Türkçe harf 256 BAYT eder ve dosya ext4'te YARATILAMIYOR, ama
# `ad_hatasi` onu "geçerli" sayıyordu. Kullanıcı anlaşılır "Ad çok uzun"
# uyarısı yerine ham `OSError` görüyordu ("Oluşturulamadı: [Errno 36] ...").
#
# Modülün baştaki ilkesi gereği İKİ KURALIN KESİŞİMİ uygulanıyor.
_MAX_AD = 255

# Hata gerekçeleri. Çeviri GUI'nin işi: bu katman Qt'ye bağlı değil ve
# gerekçeler testlerde string karşılaştırmasıyla sabitleniyor.
BOS = "bos"
YASAK_KARAKTER = "yasak_karakter"
AYGIT_ADI = "aygit_adi"
SONU_NOKTA_BOSLUK = "sonu_nokta_bosluk"
NOKTA_ADI = "nokta_adi"
COK_UZUN = "cok_uzun"


def ad_hatasi(ad: str) -> str:
    """Dosya/klasör adı geçerli mi. Geçerliyse "" döner, değilse gerekçe kodu.

    Kırpma YAPMIYOR: çağıran ne verdiyse onu denetliyor. Baştaki/sondaki
    boşluğu sessizce atmak, kullanıcının gördüğü adla diskteki adın
    ayrışması demek olurdu.
    """
    if not ad or not ad.strip():
        return BOS
    if ad in (".", ".."):
        return NOKTA_ADI
    if _YASAK_KARAKTER.search(ad):
        return YASAK_KARAKTER
    # Windows sondaki nokta ve boşluğu SESSİZCE atıyor: "not .tex " diye
    # yaratılan dosya "not .tex" oluyor ve kullanıcı adını bulamıyor.
    if ad[-1] in " .":
        return SONU_NOKTA_BOSLUK
    # Aygıt denetimi uzantıdan ÖNCEKİ kısımda: "CON", "CON.tex", "con.TEX".
    govde = ad.split(".", 1)[0].upper()
    if govde in _AYGIT_ADLARI:
        return AYGIT_ADI
    utf8_bayt = len(ad.encode("utf-8"))              # ext4/APFS sınırı
    utf16_birim = len(ad.encode("utf-16-le")) // 2   # NTFS sınırı
    if max(utf8_bayt, utf16_birim) > _MAX_AD:
        return COK_UZUN
    return ""


def ayni_dosya_mi(a: str, b: str) -> bool:
    """İki yol aynı dosyayı mı gösteriyor (büyük/küçük harf farkı dahil).

    Windows'ta `rapor.tex` → `Rapor.tex` MEŞRU bir yeniden adlandırma, ama
    `os.path.exists` dosya sistemi harf duyarsız olduğu için True döner.
    Düz bir "hedef var mı" denetimi bu işlemi haksız yere engellerdi.
    """
    a, b = os.path.normpath(a), os.path.normpath(b)
    if a == b:
        return True
    try:
        return os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b)
    except OSError:
        return False


def hedef_dolu_mu(yol: str, *, eski: str = "") -> bool:
    """`yol` zaten kullanımda mı. `eski` verilirse harf-varyantı çarpışma sayılmaz."""
    if not os.path.exists(yol):
        return False
    if eski and ayni_dosya_mi(yol, eski):
        return False
    return True


def yeni_dosya(dizin: str, ad: str) -> str:
    """Boş dosya yarat, mutlak yolunu döndür.

    `x` kipi bilinçli: dosya varsa üstüne yazmak yerine FileExistsError.
    Denetim ile yaratma arasında dosya belirse (başka pencere, git checkout)
    sessizce içerik silinirdi.
    """
    yol = os.path.join(dizin, ad)
    with open(yol, "x", encoding="utf-8"):
        pass
    return yol


def yeni_klasor(dizin: str, ad: str) -> str:
    """Klasör yarat, mutlak yolunu döndür. Varsa FileExistsError."""
    yol = os.path.join(dizin, ad)
    os.mkdir(yol)
    return yol


def yeniden_adlandir(yol: str, yeni_ad: str) -> str:
    """Dosya/klasörü aynı dizin içinde yeniden adlandır, yeni yolu döndür.

    `os.rename` POSIX'te var olan hedefin ÜSTÜNE yazar (sessiz veri kaybı);
    çağıran `hedef_dolu_mu` ile önceden denetlemeli. Buradaki ikinci denetim
    yarışı tamamen kapatmıyor ama pencereyi daraltıyor.
    """
    dizin = os.path.dirname(os.path.abspath(yol))
    hedef = os.path.join(dizin, yeni_ad)
    if hedef_dolu_mu(hedef, eski=yol):
        raise FileExistsError(hedef)
    os.rename(yol, hedef)
    return hedef
