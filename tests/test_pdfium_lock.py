"""pdfium eşzamanlılık kilidi — B5.

pdfium THREAD-SAFE DEĞİL ve bu uygulama ona üç thread'den dokunuyor
(UI + render işçisi + arama işçisi). CI'da gerçekten segfault görüldü
(run 33329685864, Python 3.10): render işçisi ``get_page`` içindeyken UI
``get_textpage`` içindeydi. Ayrı PdfDocument nesneleri kullanmak yetmiyor,
kütüphane küresel durum tutuyor.

Buradaki testler farklı şeyleri koruyor:
- statik kapı: pdfium'a dokunan HER çağrı ``with pdfium_lock`` içinde mi
  (yeni bir çağrı eklenirken kilidi atlamak kolay)
- kapının KENDİ kapsamı: tanıdığı çağrı biçimleri daralmasın
- çalışma zamanı: üç thread aynı anda pdfium'a girince süreç ayakta kalıyor
  ve kilit gerçekten karşılıklı dışlama sağlıyor mu

Kapsam notu (2026-08-31, G1/G2): kapı ilk hâlinde yalnız sabit bir metot ADI
listesine bakıyordu ve üç gerçek çağrıyı göremiyordu — ``len(self._doc)``
(FPDF_GetPageCount'a iner ama metot çağrısına benzemez) ile ham handle'ı
pdfium'a ileten iki yardımcı (``resolve_link_action``,
``get_dest_page_index``; ikisi de listeye alınmamıştı). Üçü de kilit dışında
kalmış, kapı yeşil kalmıştı. Bu yüzden artık üç kural birden var: ad listesi,
örtük çağrılar (``len``/``iter``/``list``) ve ``self._pdf.raw`` erişimi.
"""

import ast
import pathlib
import threading
import time

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_GUI = _REPO / "desktop" / "gui"


# --- Statik kapı: her pdfium dokunuşu kilit altında olmalı ---

_PDFIUM_METOTLARI = {
    "get_textpage", "get_charbox", "get_text_range", "get_index",
    "count_chars", "get_width", "get_height", "get_toc", "get_next",
    # RENDER YOLU ve yer imi okuma da pdfium'a giriyor, ikisi de listede
    # yoktu. ÖLÇÜLDÜ (2026-09-05): beş kilitsiz çağrı taşıyan sentetik bir
    # kaynakta kapı SIFIR bulgu verdi. Kör nokta en kötü yerdeydi, çünkü
    # CI'da gerçekleşen segfault'un bir tarafı tam da render işçisiydi.
    "render", "to_pil", "get_rotation", "get_title", "get_dest",
}
# pdfium'a giden fonksiyonların TAMAMI. gui/pdf_links.py'deki dördü de burada
# olmalı: ikisi eksikti ve _events.py'deki iki korumasız çağrı kapıdan geçti
# (2026-08-31, G1). Yeni bir yardımcı eklenirse adı buraya da eklenmeli.
_PDFIUM_FONKSIYONLARI = {
    "render_page_to_qimage", "render_page_to_pixmap", "PdfDocument",
    "get_link_at_point", "resolve_link_action",
    "resolve_dest_scroll_y", "get_dest_page_index",
}
# Belgeyi ARGÜMAN alan yerleşikler: len(doc) FPDF_GetPageCount'a iner, yani
# metot çağrısı gibi görünmediği hâlde pdfium'a girer. Aynı sınıf: iter/list.
_ORTUK_CAGRILAR = {"len", "iter", "list"}
_BELGE_ALANLARI = {"_pdf", "_doc"}


def _kilit_araliklari(tree):
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.With):
            for it in n.items:
                if "pdfium_lock" in ast.dump(it.context_expr):
                    out.append((n.lineno, n.end_lineno))
    return out


def _belge_mi(node):
    return isinstance(node, ast.Attribute) and node.attr in _BELGE_ALANLARI


