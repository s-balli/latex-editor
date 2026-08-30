"""pdfium eşzamanlılık kilidi — B5.

pdfium THREAD-SAFE DEĞİL ve bu uygulama ona üç thread'den dokunuyor
(UI + render işçisi + arama işçisi). CI'da gerçekten segfault görüldü
(run 33329685864, Python 3.10): render işçisi ``get_page`` içindeyken UI
``get_textpage`` içindeydi. Ayrı PdfDocument nesneleri kullanmak yetmiyor,
kütüphane küresel durum tutuyor.

Buradaki iki test farklı şeyleri koruyor:
- statik kapı: pdfium'a dokunan HER çağrı ``with pdfium_lock`` içinde mi
  (yeni bir çağrı eklenirken kilidi atlamak kolay)
- çalışma zamanı: üç thread aynı anda pdfium'a girince süreç ayakta kalıyor
  ve kilit gerçekten karşılıklı dışlama sağlıyor mu
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
}
_PDFIUM_FONKSIYONLARI = {
    "render_page_to_qimage", "render_page_to_pixmap",
    "get_link_at_point", "resolve_dest_scroll_y", "PdfDocument",
}
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
        elif isinstance(n, ast.Call):
            f = n.func
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

    assert denetlenen > 30, f"yalnız {denetlenen} çağrı görüldü — tarama bozuk olabilir"
    assert not korumasiz, (
        "pdfium çağrısı kilit dışında (segfault riski):\n" + "\n".join(korumasiz))


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
