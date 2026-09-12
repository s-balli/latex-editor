"""\\ref için \\label, \\cite için .bib anahtar toplama (doküman-farkında tamamlama).

Editörün \\ref{ / \\cite{ tamamlaması için kullanılır. Sadece okur/yazar dosya,
Qt bağımlılığı yok (tıpkı input_parser gibi).
"""

import logging
import os
import re
import time
from dataclasses import dataclass, field

from core.bibtex import RE_GIRDI_ANAHTARI
from core.input_parser import parse_inputs
from core.latex_utils import sozel_soy, strip_comments

_logger = logging.getLogger("latex_editor.latex_refs")

# TANIM deseni. `gui/editor._RE_LABELARG` aynı komutu `*` ile arıyor; orası
# "imleç altındaki anahtar" istiyor, burası TANIM topluyor. Desendeki `+`
# yer tutucuları eliyor (gerçek şablonlar `\label{}` diye doldurulmayı
# bekleyen 9 tane bırakıyor, 6 dosyada, ölçüldü 2026-09-09) ama ASIL GÜVENCE
# DESEN DEĞİL: `\label{ }` bu desenden de geçiyor ve `.strip()` sonrası boş
# anahtar oluyor. O yüzden HER tüketici strip'lenmiş anahtarı süzüyor
# (`_extract_labels`, `label_locations`). Desen değişirse kural bozulmuyor.
_RE_LABEL = re.compile(r'\\label\s*\{([^}]+)\}')

# Bir anahtarda BULUNAMAYACAK karakterler: hepsi LaTeX'in kendi sözdizimi.
# Bunlardan biri varsa yakalanan şey anahtar değil, yanlış eşleşmedir.
# ÖLÇÜLDÜ (2026-09-09, 39 gerçek şablonda) iki üretim:
#   `\newcommand{\pref}[1]{(\ref{#1})}`        -> "Tanımsız \ref: #1"
#   `\pretocmd\citep{\citestyle{semicolon}}`   -> "Tanımsız \cite:
#                                                 \citestyle{semicolon"
# İkisi de kullanıcının düzeltemeyeceği bulgular. Süzgeç KARA LİSTE
# (beyaz liste değil) bilerek: gerçek bir anahtarı yanlışlıkla atmak KIRIK
# bir referansı gizlemek olurdu, o daha kötü.
_ANAHTAR_YASAK = set("\\{}#%$&~^|")


def _anahtar_olabilir(k: str) -> bool:
    return bool(k) and not (_ANAHTAR_YASAK & set(k))
_RE_ADDBIB = re.compile(r'\\addbibresource\s*\{([^}]+\.bib)\}')
_RE_BIBLIO = re.compile(r'\\bibliography\s*\{([^}]+)\}')

# Çocuk dosya (\\input zinciri) label önbelleği: path -> (mtime, [labels])
_label_file_cache: dict[str, tuple[float, list[str]]] = {}
# .bib anahtar önbelleği: bib_path -> (mtime, [keys])
_bib_cache: dict[str, tuple[float, list[str]]] = {}

# Önbellek üst sınırı: uzun oturumda silinmiş/projeden çıkmış dosyaların
# girdileri sonsuza dek birikmesin (LRU: isabet girdiyi taze taşır)
_CACHE_MAX = 64


def _cache_get(cache: dict, key: str):
    """İsabet: değeri döndür ve girdiyi en taze konuma taşı (LRU)."""
    value = cache.get(key)
    if value is not None:
        cache.pop(key)
        cache[key] = value
    return value


def _cache_put(cache: dict, key: str, value) -> None:
    cache[key] = value
    while len(cache) > _CACHE_MAX:
        cache.pop(next(iter(cache)))


def _base_dir(base_path: str) -> str:
    return os.path.dirname(os.path.abspath(base_path)) if base_path else os.getcwd()


def _extract_labels(text: str) -> list[str]:
    """Metinden (yorum ve sözel içerik soyularak) \\label anahtarlarını döndür.

    Sözel soyma ŞART: kod örneğindeki `\\label{x}` gerçek bir tanım değil.
    Tanım sayılırsa gerçek bir `\\ref{x}` "tanımlı" görünür ve KIRIK referans
    gizlenir; ayrıca örnek anahtar tamamlama listesine de düşerdi.

    Süzgeç STRIP'lenmiş anahtara bakıyor. Eskiden ham argümana bakıyordu ve
    `\\label{ }` süzgeçten geçip `.strip()` ile BOŞ anahtara dönüşüyordu.
    ÖLÇÜLDÜ (2026-09-09): boş anahtar etiket evrenine giriyor, denetim onu
    "kullanılmayan etiket" diye BOŞ bir satır olarak gösteriyor ve `\\ref{`
    tamamlaması boş bir öneri sunuyordu. Atıf tarafı (`_kullanim_anahtarlari`)
    strip'ten SONRA süzüyor, yani `\\ref{ }` zaten yok sayılıyordu; asimetri
    yalnız bu koldaydı.
    """
    return [k for k in (m.group(1).strip() for m in _RE_LABEL.finditer(
        sozel_soy(strip_comments(text)))) if _anahtar_olabilir(k)]


def _flatten_input_paths(content: str, base_dir: str) -> list[str]:
    """parse_inputs ağcını düz dosya-yolu listesine indir."""
    paths: list[str] = []

    def walk(nodes):
        for n in nodes:
            paths.append(n['path'])
            walk(n.get('children', []))

    try:
        walk(parse_inputs(content, base_dir))
    except Exception:
        _logger.warning("input zinciri çözülemedi (base: %s)", base_dir, exc_info=True)
    return paths


def collect_labels(content: str, base_path: str) -> list[str]:
    """Mevcut dosya (``content``) + \\input zincirindeki tüm \\label anahtarları.

    Canlı ``content`` her zaman taze değerlendirilir; zincirdeki çocuk dosyalar
    mtime'a göre önbelleklenir (değişmeyen dosya tekrar okunmaz). Sıralı + tekil.
    """
    labels = set(_extract_labels(content))
    bdir = _base_dir(base_path)
    for path in _flatten_input_paths(content, bdir):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        cached = _cache_get(_label_file_cache, path)
        if cached and cached[0] == mtime:
            file_labels = cached[1]
        else:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    file_labels = _extract_labels(f.read())
            except OSError:
                continue
            _cache_put(_label_file_cache, path, (mtime, file_labels))
        labels.update(file_labels)
    return sorted(labels)