def _pdfium_dokunuslari(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Subscript) and _belge_mi(n.value):
            yield n.lineno, f"self.{n.value.attr}[...]"
        # self._pdf.raw — ham C handle'ı dışarı veriliyor. Adı listede olmayan
        # bir yardımcıya geçirilse bile bu kural yakalar (ikinci savunma).
        elif isinstance(n, ast.Attribute) and n.attr == "raw" and _belge_mi(n.value):
            yield n.lineno, f"self.{n.value.attr}.raw"
        elif isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in _ORTUK_CAGRILAR:
                for a in n.args:
                    if _belge_mi(a):
                        yield n.lineno, f"{f.id}(self.{a.attr})"
            if isinstance(f, ast.Attribute):
                if f.attr in _PDFIUM_METOTLARI:
                    yield n.lineno, f".{f.attr}()"
                elif f.attr == "close" and _belge_mi(f.value):
                    yield n.lineno, f"self.{f.value.attr}.close()"
                elif f.attr in _PDFIUM_FONKSIYONLARI:
                    yield n.lineno, f".{f.attr}()"
            elif isinstance(f, ast.Name) and f.id in _PDFIUM_FONKSIYONLARI:
                yield n.lineno, f"{f.id}()"


def test_tum_pdfium_cagrilari_kilit_altinda():
    """pdfium'a dokunan her çağrı ``with pdfium_lock`` bloğunda olmalı.

    Kırılırsa: ilgili bloğu ``with pdfium_lock:`` içine alın. Kilit RLock,
    yani çağıran zaten tutuyorsa iç içe almak güvenli.
    """
    korumasiz = []
    denetlenen = 0
    for y in sorted(_GUI.rglob("*.py")):
        if y.name == "pdfium_lock.py":
            continue
        tree = ast.parse(y.read_text(encoding="utf-8"))
        araliklar = _kilit_araliklari(tree)
        for ln, ne in _pdfium_dokunuslari(tree):
            denetlenen += 1
            if not any(a <= ln <= b for a, b in araliklar):
                korumasiz.append(f"  {y.relative_to(_REPO).as_posix()}:{ln}  {ne}")

    assert denetlenen > 40, f"yalnız {denetlenen} çağrı görüldü — tarama bozuk olabilir"
    assert not korumasiz, (
        "pdfium çağrısı kilit dışında (segfault riski):\n" + "\n".join(korumasiz))


# Kaynak: yukarıdaki kapının GÖRMESİ gereken üç biçim (G1'de üçü de kaçmıştı)
# + görmemesi gereken iki kontrol satırı.
_ORNEK_KAYNAK = '''
class X:
    def f(self):
        n = len(self._doc)                        # örtük: FPDF_GetPageCount
        a = resolve_link_action(self._pdf.raw, k) # ad listesi + ham handle
        b = get_dest_page_index(self._pdf.raw, d) # ad listesi + ham handle
        r = page.render(scale=2.0)                # RENDER yolu
        p = r.to_pil()                            # RENDER yolu
        d2 = page.get_rotation()                  # dönme okuma
        t = bm.get_title()                        # yer imi okuma
        c = self._metin.count("x")                # KONTROL: pdfium değil
        e = len(self._page_labels)                # KONTROL: pdfium değil
        return n, a, b, r, p, d2, t, c, e
'''


def test_kapi_kacan_uc_bicimi_taniyor():
    """Kapının kapsamı daralmasın: üç biçim de tanınmaya devam etmeli.

    G1'de kapı yeşilken üç gerçek pdfium çağrısı kilit dışındaydı; kapı
    onları GÖREMİYORDU. Asıl kapı yalnız depodaki kodu tarar, yani biçim
    tanıma yeteneği sessizce daralırsa kimse fark etmez. Bu test o yeteneği
    doğrudan sınar.
    """
    bulunan = {ne for _ln, ne in _pdfium_dokunuslari(ast.parse(_ORNEK_KAYNAK))}
    for beklenen in ("len(self._doc)", "resolve_link_action()",
                     "get_dest_page_index()", "self._pdf.raw",
                     # Render yolu 2026-09-05'e kadar kapının kör noktasıydı.
                     ".render()", ".to_pil()", ".get_rotation()",
                     ".get_title()"):
        assert beklenen in bulunan, (
            f"kapı '{beklenen}' biçimini artık tanımıyor — kapsam daralmış. "
            f"Gördükleri: {sorted(bulunan)}")
    # Kontrol: pdfium'la ilgisi olmayan çağrılar işaretlenmemeli (kapı
    # her şeyi işaretleseydi yukarıdaki assert'ler bedava geçerdi).
    assert not any("_metin" in b or "_page_labels" in b for b in bulunan), (
        f"kapı pdfium dışı çağrıları da işaretliyor: {sorted(bulunan)}")


