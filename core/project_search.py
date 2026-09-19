"""Projede ara — kök altındaki tüm kaynak dosyalarda metin araması.

Qt'süz ve saf: dosya yürüyüşü, kodlama çözümü ve eşleştirme burada; sunum
(liste, tıklama, tema) `gui` tarafında. Aynı ayrım `core/latex_refs.py`de de
var ve arka plana taşımayı kolaylaştırıyor.

UYGULAMADAKİ DİĞER ARAMALARDAN FARKI:
- Ctrl+F (gui/find_replace.py) yalnız AÇIK SEKMEDE arar — tek belge.
- PDF araması (gui/pdf_viewer_mixins/_search.py) derlenmiş PDF'te arar.
- Ctrl+P (gui/quick_open.py) dosya ADLARINDA arar, içerikte değil.
Burada aranan şey proje kökü altındaki tüm .tex/.cls/.sty/.bib dosyalarının
İÇERİĞİ — sekmede açık olmayanlar dahil.
"""

import os
import stat
from dataclasses import dataclass

# Yürüyüşe girmeyen dizinler. TEK KAYNAK: gui/file_tree.py ve gui/quick_open.py
# buradan alır. Üç ayrı kopya tutmak, bu depoda paketleme tanımlarında bilfiil
# yaşanan sürükleme hatasının aynısını doğururdu.
SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".svn",
    "build", "dist", ".venv", "venv", ".env",
    ".mypy_cache", ".pytest_cache",
}

# Editörün açabildiği dosya türleri — arama sonucuna tıklayınca dosyanın
# gerçekten açılabilmesi gerekiyor. TEK KAYNAK core.fs_ops; buradaki ad
# korunuyor çünkü `iter_project_files`/`search_project`in varsayılan
# argümanı ve modülün dışa açık yüzeyi.
from core.fs_ops import KAYNAK_UZANTILARI  # noqa: F401

# Sonuç ve maliyet sınırları. Sınıra takılan arama SESSİZ KESİLMEZ:
# search_project ikinci dönüş değeriyle "kesildi" bilgisini verir ve arayan
# bunu kullanıcıya yazar (bu depoda sessiz kırpma daha önce yanıltmıştı).
VARSAYILAN_SINIR = 2000
_MAX_DOSYA_BAYT = 8 * 1024 * 1024      # 8 MB üstü dosya kaynak değil, çıktıdır
_SATIR_KIRP = 200                       # listede gösterilecek satır uzunluğu


@dataclass(frozen=True)
class Bulgu:
    """Tek bir eşleşme. `line` 1-tabanlı (editörün beklediği gibi)."""
    path: str        # mutlak yol
    line: int
    col: int         # 0-tabanlı sütun
    text: str        # satırın kırpılmış hâli (baştaki boşluk atılmış)


def kucult(s: str) -> str:
    """Harf duyarsız karşılaştırma için küçült — Türkçe noktalı İ dahil.

    Düz `str.lower()` YETMİYOR: Unicode 'İ'yi 'i' + U+0307 (birleşen nokta)
    yapıyor, yani metindeki 'İçindekiler' ile kullanıcının yazdığı
    'içindekiler' eşleşmiyor. Ölçüldü — beş gerçekçi Türkçe sorgudan DÖRDÜ
    düz lower() ile kaçıyordu:

        icerik: "İçindekiler ve İSTANBUL"
        sorgu            lower()   bu fonksiyon
        içindekiler      YOK       VAR
        İÇİNDEKİLER      YOK       VAR
        istanbul         YOK       VAR
        ISTANBUL         YOK       VAR

    Türkçe LaTeX belgesi bu başlıklarla dolu (\\section{İçindekiler},
    \\caption{Şekil ...}), yani sorun kenar durumu değil.

    ı/i ayrımı KORUNUYOR: yalnız birleşen nokta atılıyor, harf eşlemesi
    değişmiyor ('IŞIK' → 'işik', 'ışık' → 'ışık' — ikisi hâlâ farklı).

    UZUNLUK KORUNUR, dolayısıyla `col` ofsetleri kayamaz: tüm Unicode
    taranarak denendi, uzunluğu değişen TEK karakter U+0307'nin kendisi
    (kaynakta yalnız başına birleşen nokta). 'İ'.lower() iki karakter
    üretiyor ama eklediği tam da U+0307 olduğu için silince eski uzunluğa
    dönülüyor.
    """
    return s.lower().replace("̇", "")