def _bib_paths_in(text: str, bdir: str) -> list[str]:
    """Bir metindeki BÜTÜN .bib bildirimlerinin çözülen yolları (sıralı, tekil).

    Üç biçim birden okunuyor ve üçü de gerçek LaTeX:

      \\bibliography{kaynaklar,ek}          virgüllü liste
      \\addbibresource{a.bib}
      \\addbibresource{b.bib}               birden çok bildirim satırı
      \\addbibresource{...} + \\bibliography{...}

    Virgüllü liste eskiden `kaynaklar,ek.bib` diye TEK ad sayılıyordu,
    diskte bulunamıyordu ve fonksiyon boş dönüyordu; yani belgenin
    kaynakçası olduğu hâlde uygulama "kaynakça yok" diyordu. Dışa aktarma
    tarafında aynı ders 2026-09-06'da gerçek pandoc ile ölçülmüştü, ama
    düzeltme yalnız oraya yazılmıştı (bkz. exporter._find_bibliography).
    """
    bulunan: list[str] = []
    for pat in (_RE_ADDBIB, _RE_BIBLIO):
        for m in pat.finditer(text):
            for name in m.group(1).split(','):
                name = name.strip()
                if not name:
                    continue
                if not name.endswith('.bib'):
                    name += '.bib'
                cand = os.path.join(bdir, name)
                if os.path.isfile(cand) and cand not in bulunan:
                    bulunan.append(cand)
    return bulunan


# Zincir taramasının sonucu. Otomatik tamamlama bu fonksiyonu her tuş
# vuruşunda çağırıyor; zincir çözümlemesi 15 dosyalık bir tezde 16 ms
# (ölçüldü, template33-tez). TTL bilinçli: zincirin mtime'ını anahtar yapmak
# zincirin kendisini çözmeyi gerektirirdi, yani pahalı kısmı.
_bib_chain_cache: dict = {}
_BIB_CHAIN_TTL = 2.0


# \bibitem[etiket]{anahtar} GÖVDE ... bir sonraki \bibitem'e ya da ortamın
# sonuna kadar. Gövde serbest metin: .bib gibi alanlara ayrılmış değil.
_RE_BIBITEM_GOVDE = re.compile(
    r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}"
    r"(.*?)(?=\\bibitem|\\end\{thebibliography\}|\Z)", re.DOTALL)

# Gösterim için soyulan biçim komutları. Liste DAR: tanınmayan komutu silmek
# metni bozabilir (\& gibi kaçışlar, \TeX gibi anlam taşıyanlar).
_RE_BICIM = re.compile(r"\\(?:emph|textit|textbf|texttt|textsc|url|href)\s*\{([^{}]*)\}")
_RE_NEWBLOCK = re.compile(r"\\newblock\b")

# Yıl adayı: 1800-2049. Sayfa/cilt numaraları da bu aralığa düşebiliyor,
# bu yüzden TEK aday yoksa yıl BOŞ bırakılıyor (aşağıya bakın).
_RE_YIL = re.compile(r"\b(1[89]\d{2}|20[0-4]\d)\b")


def _bibitem_metni(ham: str) -> str:
    """\\bibitem gövdesini okunur tek satıra indir."""
    s = _RE_NEWBLOCK.sub(" ", ham)
    for _ in range(3):          # iç içe \emph{\textbf{...}} için birkaç tur
        yeni = _RE_BICIM.sub(r"\1", s)
        if yeni == s:
            break
        s = yeni
    s = s.replace("~", " ").replace("``", '"').replace("''", '"')
    s = s.replace("{", "").replace("}", "")
    return " ".join(s.split()).strip(" ,.")


def _bibitem_yili(metin: str) -> str:
    """Metinde TEK bir yıl adayı varsa onu döndür, yoksa "".

    Tahmin YOK. Ölçüldü (222 gerçek girdi): %87'sinde tek aday var, %5'inde
    birden çok ve orada hangisinin yıl olduğu belli değil. Gerçek bir örnek:
    adaylar 2014, 2023, 2037 ve sonuncusu bir SAYFA numarası. Yanlış yıl
    göstermek, boş bırakmaktan kötü: sütuna göre sıralama da bozulur.
    """
    adaylar = set(_RE_YIL.findall(metin))
    return adaylar.pop() if len(adaylar) == 1 else ""


def parse_bibitems(content: str, base_path: str) -> list[tuple[str, str, int, str]]:
    """Elle yazılmış kaynakça girdileri: (anahtar, dosya, satır, metin).

    Belgede ve \\input zincirinde geçen `\\bibitem`ler. .bib'in aksine her
    girdi FARKLI bir dosyada olabiliyor, o yüzden yol satır başına dönüyor.

    Yorumlar soyulmuyor: satır numarası GERÇEK dosyadaki satır olmalı ki
    tıklama doğru yere gitsin. (`strip_comments` satırları koruyor ama burada
    ham metinle çalışmak daha az varsayım demek.)
    """
    kaynaklar: list[tuple[str, str]] = []
    if base_path:
        kaynaklar.append((base_path, content))
    bdir = _base_dir(base_path)
    for yol in _flatten_input_paths(content, bdir):
        try:
            with open(yol, 'r', encoding='utf-8', errors='replace') as f:
                kaynaklar.append((yol, f.read()))
        except OSError:
            continue

    cikti: list[tuple[str, str, int, str]] = []
    gorulen: set[str] = set()
    for yol, metin in kaynaklar:
        # YORUMLAR SOYULUYOR. Eskiden ham metinle çalışılıyordu ve gerekçesi
        # "satır numarası GERÇEK dosyadaki satır olmalı" idi; `strip_comments`
        # satırları KORUDUĞU için o kaygı yersiz (aynı dosyadaki
        # `_bibitem_line_in` ve `_extract_labels` zaten öyle yapıyor).
        #
        # Bedeli ölçüldü (2026-09-12, 39 gerçek şablon): yoruma alınmış üç
        # `\bibitem` (template33-tez/17kaynaklar.tex) GERÇEK girdi sayılıyordu.
        # İki yüzey ayrışıyordu: Kaynakça sekmesi onları listeliyor ve
        # `\cite{` tamamlaması öneriyor, ama Alt+tık ile "tanıma git"
        # hiçbir yere gitmiyordu (`find_bibitem_location` yorumları zaten
        # soyuyor). 216 girdinin 213'ü iki tarafta da aynıydı, ayrışan
        # yalnız bu üçü.
        #
        # SÖZEL bloklar BİLEREK soyulmuyor: karşı taraf (`_bibitem_line_in`)
        # da soymuyor ve ikisinin AYNI kuralı görmesi bu düzeltmenin konusu.
        # Satır sayımı SOYULMUŞ metinde yapılmalı: ofsetler oradan geliyor.
        # Ham metinde saymak satırı kaydırıyor (kapı yakaladı: yoruma alınmış
        # bir girdiden sonraki gerçek girdi 3 yerine 2 çıkıyordu).
        temiz = strip_comments(metin)
        for m in _RE_BIBITEM_GOVDE.finditer(temiz):
            anahtar = m.group(1).strip()
            if not anahtar or anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            cikti.append((anahtar, yol, temiz.count("\n", 0, m.start()) + 1,
                          _bibitem_metni(m.group(2))))
    return cikti