# --- Çalışma zamanı: üç thread aynı anda ---

def test_kilit_karsilikli_dislama_sagliyor():
    """İki thread aynı anda kilidin içinde bulunamamalı."""
    from gui.pdfium_lock import pdfium_lock

    icerdekiler = 0
    en_fazla = 0
    kilit = threading.Lock()
    dur = threading.Event()

    def isci():
        nonlocal icerdekiler, en_fazla
        while not dur.is_set():
            with pdfium_lock:
                with kilit:
                    icerdekiler += 1
                    en_fazla = max(en_fazla, icerdekiler)
                time.sleep(0.0005)
                with kilit:
                    icerdekiler -= 1

    thlar = [threading.Thread(target=isci, daemon=True) for _ in range(4)]
    for t in thlar:
        t.start()
    time.sleep(0.4)
    dur.set()
    for t in thlar:
        t.join(2)

    assert en_fazla == 1, f"aynı anda {en_fazla} thread kilidin içindeydi"


def test_rlock_ic_ice_alinabiliyor():
    """İç içe çağrılar (ör. _show_search_result -> _draw_search_highlight)."""
    from gui.pdfium_lock import pdfium_lock
    with pdfium_lock:
        with pdfium_lock:
            assert True


def test_uc_thread_ayni_anda_pdfium_kullanabiliyor(tmp_path):
    """UI + iki işçi aynı anda pdfium'a girince süreç ayakta kalmalı.

    Kilit olmadan bu desen CI'da segfault üretmişti. Segfault süreci
    öldürdüğü için "başarısız test" değil "çöken koşu" olarak görünür —
    bu testin geçmesi, sürecin sağ kalması demektir.
    """
    pypdfium2 = pytest.importorskip("pypdfium2")
    from gui.pdfium_lock import pdfium_lock

    # Basit tek sayfalık PDF üret (harici araç gerekmesin)
    pdf = pypdfium2.PdfDocument.new()
    pdf.new_page(200, 200)
    yol = tmp_path / "t.pdf"
    pdf.save(str(yol))
    pdf.close()
    veri = yol.read_bytes()

    hatalar = []
    dur = threading.Event()

    def dongu():
        try:
            with pdfium_lock:
                belge = pypdfium2.PdfDocument(veri)
            while not dur.is_set():
                with pdfium_lock:
                    sayfa = belge[0]
                    sayfa.get_width()
                    sayfa.get_height()
                    sayfa.get_textpage().count_chars()
            with pdfium_lock:
                belge.close()
        except Exception as e:      # pragma: no cover
            hatalar.append(e)

    thlar = [threading.Thread(target=dongu, daemon=True) for _ in range(3)]
    for t in thlar:
        t.start()
    time.sleep(0.5)
    dur.set()
    for t in thlar:
        t.join(5)
        assert not t.is_alive(), "thread bitmedi (kilitlenme?)"

    assert not hatalar, f"eşzamanlı pdfium kullanımında hata: {hatalar}"


# --- Render yolu: fonksiyon kilidi KENDİ alıyor mu ---
#
# `render_page_to_qimage` uzun süre kilidi çağıranlarına bırakıyordu ve
# yukarıdaki statik kapı `render`/`to_pil` adlarını tanımadığı için bunu
# GÖREMİYORDU (ölçüldü 2026-09-05: beş kilitsiz çağrı taşıyan sentetik
# kaynakta kapı sıfır bulgu verdi). CI'da gerçekleşen segfault'un bir tarafı
# tam da render işçisiydi, yani korumanın en çok gerektiği yol kapının kör
# noktasındaydı.
#
# Kapı artık o adları tanıyor; bu testler ayrıca fonksiyonun KENDİNİ
# savunduğunu sabitliyor, çünkü ikisi ayrı korumadır: kapı çağrının nerede
# yazıldığına bakar, buradaki test fonksiyonun tek başına çağrılabilir
# olduğunu sınar.

_RENDER_YOLU = _GUI / "pdf_render.py"


