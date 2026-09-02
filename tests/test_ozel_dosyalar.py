"""Düz olmayan dosyalar (FIFO, aygıt) taramaları asmasın.

Yazan tarafı olmayan bir FIFO'yu okumaya kalkmak SONSUZA DEK blokluyor.
Proje ağacındaki tek bir `boru.tex` şunları kilitliyordu (ölçüldü 2026-09-02,
dış güvenlik raporu 3. bulgu; 30 sn zaman aşımıyla doğrulandı):

- Klasörde Ara: arama işçisi asılı kalıyor ve İPTAL DE İŞE YARAMIYOR, çünkü
  engel `f.read()` içinde oluşuyor, iptal bayrağı ise okuma bittikten sonra
  denetleniyor.
- minted taraması: derleme kararı orada asılıyor.
- latex_refs'in .tex yürüyüşü.

Linux ve macOS'a özgü: Windows'ta adlandırılmış borular dosya sisteminde
böyle görünmüyor, bu yüzden testler orada atlanıyor.
"""

import os
import threading
import time

import pytest

from core.latex_refs import find_cite_usage
from core.project_search import duz_dosya_mi, search_project
from core.shell_escape import minted_kullaniliyor

fifo = pytest.mark.skipif(
    not hasattr(os, "mkfifo"), reason="FIFO yok (Windows)")

# Her çağrı bu süreden kısa sürmeli; asılma saniyeler değil dakikalar sürüyor.
_SINIR = 10.0


def _sureli(fn, *a, **kw):
    """fn'i ayrı iş parçacığında koş; asılırsa testi bloklamadan bildir."""
    sonuc = {}

    def kos():
        try:
            sonuc["deger"] = fn(*a, **kw)
        except Exception as e:            # pragma: no cover
            sonuc["hata"] = e

    t = threading.Thread(target=kos, daemon=True)
    t0 = time.time()
    t.start()
    t.join(_SINIR)
    if t.is_alive():
        pytest.fail("%s %.0f sn içinde dönmedi (asıldı)"
                    % (getattr(fn, "__name__", fn), _SINIR))
    if "hata" in sonuc:
        raise sonuc["hata"]
    return sonuc["deger"], time.time() - t0


@fifo
def test_duz_dosya_mi_fifoyu_eliyor(tmp_path):
    duz = tmp_path / "a.tex"
    duz.write_text("x", encoding="utf-8")
    boru = tmp_path / "boru.tex"
    os.mkfifo(str(boru))

    assert duz_dosya_mi(str(duz))
    assert not duz_dosya_mi(str(boru))
    assert not duz_dosya_mi(str(tmp_path))            # dizin
    assert not duz_dosya_mi(str(tmp_path / "yok.tex"))


@fifo
def test_arama_fifoya_takilmiyor(tmp_path):
    (tmp_path / "normal.tex").write_text("aranan kelime\n", encoding="utf-8")
    os.mkfifo(str(tmp_path / "boru.tex"))

    (bulgular, kesildi), _sn = _sureli(search_project, str(tmp_path), "aranan")

    assert len(bulgular) == 1
    assert bulgular[0].line == 1
    assert not kesildi


@fifo
def test_minted_taramasi_fifoya_takilmiyor(tmp_path):
    """Klasörde minted YOK: tarama FIFO'yu okumak ZORUNDA kalıyor.

    minted'li bir dosya da konsaydı `os.walk` ona FIFO'dan önce ulaşınca
    tarama erken dönerdi ve test şansa geçerdi (kasıtlı bozmada görüldü).
    """
    (tmp_path / "duz.tex").write_text("\\usepackage{listings}\n", encoding="utf-8")
    os.mkfifo(str(tmp_path / "boru.tex"))
    os.mkfifo(str(tmp_path / "boru2.sty"))

    var, _sn = _sureli(minted_kullaniliyor, str(tmp_path))

    assert var is False


@fifo
def test_minted_fifo_varken_gercegi_yine_buluyor(tmp_path):
    """FIFO'yu atlamak minted tespitini körleştirmemeli."""
    os.mkfifo(str(tmp_path / "boru.tex"))
    (tmp_path / "z_kod.sty").write_text("\\usepackage{minted}\n", encoding="utf-8")

    var, _sn = _sureli(minted_kullaniliyor, str(tmp_path))

    assert var is True


@fifo
def test_bib_ten_atifa_gidis_fifoya_takilmiyor(tmp_path):
    """`.bib` girdisinden makaledeki \\cite'a gidiş (Alt+tık, ters yön).

    Bu yol .bib ile aynı ağaçtaki tüm .tex dosyalarını AÇIYOR; aranan anahtar
    bulunamazsa hepsi okunuyor, yani FIFO'ya mutlaka takılıyor.
    """
    bib = tmp_path / "kaynaklar.bib"
    bib.write_text("@article{k, title={x}}\n", encoding="utf-8")
    (tmp_path / "a.tex").write_text("hic atif yok\n", encoding="utf-8")
    os.mkfifo(str(tmp_path / "boru.tex"))

    sonuc, _sn = _sureli(find_cite_usage, str(bib), "k")

    assert sonuc is None            # anahtar hiçbir yerde kullanılmıyor


@fifo
def test_bib_ten_atifa_gidis_gercegi_yine_buluyor(tmp_path):
    """FIFO'yu atlamak gerçek atıfı körleştirmemeli."""
    bib = tmp_path / "kaynaklar.bib"
    bib.write_text("@article{k, title={x}}\n", encoding="utf-8")
    os.mkfifo(str(tmp_path / "boru.tex"))
    (tmp_path / "z_makale.tex").write_text("bkz \\cite{k}\n", encoding="utf-8")

    sonuc, _sn = _sureli(find_cite_usage, str(bib), "k")

    assert sonuc is not None
    assert sonuc[0].endswith("z_makale.tex")
    assert sonuc[1] == 1
