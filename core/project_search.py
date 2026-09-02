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
# gerçekten açılabilmesi gerekiyor.
KAYNAK_UZANTILARI = (".tex", ".cls", ".sty", ".bib")

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


def coz(ham: bytes) -> str:
    """Baytları metne çevir — UTF-8, olmazsa Türkçe eski kodlamalar.

    gui/editor.py'deki `_decode_bytes` ile AYNI sıra: cp1254/iso-8859-9 ile
    yazılmış eski Türkçe .tex dosyaları aramada da doğru okunmalı, yoksa
    'Ş' arayan kullanıcı kendi dosyasında sonuç alamaz. Burada kodlama ADI
    döndürülmüyor: arama dosyayı yazmıyor, round-trip derdi yok.
    """
    for enc in ("utf-8", "cp1254", "iso-8859-9"):
        try:
            return ham.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return ham.decode("utf-8", errors="replace")


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
        # Hız yolu: dosyada hiç geçmiyorsa satır satır bakma. Tipik projede
        # dosyaların çoğu bu daldan çıkar.
        if aranan not in (metin if case_sensitive else kucult(metin)):
            continue
        for no, satir in enumerate(metin.split("\n"), 1):
            karsilastirilan = satir if case_sensitive else kucult(satir)
            bas = karsilastirilan.find(aranan)
            if bas < 0:
                continue
            gosterilen = satir.strip()[:_SATIR_KIRP]
            while bas >= 0:
                bulgular.append(Bulgu(yol, no, bas, gosterilen))
                if len(bulgular) >= limit:
                    return bulgular, True
                bas = karsilastirilan.find(aranan, bas + 1)
    return bulgular, False


def dosyaya_gore_grupla(bulgular: list[Bulgu]) -> list[tuple[str, list[Bulgu]]]:
    """Bulguları dosya sırasını koruyarak grupla — sunum kolaylığı için."""
    gruplar: dict[str, list[Bulgu]] = {}
    for b in bulgular:
        gruplar.setdefault(b.path, []).append(b)
    return list(gruplar.items())