def bib_declaration(content: str, base_path: str) -> str:
    """Bildirimde YAZAN .bib adı, dosya var olmasa da. Yoksa "".

    `find_bib_path` boş döndüğünde iki ayrı durum var ve ayırt edilmeleri
    gerekiyor: bildirim hiç yok, ya da bildirim var ama gösterdiği dosya
    bulunamıyor. İkisine aynı mesajı vermek kullanıcıyı zaten belgede duran
    bir komutu aramaya gönderiyordu.
    """
    for metin in [strip_comments(content)] + [t for _p, t in _chain_texts(content, base_path)]:
        for pat in (_RE_ADDBIB, _RE_BIBLIO):
            m = pat.search(metin)
            if m:
                return m.group(1).strip()
    return ""


def has_manual_bibliography(content: str, base_path: str) -> bool:
    """Belge kaynakçayı `\\begin{thebibliography}` ile ELLE mi yazıyor.

    39 şablonun 13'ü böyle (213 kaynak). Onlara "kaynakçan yok" demek
    yanlış: kaynakça var, yalnız .bib dosyasında değil .tex içinde.
    """
    for metin in [strip_comments(content)] + [t for _p, t in _chain_texts(content, base_path)]:
        if "\\begin{thebibliography}" in metin or _RE_BIBITEM.search(metin):
            return True
    return False


def _sinif_dosyalarinda_ara(bdir: str, ayikla) -> list:
    """Belgenin yanındaki `.cls`/`.sty` içinde bir bildirim ara.

    ``ayikla(metin, bdir)`` bildirimi çıkaran işlev; boş liste "bulunamadı"
    demek. Genel yazıldı çünkü aynı üç düzeyli arama (belge, `\\input`
    zinciri, sınıf dosyası) iki ayrı bildirim için gerekiyor: `.bib` yolu ve
    `\\graphicspath`. İkincisi bu aramayı YAPMIYORDU ve dışa aktarmada
    ölçüldü (2026-09-10, template28-book1): `\\graphicspath{{Images/}}`
    bildirimi `LegrandOrangeBook.cls` içinde, üç görselin bağı kırık
    çıkıyordu.

    biblatex şablonlarının bir kısmı `\\addbibresource`i SINIF dosyasına
    koyuyor ve `.tex` zincirinde hiç bildirim olmuyor. ÖLÇÜLDÜ (2026-09-09,
    template4): `rho.bib` klasörde duruyor, bildirim `rho.cls` içinde ve
    denetim belgedeki üç atıfı da "tanımsız" sayıyordu.

    Belgenin dizini VE bir alt düzeyi taranıyor: template4 sınıf dosyasını
    `rho-class/` alt klasörüne koyuyor, yani "yalnız kendi dizini" yetmiyor
    (ölçüldü). Daha derine inilmiyor ve sistemdeki TeX kurulumu hiç
    taranmıyor: oradaki sınıf dosyaları projenin .bib'ini zaten bildirmez.

    Bulunan yol BELGENİN dizinine göre çözülüyor, sınıf dosyasının dizinine
    göre değil: LaTeX de `\\addbibresource`i ana belgeye göre çözüyor.
    """
    from core.project_search import SKIP_DIRS

    dizinler = [bdir]
    try:
        for ad in sorted(os.listdir(bdir)):
            alt = os.path.join(bdir, ad)
            if (os.path.isdir(alt) and not ad.startswith(".")
                    and ad not in SKIP_DIRS):
                dizinler.append(alt)
    except OSError:
        return []
    for dizin in dizinler:
        try:
            adlar = sorted(os.listdir(dizin))
        except OSError:
            continue
        for ad in adlar:
            if not ad.lower().endswith((".cls", ".sty")):
                continue
            try:
                with open(os.path.join(dizin, ad), encoding="utf-8",
                          errors="replace") as f:
                    metin = f.read()
            except OSError:
                continue
            bulunan = ayikla(strip_comments(metin), bdir)
            if bulunan:
                return bulunan
    return []


def _zincir_ve_sinifta_ara(content: str, base_path: str, ayikla) -> list:
    """Bildirimi `\\input` zincirinde, sonra sınıf/stil dosyasında ara."""
    bdir = _base_dir(base_path)
    for _p, metin in _chain_texts(content, base_path):
        bulunan = ayikla(metin, bdir)
        if bulunan:
            return bulunan
    return _sinif_dosyalarinda_ara(bdir, ayikla)


def bildirimleri_ara(content: str, base_path: str, ayikla) -> list:
    """Bir LaTeX bildirimini ÜÇ DÜZEYDE ara: belge, zincir, sınıf dosyası.

    ``ayikla(metin, bdir)`` bildirimi çıkaran işlev; ilk boş olmayan sonuç
    kazanıyor. Arama STRATEJİSİ burada tek kaynak, ÇIKARMA kuralı çağıranda:
    `.bib` yolunu `find_bib_paths`, `\\graphicspath` dizinlerini
    `core.exporter` çıkarıyor.

    Strateji neden üç düzeyli: bildirim ana dosyada olmayabiliyor (çok
    dosyalı tez) ve hiç `.tex`te olmayabiliyor (şablon onu sınıf dosyasına
    koyuyor). İki bildirim için de ölçüldü; ayrıntı `find_bib_paths` ve
    `_sinif_dosyalarinda_ara` notlarında.

    Önbellek YOK: `find_bib_paths` kendi TTL'sini tutuyor çünkü tamamlama
    yolunda her tuş vuruşunda çağrılıyor. Buradan geçen öteki çağrı (dışa
    aktarma) kullanıcı eylemi başına bir kez koşuyor.
    """
    bdir = _base_dir(base_path)
    dogrudan = ayikla(strip_comments(content), bdir)
    if dogrudan:
        return dogrudan
    return _zincir_ve_sinifta_ara(content, base_path, ayikla)