_BIRLESEN_NOKTA = "̇"


def _katlanmis(metin: str) -> tuple[str, list[int]]:
    """(katlanmış metin, her katlanmış karakterin ÖZGÜN indisi).

    NEDEN HARİTA. ``kucult`` uzunluğu KORUMUYOR: gövdesi birleşen noktayı
    siliyor ve o nokta metinde tek başına da bulunabiliyor. Ayrıştırılmış
    (NFD) bir `İ` harfi tam olarak `I` + U+0307, yani böyle bir metinde
    katlanmış dizge özgünden kısa kalıyor ve o noktadan sonraki bütün
    ofsetler kayıyor. NFD gerçek bir kaynak: macOS dosya adlarını öyle
    üretiyor, PDF ve web'den kopyalanan metin öyle gelebiliyor.

    ÖLÇÜLDÜ (2026-09-19): `I`+U+0307+`cindekiler sekil` metninde `sekil`
    sorgusu ofset 12 veriyordu ve özgün metnin 12. karakterinden itibaren
    `\\nseki` duruyor. Ctrl+F yanlış yeri seçiyor, "Tümünü Değiştir" yanlış
    yeri değiştiriyordu: `Burada sekil var.` -> `BuradaSEKILl var.`

    KÜÇÜLTME BÜTÜN DİZGEDE yapılıyor, karakter karakter DEĞİL: Yunanca son
    sigma bağlama duyarlı (`ΑΣ`.lower() -> `ας`, karakter karakter `ασ`).
    ÖLÇÜLDÜ: tüm Unicode taranınca tek karakterde hiç ayrışma yok, ama
    dizgede var; o yüzden küçültmeyi `str.lower()` yapıyor, bu döngü yalnız
    hangi katlanmış karakterin hangi özgün karakterden geldiğini sayıyor.
    Son sigma 1'e 1 olduğu için sayım bozulmuyor (ölçüldü: en zorlu 14
    karakterden kurulu 2744 üçlüde uzunluk ayrışması 0).
    """
    alt = metin.lower()
    parcalar: list[str] = []
    harita: list[int] = []
    j = 0
    for i, ch in enumerate(metin):
        for k in range(j, min(j + len(ch.lower()), len(alt))):
            if alt[k] != _BIRLESEN_NOKTA:
                parcalar.append(alt[k])
                harita.append(i)
        j += len(ch.lower())
    return "".join(parcalar), harita