def _kendi_kilidini_aliyor(fn_adi, yol):
    """`yol` dosyasındaki `fn_adi` fonksiyonu gövdesinde pdfium_lock alıyor mu."""
    for n in ast.parse(yol.read_text(encoding="utf-8")).body:
        if isinstance(n, ast.FunctionDef) and n.name == fn_adi:
            return any(
                isinstance(x, ast.With)
                and any("pdfium_lock" in ast.dump(i.context_expr)
                        for i in x.items)
                for x in ast.walk(n))
    raise AssertionError(f"{fn_adi} bulunamadı: {yol}")


@pytest.mark.parametrize("fn", ["render_page_to_qimage", "render_page_to_pixmap"])
def test_render_fonksiyonlari_kendi_kilidini_aliyor(fn):
    """Tek başına çağrılabilir olmalı; RLock iç içe almayı bedava yapıyor."""
    assert _kendi_kilidini_aliyor(fn, _RENDER_YOLU), (
        f"{fn} pdfium'a kilitsiz giriyor; `with pdfium_lock:` içine alın")


def test_render_gercekten_kilit_altinda_calisiyor(tmp_path):
    """Çalışma zamanı: fonksiyon koşarken kilit GERÇEKTEN tutuluyor mu.

    Statik kapı `with pdfium_lock:` yazısını görür; bu test kilidin o an
    tutulduğunu ölçer. Kilit RLock olduğu için sahibi olan thread onu
    yeniden alabilir: başka bir thread'den `acquire(blocking=False)`
    denenirse BAŞARISIZ olmalı.
    """
    pypdfium2 = pytest.importorskip("pypdfium2")
    from gui.pdf_render import render_page_to_qimage
    from gui.pdfium_lock import pdfium_lock

    pdf = pypdfium2.PdfDocument.new()
    pdf.new_page(80, 80)
    sayfa = pdf[0]

    tutuluyordu = []

    def deneyen():
        # Başka thread: kilit içerideyken alınamamalı
        alindi = pdfium_lock.acquire(blocking=False)
        tutuluyordu.append(not alindi)
        if alindi:
            pdfium_lock.release()

    gercek_render = type(sayfa).render

    def izleyen(self, *a, **kw):
        t = threading.Thread(target=deneyen)
        t.start()
        t.join(2)
        return gercek_render(self, *a, **kw)

    type(sayfa).render = izleyen
    try:
        render_page_to_qimage(sayfa, 1.0)
    finally:
        type(sayfa).render = gercek_render
        pdf.close()

    assert tutuluyordu == [True], (
        "render sırasında pdfium_lock tutulmuyordu: %s" % tutuluyordu)


def test_kapi_render_yolunu_kilit_disinda_YAKALIYOR():
    """Kapının kendi işini yaptığının doğrudan kanıtı.

    Yukarıdaki `test_tum_pdfium_cagrilari_kilit_altinda` yalnız depoyu
    tarıyor; depo temizken o test, kapı hiçbir şey görmese de yeşil kalır.
    Burada kapıya KİLİTSİZ bir kaynak veriliyor ve işaretlemesi bekleniyor.
    """
    kaynak = '''
class X:
    def f(self, page):
        return page.render(scale=2.0).to_pil()
'''
    agac = ast.parse(kaynak)
    araliklar = _kilit_araliklari(agac)
    dokunuslar = list(_pdfium_dokunuslari(agac))
    assert dokunuslar, "kapı render yolunu hiç görmüyor"
    korumasiz = [ne for ln, ne in dokunuslar
                 if not any(a <= ln <= b for a, b in araliklar)]
    assert len(korumasiz) == 2, (
        "kilitsiz render/to_pil işaretlenmedi: %s" % dokunuslar)


def test_kilitli_kaynak_yanlislikla_isaretlenmiyor():
    """Karşı durum: aynı çağrılar kilit altındayken temiz geçmeli."""
    kaynak = '''
class X:
    def f(self, page):
        with pdfium_lock:
            return page.render(scale=2.0).to_pil()
'''
    agac = ast.parse(kaynak)
    araliklar = _kilit_araliklari(agac)
    korumasiz = [ne for ln, ne in _pdfium_dokunuslari(agac)
                 if not any(a <= ln <= b for a, b in araliklar)]
    assert not korumasiz, korumasiz