def find_bib_paths(content: str, base_path: str) -> list[str]:
    """\\addbibresource{X.bib} / \\bibliography{X} ile verilen BÜTÜN .bib yolları.

    ÖNCE açık belgede, bulunamazsa \\input/\\include ZİNCİRİNDE aranıyor.
    Zincir taraması 2026-09-02'de eklendi: çok dosyalı tezlerde bildirim
    ana dosyada değil bir bölüm dosyasında oluyor ve o zaman uygulama
    "kaynakça yok" sanıyordu. Üç yeri birden bozuyordu:

      - \\cite otomatik tamamlama hiçbir anahtar önermiyordu
      - referans denetimi HER \\cite'ı "tanımsız" sayıyordu (template33-tez
        için 7 sahte uyarı, ölçüldü)
      - Kaynakça sekmesi boş kalıyordu

    22 şablonun 19'unda bildirim ana dosyada; zincir gerektiren 1 tanesi
    template33-tez (`0main.tex` -> `\\include{17kaynaklar}` -> orada).

    BU DEPODA .bib'i BULAN TEK YER. `core/exporter.py`nin kendi kopyası
    vardı ve iki uygulama birbirinin düzeltmesini taşımıyordu; ÖLÇÜLDÜ
    (2026-09-09, 39 gerçek şablon): iki tez şablonunda (template33-tez
    zincirde, template4 sınıf dosyasında) dışa aktarma kaynakçayı HİÇ
    bulamıyordu, yani DOCX/HTML çıktısı kaynakçasız çıkıyordu. Ters yönde
    de eksik vardı: virgüllü listeyi yalnız dışa aktarma biliyordu.
    """
    bdir = _base_dir(base_path)
    dogrudan = _bib_paths_in(strip_comments(content), bdir)
    if dogrudan:
        return dogrudan

    onbellek = _bib_chain_cache.get(base_path)
    if onbellek and (time.time() - onbellek[0]) < _BIB_CHAIN_TTL:
        return list(onbellek[1])

    sonuc = _zincir_ve_sinifta_ara(content, base_path, _bib_paths_in)
    if len(_bib_chain_cache) > 8:
        _bib_chain_cache.clear()
    _bib_chain_cache[base_path] = (time.time(), sonuc)
    return list(sonuc)


def find_bib_path(content: str, base_path: str) -> str:
    """İLK .bib yolu ("" yoksa). Birden çok dosya için `find_bib_paths`.

    Tek hedef isteyen çağıranlar için: Kaynakça sekmesi bir dosya
    gösteriyor, DOI ekleme bir dosyaya yazıyor, F2 bir dosyada yeniden
    adlandırıyor. Bunlar "hangi dosya" kararı, bilgi kopyası değil.
    """
    yollar = find_bib_paths(content, base_path)
    return yollar[0] if yollar else ""


# --- \input / \include tamamlama: projedeki .tex dosyaları ---