def eslesme_ofsetleri(metin: str, sorgu: str, *,
                      case_sensitive: bool = False):
    """`sorgu`nun `metin` içindeki (baş, bit) aralıkları; ÖZGÜN indislerle.

    TEK KAYNAK: projede arama da, Ctrl+F de buradan geçiyor. İkisi eskiden
    ayrı motorlar kullanıyordu ve harf katlaması AYRIŞMIŞTI: Scintilla'nın
    duyarsız araması yalnız ASCII'yi katlıyor, yani `şekil` sorgusu
    `Şekil`i, `istanbul` sorgusu `İstanbul`u hiç bulmuyordu (ölçüldü
    2026-09-10). Aynı çift bir kez de ÖRTÜŞEN eşleşmelerde ayrışmıştı
    (aşağıdaki nota bakın); iki eksen, aynı kök.

    ÖRTÜŞEN eşleşme sayılmaz: her eşleşmenin SONUNDAN devam ediliyor. Bir
    karakter ilerlemek uygulamayı kendisiyle çelişkiye düşürüyordu; aynı
    metin, aynı sorgu (ölçüldü 2026-09-09, Ctrl+F / Projede Ara):

        `a \\\\ b`  sorgu `\\`        ->  2 / 3
        `a      b`  sorgu iki boşluk  ->  3 / 5

    İkisi de gerçek LaTeX sorgusu (satır kırma, fazla boşluk temizliği).
    39 gerçek şablonda `\\` sorgusu 2725 satır gösteriyordu, doğrusu 2629.
    Scintilla'nın motoru (SCI_SEARCHINTARGET) ve `grep -o` da eşleşmenin
    sonundan devam ediyor.

    ARALIK dönüyor, yalnız başlangıç değil: ``kucult`` uzunluğu korumadığı
    için eşleşmenin özgün metindeki uzunluğu ``len(sorgu)`` olmayabilir
    (bkz. ``_katlanmis``). Çağıranlar bitişi buradan almak zorunda.
    """
    if not sorgu:
        return
    if case_sensitive:
        n = len(sorgu)
        bas = metin.find(sorgu)
        while bas >= 0:
            yield bas, bas + n
            bas = metin.find(sorgu, bas + n)
        return
    katlanmis = kucult(metin)
    hedef = kucult(sorgu)
    # KATLANINCA BOŞALAN sorgu: tek başına birleşen nokta böyle. `find("")`
    # her çağrıda aynı konumu döndürüyor ve döngü İLERLEMİYORDU; üreteci
    # `list()`e veren Ctrl+F yolu (bkz. find_replace._yerler) arayüzü
    # süresiz kilitliyor ve belleği şişiriyordu (ölçüldü 2026-09-19: ilk 12
    # sonuç da 0, sayaç artmıyor).
    if not hedef:
        return
    n = len(hedef)
    if len(katlanmis) == len(metin):
        # HIZLI YOL: metinde birleşen nokta yok, yani katlama uzunluğu
        # korumuş ve ofsetler özgün metinde olduğu gibi geçerli. Harita
        # kurmak SADECE bunun bozulduğu metinlerde gerekiyor ve pahalı:
        # ÖLÇÜLDÜ (2026-09-19, gerçek 77 KB'lık .tex) harita her çağrıda
        # 45 ms, bu yol 0.03 ms. Sayaç her tuş vuruşunda buradan geçiyor.
        # Uzunluk denetimi güvenli bir ölçüt: ``kucult`` hiçbir karakteri
        # UZATMIYOR (tüm Unicode tarandı, uzunluğu değiştiren tek kod
        # noktası U+0307 ve o da siliniyor), yani eşit uzunluk "hiç nokta
        # silinmedi" demek.
        b = katlanmis.find(hedef)
        while b >= 0:
            yield b, b + n
            b = katlanmis.find(hedef, b + n)
        return
    katlanmis, harita = _katlanmis(metin)
    b = katlanmis.find(hedef)
    while b >= 0:
        yield harita[b], harita[b + n - 1] + 1
        b = katlanmis.find(hedef, b + n)


# Çözücü zincir TEK KAYNAK core.fs_ops; buradaki ad korunuyor çünkü modülün
# dışa açık yüzeyi (dışa aktarma, .bib denetimi ve testler `coz`u buradan
# alıyor). Kendi gövdesi vardı; üç kopyanın biriydi (bkz. oradaki not).
from core.fs_ops import coz  # noqa: E402,F401


def duz_dosya_mi(yol: str) -> bool:
    """Yol DÜZ bir dosya mı: FIFO, aygıt ya da soket değil.

    Yazan tarafı olmayan bir FIFO'yu okumaya kalkmak SONSUZA DEK blokluyor.
    Proje ağacındaki tek bir `boru.tex` aramayı kilitliyordu ve iptal bayrağı
    da kurtarmıyordu: engel `f.read()` içinde oluşuyor, bayrak ise okuma
    bittikten sonra denetleniyor (ölçüldü 2026-09-02, 30 sn zaman aşımı).

    Linux ve macOS'a özgü; Windows'ta adlandırılmış borular dosya sisteminde
    böyle görünmüyor. Aynı koruma minted taramasında ve latex_refs'in .tex
    yürüyüşünde de var; ikisi de dosyaları AÇIYOR.
    """
    try:
        return stat.S_ISREG(os.stat(yol).st_mode)
    except OSError:
        return False


def iter_project_files(root: str, uzantilar=KAYNAK_UZANTILARI):
    """Kök altındaki kaynak dosyaları mutlak yol olarak üret (sıralı).

    Gizli dizinlere ve SKIP_DIRS'e inilmez. Sıralama belirli olsun diye her
    dizinin girdileri sıralanır — sonuç listesi koşudan koşuya değişmesin.
    """
    if not root or not os.path.isdir(root):
        return
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs
                         if not d.startswith('.') and d not in SKIP_DIRS)
        for fn in sorted(files):
            if not fn.lower().endswith(uzantilar):
                continue
            yol = os.path.join(dirpath, fn)
            if duz_dosya_mi(yol):
                yield yol