def collect_input_paths(base_path: str) -> list[str]:
    r"""\input{ / \include{ tamamlaması için projedeki .tex dosyaları.

    Ana dosyanın dizinini ve alt dizinlerini tarar; kök dizine göre .tex
    uzantısı soyulmuş göreli yollar döndürür (\include uzantı kabul etmez,
    \input uzantısızı da bulur; ikisi için de uzantısız öneri derlenir).
    Gizli dizinlere inilmez; ana dosyanın kendisi listede olmaz (kendini
    \input etmek döngü olur). Yol ayracı her platformda LaTeX'in beklediği
    '/'tir.
    """
    bdir = _base_dir(base_path)
    base_name = os.path.basename(os.path.abspath(base_path))
    rels: list[str] = []
    for root, dirs, files in os.walk(bdir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fn in files:
            # KÜÇÜK HARFE ÇEVİRİP bak: `.TEX` uzantılı kök dosyalar sahada
            # var (template34-tez: `iufenbil_tez_sablonu.TEX`) ve harf duyarlı
            # süzgeç onları hiç önermiyordu. Aynı dosyanın
            # `collect_image_paths`i zaten `.lower()` kullanıyor; tutarsızlık
            # dosyanın içindeydi. Aynı sınıf `63173f9`'da file_tree ve
            # file_ops için düzeltilmişti, o turun denetim listesinde burası
            # yoktu.
            if not fn.lower().endswith('.tex'):
                continue
            rel = os.path.relpath(os.path.join(root, fn), bdir)
            if rel == base_name:
                continue
            rels.append(rel[:-4].replace(os.sep, '/'))
    return sorted(rels)


# Grafik uzantıları: derleyicinin/graphicx'in kabul ettiği yaygın biçimler.
# TEK KAYNAK: sürükle-bırak da (main_window._handle_dropped_urls) buradan
# okuyor. Yorum zaten "aynı küme" diyordu ama orada elle yazılmış ikinci
# bir kopya duruyordu; `_OPENABLE_EXT` bu dersi bir kez almıştı.
IMG_EXTS = (".png", ".jpg", ".jpeg", ".pdf", ".eps")


def collect_image_paths(base_path: str) -> list[str]:
    """\\includegraphics{ tamamlaması için projedeki resim dosyaları.

    Ana dosyanın dizinini ve alt dizinlerini tarar (media/ vb. dahil); kök
    dizine göre, uzantısı KORUNMUŞ göreli yollar döndürür — görsel ekleme
    (sürükle-bırak/panodan yapıştır) da aynı kurala yazar. Ana dosyanın kendi
    derleme çıktısı (main.pdf) önerilmez; gizli dizinlere inilmez. Yol ayracı
    her platformda LaTeX'in beklediği '/'tir.
    """
    bdir = _base_dir(base_path)
    base_pdf = os.path.splitext(os.path.basename(os.path.abspath(base_path)))[0].lower() + ".pdf"
    rels: list[str] = []
    for root, dirs, files in os.walk(bdir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fn in files:
            if not fn.lower().endswith(IMG_EXTS) or fn.lower() == base_pdf:
                continue
            rel = os.path.relpath(os.path.join(root, fn), bdir)
            rels.append(rel.replace(os.sep, '/'))
    return sorted(rels)


def _bib_dosya_anahtarlari(bib_path: str) -> list[str]:
    """Tek bir .bib dosyasının anahtarları (mtime önbellekli)."""
    try:
        mtime = os.path.getmtime(bib_path)
    except OSError:
        return []
    cached = _cache_get(_bib_cache, bib_path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(bib_path, 'r', encoding='utf-8', errors='replace') as f:
            keys = sorted({m.group(1).strip() for m in RE_GIRDI_ANAHTARI.finditer(f.read())})
    except OSError:
        return []
    _cache_put(_bib_cache, bib_path, (mtime, keys))
    return keys


def collect_cite_keys(content: str, base_path: str) -> list[str]:
    """Referans verilen BÜTÜN .bib dosyalarındaki giriş anahtarları.

    .bib bulunamazsa boş liste. Birden çok dosya bildirilmişse hepsi
    okunuyor: yalnız ilkini okumak ikinci dosyanın her atfını "tanımsız"
    göstermek olurdu (denetim), tamamlamada da o anahtarlar hiç önerilmezdi.
    """
    keys: set[str] = set()
    for bib_path in find_bib_paths(content, base_path):
        keys.update(_bib_dosya_anahtarlari(bib_path))
    return sorted(keys)


def collect_citable_keys(content: str, base_path: str) -> list[str]:
    r"""`\cite` EDİLEBİLİR bütün anahtarlar: .bib girdileri + `\bibitem`ler.

    Elle yazılmış kaynakça (`thebibliography` + `\bibitem`) .bib kadar
    geçerli bir kaynakçadır ve uygulamanın geri kalanı bunu zaten biliyor:
    referans denetimi `undefined_cites`tan `\bibitem` anahtarlarını
    düşüyor, Alt+tık `\bibitem{k}` üzerinden ters yöne gidiyor. Yalnız
    tamamlama bilmiyordu; `.bib` yoksa `\cite{` yazınca HİÇBİR ŞEY
    önermiyordu.

    ÖLÇÜLDÜ (2026-09-12, 39 gerçek şablon): 13 şablonda elle yazılmış
    kaynakça var ve 12'sinde öneri listesi BOŞ geliyordu (6 ile 41 arası
    girdiye rağmen); .bib'i de olan template33-tez'de 118 anahtar
    öneriliyor ama 3 `\bibitem` görünmüyordu. Toplam 216 girdi.

    Aynı soru ("bu anahtar zaten kullanılıyor mu") DOI ile kaynak eklerken
    de soruluyor; orada da bu liste veriliyor, yoksa DOI'den gelen kayıt
    var olan bir `\bibitem` anahtarıyla çakışabilir.
    """
    keys = set(collect_cite_keys(content, base_path))
    # Canlı arabellek AYRICA taranıyor: `parse_bibitems` belgenin kendisini
    # ancak `base_path` VARSA okuyor, yani hiç kaydedilmemiş bir belgede
    # kendi `\bibitem`leri listeye girmezdi.
    keys.update(k for m in _RE_BIBITEM.finditer(content)
                if (k := m.group(1).strip()))
    keys.update(k for k, _yol, _satir, _metin
                in parse_bibitems(content, base_path))
    return sorted(keys)


# --- Alt+tık ile tanıma git: anahtarın (dosya, satır) konumu ---

def _label_line_in(text: str, key: str) -> int | None:
    """\\label{key}'in 1-bazlı satır numarası (yorumlar strip edilmiş metinde).

    strip_comments satır sayısını korur (\\n'leri silmez), bu yüzden strip
    edilmiş metindeki satır no'su orijinalle aynıdır. Yorum içindeki \\label
    doğru şekilde yok sayılır.
    """
    pat = re.compile(r'\\label\s*\{\s*' + re.escape(key) + r'\s*\}')
    for i, ln in enumerate(strip_comments(text).split('\n'), start=1):
        if pat.search(ln):
            return i
    return None


def find_label_location(content: str, base_path: str, key: str) -> tuple[str, int] | None:
    """\\label{key}'in (dosya yolu, 1-bazlı satır) konumu.

    Önce mevcut ``content``'te, sonra \\input zincirindeki çocuk dosyalarda arar.
    Bulunamazsa None. Alt+tık ile \\ref tanıma git için kullanılır.
    """
    loc = _label_line_in(content, key)
    if loc is not None:
        return (base_path, loc)
    bdir = _base_dir(base_path)
    for path in _flatten_input_paths(content, bdir):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                t = f.read()
        except OSError:
            continue
        loc = _label_line_in(t, key)
        if loc is not None:
            return (path, loc)
    return None


def find_cite_location(content: str, base_path: str, key: str) -> tuple[str, int] | None:
    """\\cite{key} için .bib girişinin (dosya yolu, 1-bazlı satır) konumu.

    .bib bulunamaz veya anahtar yoksa None. Alt+tık ile \\cite tanıma git için.
    Birden çok .bib bildirilmişse hepsine bakılıyor, yoksa ikinci dosyadaki
    girdiye tıklamak hiçbir şey yapmazdı.
    """
    pat = re.compile(r'@\w+\s*[{(]\s*' + re.escape(key) + r'\s*,')
    for bib_path in find_bib_paths(content, base_path):
        try:
            with open(bib_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError:
            continue
        for i, ln in enumerate(text.split('\n'), start=1):
            if pat.search(ln):
                return (bib_path, i)
    return None


# --- \bibitem (thebibliography, el ile kaynakça): \cite için .bib yoksa fallback ---

def _bibitem_line_in(text: str, key: str) -> int | None:
    """\\bibitem{key}'in 1-bazlı satır numarası (yorumlar strip edilmiş metinde).

    \\bibitem[label]{key} opsiyonel etiketini de destekler.
    """
    pat = re.compile(r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{\s*' + re.escape(key) + r'\s*\}')
    for i, ln in enumerate(strip_comments(text).split('\n'), start=1):
        if pat.search(ln):
            return i
    return None


def find_bibitem_location(content: str, base_path: str, key: str) -> tuple[str, int] | None:
    """\\bibitem{key}'in (thebibliography) (dosya yolu, satır) konumu.

    El ile kaynakça kullanan (.bib'siz) belgelerde \\cite tanıma git için
    fallback. Önce mevcut content'te, sonra \\input zincirinde arar.
    """
    loc = _bibitem_line_in(content, key)
    if loc is not None:
        return (base_path, loc)
    bdir = _base_dir(base_path)
    for path in _flatten_input_paths(content, bdir):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                t = f.read()
        except OSError:
            continue
        loc = _bibitem_line_in(t, key)
        if loc is not None:
            return (path, loc)
    return None


# .bib girdisinden makalede \cite edildiği yere (ters yön) git
# Atıf komutları. Aile GENİŞ tutulmak zorunda: tanınmayan bir komut İKİ kez
# zarar veriyor. (1) Denetim kaynakça girdisini "kullanılmıyor" sanıp sahte
# uyarı basıyor, (2) F2 o kullanımı GÜNCELLEMİYOR ve belgede sarkan atıf
# kalıyor (derleme "[?]" basar). ÖLÇÜLDÜ (2026-09-08): sekiz komut
# kaçıyordu ve aralarında biblatex'in ÖNERDİĞİ `\autocite` de vardı, yani
# biblatex kullanan bir belgede HER atıf iki kusuru birden yaşıyordu.
_CITE_KOMUTLARI = (
    # LaTeX çekirdeği
    "cite", "nocite",
    # natbib
    "citep", "Citep", "citet", "Citet", "citealp", "Citealp",
    "citealt", "Citealt", "citeauthor", "Citeauthor", "citeyear",
    "citeyearpar", "citenum",
    # biblatex
    "parencite", "Parencite", "textcite", "Textcite", "autocite", "Autocite",
    "footcite", "Footcite", "smartcite", "Smartcite", "supercite",
    "citetitle", "citedate", "citeurl", "fullcite",
)
# `\*?`: natbib yıldızlı biçimleri (`\citep*`) tüm yazar listesini basıyor.
_RE_CITEUSE = re.compile(
    r'\\(?:' + '|'.join(_CITE_KOMUTLARI) + r')\*?'
    r'\s*(?:\[[^\]]*\]\s*)*\{([^}]*)\}'
)


def find_cite_usage(bib_path: str, key: str) -> tuple[str, int] | None:
    """\\bib girdisi ``key``'in makalede \\cite edildiği (tex yolu, satır) konumu.

    .bib ile aynı dizin ağacındaki .tex dosyalarını tarar; ilk eşleşmeyi döndürür.
    Alt+tık ile .bib'ten makaledeki atıfa gitmek için (ters yön).
    """
    bdir = os.path.dirname(os.path.abspath(bib_path)) if bib_path else ""
    if not bdir:
        return None
    from core.project_search import SKIP_DIRS, duz_dosya_mi

    for root, dirs, files in os.walk(bdir):
        # Gizli ve derleme/paket dizinlerine inilmiyor. Bu yürüyüş her .tex'i
        # AÇIP okuyor; `node_modules` gibi bir ağaç altta kalırsa Alt+tık
        # denetimi onu baştan tarıyordu (ölçüldü 2026-09-02: node_modules
        # altında 1000 .tex varken 0.97 sn, temizken 0.00 sn). Aynı atlama
        # kuralı project_search ve dosya ağacında da geçerli.
        dirs[:] = sorted(x for x in dirs
                         if not x.startswith('.') and x not in SKIP_DIRS)
        for fn in sorted(files):
            # KÜÇÜK HARFE ÇEVİRİP bak, bkz. `collect_input_paths`. Burada
            # bedeli daha ağır: `.bib` editöründen F2 ile anahtar değiştirme
            # `find_cite_usage`in bulduğu dosyadan yola çıkıyor. Bulamayınca
            # `edit_ops._on_rename_cite` yalnız `.bib`i değiştiriyor,
            # makaledeki `\cite{eski}` olduğu gibi kalıyor ve kaynakçada
            # `[?]` basılıyor (ölçüldü).
            if not fn.lower().endswith('.tex'):
                continue
            path = os.path.join(root, fn)
            # FIFO'yu okumak sonsuza dek bloklardi (bkz.
            # project_search.duz_dosya_mi).
            if not duz_dosya_mi(path):
                continue
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    text = f.read()
            except OSError:
                continue
            for i, ln in enumerate(strip_comments(text).split('\n'), start=1):
                for m in _RE_CITEUSE.finditer(ln):
                    keys = [k.strip() for k in m.group(1).split(',')]
                    if key in keys:
                        return (path, i)
    return None


# --- Referans denetimi: tanımsız \ref / \cite, kullanılmayan .bib girdileri ---

# Etikete başvuran komutlar. Gerekçe _CITE_KOMUTLARI ile aynı; ÖLÇÜLDÜ
# (2026-09-08): on bir komut kaçıyordu, `\ref*` ve `\cref*` dahil.
#
# `\*?`: hyperref ve cleveref bağlantısız biçimi yıldızla yazıyor
# (`\ref*{...}`, `\autoref*{...}`, `\cref*{...}`).
_REF_ARALIK_KOMUTLARI = ("crefrange", "Crefrange", "vrefrange", "Vrefrange")
_REF_TEKIL_KOMUTLARI = (
    "ref", "eqref", "pageref", "autoref", "autopageref", "nameref",
    # cleveref
    "cref", "Cref", "cpageref", "Cpageref", "labelcref", "labelcpageref",
    # varioref
    "vref", "Vref", "vpageref", "Vpageref", "fullref",
)
# İki kollu: aralık komutları İKİ etiket alıyor (`\crefrange{ilk}{son}`) ve
# ikisi de anahtar. İkinci `{...}` yalnız o kolda aranıyor; tekil komutlarda
# da aransaydı `\cref{fig:a} {\itshape ve}` yazımında "ve" bir anahtar
# sanılıp "Tanımsız \ref" diye sahte bulgu üretirdi. Aralık kolu ÖNCE
# geliyor, yani `\crefrange` iki kez eşleşmiyor; iki kez eşleşseydi F2 aynı
# aralığı iki kez değiştirip metni bozardı.
_RE_REFUSE = re.compile(
    r'\\(?:' + '|'.join(_REF_ARALIK_KOMUTLARI) + r')\*?\s*'
    r'(?:\[[^\]]*\]\s*)?\{([^}]*)\}\s*\{([^}]*)\}'
    r'|\\(?:' + '|'.join(_REF_TEKIL_KOMUTLARI) + r')\*?\s*\{([^}]*)\}'
)


# Aileyi DIŞARIYA açan tek kaynak. editor.py'nin üç ayrı kopyası vardı ve
# aile 36a00c0'da genişletildiğinde hiçbiri güncellenmemişti. ÖLÇÜLDÜ
# (2026-09-09): `\autocite{`, `\ref*{`, `\cpageref{` gibi komutlarda
# tamamlama açılmıyor, Alt+tık tanıma gitmiyor, F2 anahtarı görmüyordu.
REF_KOMUTLARI = _REF_ARALIK_KOMUTLARI + _REF_TEKIL_KOMUTLARI
REF_ARALIK_KOMUTLARI = _REF_ARALIK_KOMUTLARI
CITE_KOMUTLARI = _CITE_KOMUTLARI


def komut_alternatifi(komutlar) -> str:
    """``\\(?:a|b|c)\\*?`` biçiminde regex parçası (yıldızlı biçim dahil)."""
    return r'\\(?:' + '|'.join(komutlar) + r')\*?'


def _kullanim_anahtarlari(m) -> list[str]:
    """Bir referans/atıf eşleşmesindeki BÜTÜN anahtarlar.

    İki şey birleşiyor: virgüllü liste (`\\cref{a,b}`) ve iki argümanlı
    aralık biçimi (`\\crefrange{ilk}{son}`). Eşleşmeyen kollar None geliyor.
    """
    out: list[str] = []
    for arg in m.groups():
        if arg:
            out.extend(k.strip() for k in arg.split(',')
                       if _anahtar_olabilir(k.strip()))
    return out


def _segment_araliklari(m, old: str) -> list[tuple[int, int]]:
    """Eşleşmedeki anahtar segmentlerinden ``old``'a EŞİT olanların aralıkları.

    Segment birebir karşılaştırılıyor: `old` öneki taşıyan `oldx` eşleşmez.
    """
    out: list[tuple[int, int]] = []
    for grup in range(1, m.re.groups + 1):
        arg = m.group(grup)
        if arg is None:
            continue
        arg_a = m.span(grup)[0]
        off = 0
        for part in arg.split(','):
            if part.strip() == old:
                s = arg_a + off + (len(part) - len(part.lstrip()))
                out.append((s, s + len(old)))
            off += len(part) + 1  # virgülü atla
    return out
_RE_BIBITEM = re.compile(r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}')
_RE_NOCITE_ALL = re.compile(r'\\nocite\s*\{\*\}')


@dataclass
class RefAudit:
    """Referans denetimi sonucu — tüm listeler sıralı ve tekil.

    undefined_refs:  kullanılan ama \\label'i (doküman + \\input zinciri) olmayan
                     \\ref ailesi anahtarları
    undefined_cites: kullanılan ama .bib girdisi de \\bibitem'i de olmayan
                     \\cite anahtarları
    unused_bib_keys: .bib'te olup hiç \\cite edilmemiş girdi anahtarları
                     (\\nocite{*} varsa boş — her şey kullanılmış sayılır)
    unused_labels:   tanımlı olup hiç \\ref ailesiyle kullanılmayan \\label
                     anahtarları (bilgi amaçlı; "ilerde lazım" label'ları da
                     yakalar, bu yüzden hata değil öneri olarak sunulur)
    """
    undefined_refs: list[str] = field(default_factory=list)
    undefined_cites: list[str] = field(default_factory=list)
    unused_bib_keys: list[str] = field(default_factory=list)
    unused_labels: list[str] = field(default_factory=list)


def _chain_texts(content: str, base_path: str) -> list[tuple[str, str]]:
    """\\input zincirindeki çocuk dosyaların (yol, yorumları soyulmuş metin) listesi."""
    bdir = _base_dir(base_path)
    out: list[tuple[str, str]] = []
    for path in _flatten_input_paths(content, bdir):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                out.append((path, strip_comments(f.read())))
        except OSError:
            continue
    return out


def _audit_texts(content: str, base_path: str) -> list[str]:
    """Denetim metinleri: mevcut içerik + \\input zinciri.

    Yorumlar VE sözel içerik soyulmuş: kod örneğindeki `\\cite{key}` gerçek
    atıf değil (bkz. latex_utils.sozel_soy'daki ölçüm).
    """
    return [sozel_soy(strip_comments(content))] + [
        sozel_soy(t) for _p, t in _chain_texts(content, base_path)]


def audit_references(content: str, base_path: str) -> RefAudit:
    """Dokümanı (ve \\input zincirini) referans açısından denetle.

    Derlemeden bağımsız hızlı lokal analiz: kırık çapraz referanslar ve
    kullanılmayan kaynakça girdileri. ``content`` canlı editör içeriğidir;
    zincirdeki çocuk dosyalar diskten okunur.
    """
    texts = _audit_texts(content, base_path)
    used_refs: set[str] = set()
    used_cites: set[str] = set()
    nocite_all = False
    for t in texts:
        for m in _RE_REFUSE.finditer(t):
            used_refs.update(_kullanim_anahtarlari(m))
        for m in _RE_CITEUSE.finditer(t):
            # '*' bir anahtar DEĞİL: \nocite{*} "hepsini kaynakçaya al" demek.
            # _RE_CITEUSE \nocite'ı da kapsadığı için '*' used_cites'a giriyor,
            # hiçbir .bib girdisiyle eşleşmiyor ve "Tanımsız \cite: *" diye
            # kalıcı sahte uyarı üretiyordu (nocite_all bayrağı yalnız
            # unused_bib_keys'i etkiliyor, bu kolu değil).
            used_cites.update(k for k in _kullanim_anahtarlari(m) if k != '*')
        if _RE_NOCITE_ALL.search(t):
            nocite_all = True

    defined_labels = set(collect_labels(content, base_path))
    # Boş anahtar süzülüyor: `\bibitem{ }` "" üretip her atfı "tanımlı"
    # göstermezdi ama boş anahtar kümeye girip karşılaştırmaları kirletirdi
    # (etiket kolundaki aynı ders için `_extract_labels`e bakın).
    bibitem_keys = {
        k for t in texts for m in _RE_BIBITEM.finditer(t)
        if (k := m.group(1).strip())
    }
    bib_keys = set(collect_cite_keys(content, base_path))

    return RefAudit(
        undefined_refs=sorted(used_refs - defined_labels),
        undefined_cites=sorted(used_cites - bib_keys - bibitem_keys),
        unused_bib_keys=[] if nocite_all else sorted(bib_keys - used_cites),
        unused_labels=sorted(defined_labels - used_refs),
    )


# --- Toplu konum çıkarımı: denetim yüzlerce anahtar için konum istiyor ---
#
# Aşağıdaki üç fonksiyon, tekil karşılıklarının (find_label_location,
# find_cite_location, find_key_usage) toplu hâlidir. Tekil olanlar TEK anahtar
# için doğru ve ucuzdur (Alt+tık ile tanıma git) ama her çağrıda \input
# zincirini / .bib'i diskten BAŞTAN okur. Referans denetimi bunları bulgu
# başına çağırınca maliyet kareleniyordu — 30 bölümlü, 200 girdilik .bib'li bir
# tezde ölçüldü:
#
#     audit_references            :   12.1 ms
#     find_label_location  x300   : 1677.1 ms   (5.59 ms/çağrı, hepsi disk)
#     TOPLAM (UI thread'i bloke)  : 1739.9 ms
#
# "Derleme Sonrası Referans Denetimi" açıkken bu her derlemeden sonra
# yaşanıyordu. Toplu sürümler zinciri bir kez okuyup sözlük kurar; N arama N
# sözlük erişimine iner. İlk kayıt kazanır — tekil sürümlerin "ilk eşleşmeyi
# döndür" davranışıyla aynı sonuç.

def label_locations(content: str, base_path: str) -> dict[str, tuple[str, int]]:
    """Tüm \\label anahtarları → (dosya yolu, 1-bazlı satır). Zincir tek okuma."""
    out: dict[str, tuple[str, int]] = {}
    entries = [(base_path, strip_comments(content))] + _chain_texts(content, base_path)
    for path, text in entries:
        for i, ln in enumerate(text.split('\n'), start=1):
            for m in _RE_LABEL.finditer(ln):
                # Boş anahtar süzülüyor, `_extract_labels` ile aynı kural:
                # `\label{ }` deseni geçiyor ve strip sonrası "" oluyor.
                if (k := m.group(1).strip()):
                    out.setdefault(k, (path, i))
    return out


def bib_key_locations(content: str, base_path: str) -> dict[str, tuple[str, int]]:
    """.bib girdi anahtarları → (bib yolu, 1-bazlı satır). Dosya başına tek okuma.

    Mükerrer anahtarda İLK bildirilen dosya kazanıyor, BibTeX de öyle yapıyor.
    """
    out: dict[str, tuple[str, int]] = {}
    for bib_path in find_bib_paths(content, base_path):
        try:
            with open(bib_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError:
            continue
        for i, ln in enumerate(text.split('\n'), start=1):
            for m in RE_GIRDI_ANAHTARI.finditer(ln):
                out.setdefault(m.group(1).strip(), (bib_path, i))
    return out


def key_usage_locations(content: str, base_path: str,
                        family: str) -> dict[str, tuple[str, int]]:
    """``family`` ('ref'|'cite') anahtarları → ilk kullanım (dosya, satır)."""
    pat = _RE_REFUSE if family == "ref" else _RE_CITEUSE
    out: dict[str, tuple[str, int]] = {}
    entries = [(base_path, strip_comments(content))] + _chain_texts(content, base_path)
    for path, t in entries:
        for i, ln in enumerate(t.split('\n'), start=1):
            for m in pat.finditer(ln):
                for k in _kullanim_anahtarlari(m):
                    out.setdefault(k, (path, i))
    return out


def find_key_usage(content: str, base_path: str, key: str, family: str) -> tuple[str, int] | None:
    """``family`` ('ref' veya 'cite') komutlarında ``key``'in ilk kullanım konumu.

    Tanımsız \\ref/\\cite bulgusuna tıklayınca kullanıldığı yere atlamak için.
    Ana dosyanın canlı içeriği ve \\input zinciri taranır; yorumlar soyulur ama
    satır numaraları korunur (strip_comments satır sayısını bozmaz). Çok
    anahtarlı kullanımda (\\cref{a,b}) segment segment eşleşilir.
    Bulunamazsa None.
    """
    pat = _RE_REFUSE if family == "ref" else _RE_CITEUSE
    entries = [(base_path, strip_comments(content))] + _chain_texts(content, base_path)
    for path, t in entries:
        for i, ln in enumerate(t.split('\n'), start=1):
            for m in pat.finditer(ln):
                if key in _kullanim_anahtarlari(m):
                    return (path, i)
    return None


# --- \label yeniden adlandırma (F2): doküman + \input zinciri ---

def input_chain_paths(content: str, base_path: str) -> list[str]:
    """\\input zincirindeki çocuk dosya yolları (flat, ana dosya hariç)."""
    return _flatten_input_paths(content, _base_dir(base_path))


def _yeniden_adlandirma_taramasi(text: str) -> str:
    r"""Yeniden adlandırma aralıklarının arandığı metin: sözel içerik boşaltılmış.

    ``\begin{verbatim}`` / ``lstlisting`` bloğunun ve satır içi ``\verb``in
    içindeki ``\label{...}``, ``\ref{...}``, ``\cite{...}`` çalışan LaTeX
    değil, belgenin BASTIĞI kod örneğidir. F2 onları da değiştirince iki
    ayrı zarar veriyordu (ÖLÇÜLDÜ 2026-09-09, 39 gerçek şablonda 8 dosya):

      - Anahtar hem gerçek metinde hem örnekte geçiyorsa (16 anahtar)
        gerçeğini yeniden adlandırmak örneği de değiştiriyor: belgenin
        basılan metni sessizce başkalaşıyor.
      - Anahtar YALNIZ örnekte geçiyorsa (17 anahtar) F2 doğrudan örneği
        düzenliyor.

    ``sozel_soy`` uzunluğu koruduğu için burada bulunan aralıklar ÖZGÜN
    metinde de geçerli; hem GUI'nin seç-değiştir yolu hem diskteki dosyayı
    yeniden yazan yol aralıkları özgün metne uyguluyor.

    Yorumlara DOKUNULMUYOR, bilerek: ``% \ref{eski}`` kullanıcının kendi
    taslağı ve yeniden adlandırmayı izlemesi gerekiyor, yoksa yorum
    açıldığında sarkan bir referans çıkıyor. Aynı ayrımı denetim tarafı da
    yapıyor (bkz. ``_audit_texts``).
    """
    return sozel_soy(text)


def label_rename_spans(text: str, old: str) -> list[tuple[int, int]]:
    """``text`` içinde ``old``'a eşit \\label argümanı / \\ref segmentinin karakter
    aralıkları.

    Aralıklar tek satır içinde kalır (anahtarlar satır kırılmaz); GUI bu
    aralıkları seçip değiştirerek undo geçmişini korur. \\label{oldx},
    ``old='old'`` ile eşleşmez (segment birebir karşılaştırılır).
    """
    tarama = _yeniden_adlandirma_taramasi(text)
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r'\\label\s*\{([^}]*)\}', tarama):
        a, b = m.span(1)
        if tarama[a:b].strip() == old:
            spans.append((a, b))
    for m in _RE_REFUSE.finditer(tarama):
        spans.extend(_segment_araliklari(m, old))
    return spans


def rename_label_in_text(text: str, old: str, new: str) -> str:
    """``old`` anahtarının tüm \\label ve \\ref ailesi kullanımlarını ``new`` yap.

    Değişiklik yoksa aynı metni döndürür. Diskteki dosyalar için toplu metin
    dönüşümü; açık editör arabellekleri için GUI aralık bazlı değiştirme yapar
    (bkz. label_rename_spans).
    """
    out = text
    for s, e in sorted(label_rename_spans(text, old), reverse=True):
        out = out[:s] + new + out[e:]
    return out


# --- \cite anahtarı yeniden adlandırma (F2): kullanımlar + .bib girdisi ---

def cite_rename_spans(text: str, old: str) -> list[tuple[int, int]]:
    """``old`` cite anahtarının \\cite ailesi kullanımlarındaki karakter aralıkları.

    Çok anahtarlı kullanımda (\\cite{a, old, b}) yalnız eşleşen segment;
    'old' önekli anahtarlar ('oldx') eşleşmez. \nocite dahil tüm aile.
    """
    tarama = _yeniden_adlandirma_taramasi(text)
    spans: list[tuple[int, int]] = []
    for m in _RE_CITEUSE.finditer(tarama):
        spans.extend(_segment_araliklari(m, old))
    return spans


def bib_key_rename_spans(text: str, old: str) -> list[tuple[int, int]]:
    """.bib içeriğinde ``old`` anahtarlı @type{old, girdisinin anahtar aralığı."""
    tarama = _yeniden_adlandirma_taramasi(text)
    spans: list[tuple[int, int]] = []
    for m in RE_GIRDI_ANAHTARI.finditer(tarama):
        if m.group(1) == old:
            spans.append(m.span(1))
    return spans


def bibitem_rename_spans(text: str, old: str) -> list[tuple[int, int]]:
    """Metinde ``old`` anahtarlı \\bibitem[label]{old} girdisinin aralıkları.

    El ile kaynakça (thebibliography) kullanan belgelerde F2 cite rename
    için; segment birebir karşılaştırılır.
    """
    tarama = _yeniden_adlandirma_taramasi(text)
    spans: list[tuple[int, int]] = []
    for m in _RE_BIBITEM.finditer(tarama):
        if m.group(1).strip() == old:
            spans.append(m.span(1))
    return spans