def search_project(root: str, query: str, *, case_sensitive: bool = False,
                   limit: int = VARSAYILAN_SINIR,
                   uzantilar=KAYNAK_UZANTILARI,
                   iptal=None) -> tuple[list[Bulgu], bool]:
    """Kök altındaki dosyalarda `query` düz metnini ara.

    Döner: (bulgular, kesildi). `kesildi` True ise sınıra takılmıştır ve
    gösterilen liste eksiktir — arayan bunu kullanıcıya söylemeli.

    `iptal` verilirse her dosyadan önce çağrılır; True dönerse arama durur
    (arka plan işçisi için: yeni sorgu geldiğinde eskisi boşuna sürmesin).

    Bir satırda birden fazla eşleşme varsa her biri ayrı bulgudur; satırın
    metni hepsinde aynıdır ama `col` farklıdır, yani tıklayınca doğru sütuna
    gidilebilir.
    """
    if not query:
        return [], False

    aranan = query if case_sensitive else kucult(query)
    bulgular: list[Bulgu] = []

    for yol in iter_project_files(root, uzantilar):
        if iptal is not None and iptal():
            return bulgular, True
        try:
            if os.path.getsize(yol) > _MAX_DOSYA_BAYT:
                continue
            with open(yol, "rb") as f:
                ham = f.read()
        except OSError:
            # Okunamayan dosya aramayı düşürmez: izin yok, kilitli, ya da
            # yürüyüşle okuma arasında silinmiş olabilir.
            continue
        metin = coz(ham)
        # BOM ATILIYOR: bildirilen sütun EDİTÖRÜN GÖSTERDİĞİ metne göre
        # olmak zorunda, tıklayınca oraya gidiliyor. Çözücü zincirde
        # `utf-8-sig` yok, yani BOM metne U+FEFF olarak giriyor ve 1. satırın
        # bütün ofsetlerini bir kaydırıyor; editör tarafında Scintilla
        # `setText` sırasında onu düşürüyor.
        #
        # ÖLÇÜLDÜ (2026-09-12, gerçek BOM'lu `template14/main.tex`):
        # `documentclass` sütun 2 bildiriliyor, editörde o sütunda
        # `ocumentclass` duruyor. Yalnız 1. satır etkileniyor, BOM orada.
        # Korpusta 231 kaynak dosyanın 1'i BOM taşıyor ve o bir `main.tex`.
        #
        # Yalnız ARAMA metni kırpılıyor; dosya olduğu gibi duruyor.
        if metin.startswith("﻿"):
            metin = metin[1:]
        # Hız yolu: dosyada hiç geçmiyorsa satır satır bakma. Tipik projede
        # dosyaların çoğu bu daldan çıkar.
        if aranan not in (metin if case_sensitive else kucult(metin)):
            continue
        for no, satir in enumerate(metin.split("\n"), 1):
            # Eşleştirme kuralı (harf katlaması ve örtüşen eşleşmeler)
            # `eslesme_ofsetleri`nde; Ctrl+F de aynı işlevi kullanıyor.
            gosterilen = None
            for bas, _bit in eslesme_ofsetleri(satir, query,
                                               case_sensitive=case_sensitive):
                if gosterilen is None:
                    gosterilen = satir.strip()[:_SATIR_KIRP]
                bulgular.append(Bulgu(yol, no, bas, gosterilen))
                # Sınıra DEĞMEK kırpma değildir, sınırı AŞMAK kırpmadır: tam
                # `limit` kadar eşleşme varken liste eksik değil. Eskiden
                # `>= limit` ile tam o anda kesiliyordu ve panel "ilk 5 sonuç
                # (kırpıldı)" yazıyordu (ölçüldü). Modül sessiz kırpmayı
                # bilerek yasaklıyor; OLMAYAN kırpmayı bildirmek aynı yanılgıya
                # ters yönden yol açıyor, kullanıcı listeyi eksik sanıp sorguyu
                # boşuna daraltıyor. Bedeli: durmadan önce en fazla BİR fazla
                # eşleşme bulunur.
                if len(bulgular) > limit:
                    return bulgular[:limit], True
    return bulgular, False


def dosyaya_gore_grupla(bulgular: list[Bulgu]) -> list[tuple[str, list[Bulgu]]]:
    """Bulguları dosya sırasını koruyarak grupla — sunum kolaylığı için."""
    gruplar: dict[str, list[Bulgu]] = {}
    for b in bulgular:
        gruplar.setdefault(b.path, []).append(b)
    return list(gruplar.items())
