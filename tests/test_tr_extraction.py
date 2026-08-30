"""Çeviri çıkarımı — scripts/extract_tr.py ve katalog eksiksizliği.

Regresyon: dönüşüm tek satırlık bir regex'ti, çok satırlı _() çağrılarını
görmüyordu. O dizgeler katalogdan type="vanished" olarak düşüyor, uygulama
İngilizceye alınsa bile ilgili dialoglar Türkçe kalıyordu. CI yalnız
"unfinished" saydığı için sessizce kaçıyordu — bu dosyadaki
test_tum_cevrilebilir_dizgeler_katalogda o boşluğu kapatır.
"""

import ast
import importlib.util
import pathlib
import re
import subprocess

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_TS_EN = _REPO / "desktop" / "translations" / "latexeditor_en.ts"


def _yukle():
    yol = _REPO / "scripts" / "extract_tr.py"
    spec = importlib.util.spec_from_file_location("extract_tr", yol)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


extract_tr = _yukle()


def _cikar(tmp_path, kaynak: str) -> str:
    src = tmp_path / "modul.py"
    src.write_text(kaynak, encoding="utf-8")
    dst = tmp_path / "cikti.py"
    rc = extract_tr.main(["extract_tr.py", str(src), str(dst)])
    assert rc == 0
    return dst.read_text(encoding="utf-8")


BASLIK = ('from PyQt6.QtCore import QCoreApplication\n'
          '_ = lambda s: QCoreApplication.translate("Ctx", s)\n')


# --- bağlam çıkarımı ---


def test_baglam_lambdadan_okunur(tmp_path):
    cikti = _cikar(tmp_path, BASLIK + '_("merhaba")\n')
    assert "QCoreApplication.translate('Ctx', 'merhaba')" in cikti


def test_baglam_yoksa_cikti_bos(tmp_path):
    """Çeviri kısayolu tanımlamayan dosyadan çıkarılacak bir şey yok."""
    assert _cikar(tmp_path, 'x = 1\ndef f(): return 2\n') == ""


# --- asıl regresyon: çok satırlı çağrılar ---


def test_cok_satirli_cagri_cikarilir(tmp_path):
    kaynak = BASLIK + '''
msg = _(
    "{f} diskte değiştirildi.\\n\\n"
    "Kaydedilmemiş değişiklikleriniz var."
).format(f="a.tex")
'''
    cikti = _cikar(tmp_path, kaynak)
    assert "{f} diskte değiştirildi.\\n\\nKaydedilmemiş değişiklikleriniz var." in cikti


def test_ic_ice_parantezli_cok_satirli(tmp_path):
    kaynak = BASLIK + '''
dlg.setText(_(
    "bir "
    "iki"
).format(x=1))
'''
    assert "'bir iki'" in _cikar(tmp_path, kaynak)


def test_satir_numarasi_korunur(tmp_path):
    """<location line=...> kaynakla eşleşmeli; çevirmen bağlamı bulabilsin."""
    kaynak = BASLIK + "\n" * 8 + '_("onuncu satır")\n'
    cikti = _cikar(tmp_path, kaynak)
    satirlar = cikti.split("\n")
    (idx,) = [i for i, s in enumerate(satirlar) if "onuncu satır" in s]
    kaynak_satiri = kaynak.split("\n").index('_("onuncu satır")')
    assert idx == kaynak_satiri


def test_ayni_satirda_iki_cagri(tmp_path):
    cikti = _cikar(tmp_path, BASLIK + '999 if _("bir") else _("iki")\n')
    assert "'bir'" in cikti and "'iki'" in cikti


# --- regex sürümünün patladığı yerler ---


def test_fstring_icindeki_cagri(tmp_path):
    """Regex sürümü burada tırnak çakıştırıp 'Invalid syntax' veriyordu."""
    kaynak = BASLIK + "ad = 'x'\nmesaj = f\"{_('etiket')}: {ad}\"\n"
    assert "'etiket'" in _cikar(tmp_path, kaynak)


def test_tek_tirnakli_cagri(tmp_path):
    assert "'tek tırnak'" in _cikar(tmp_path, BASLIK + "_('tek tırnak')\n")


def test_icinde_tirnak_gecen_dizge(tmp_path):
    cikti = _cikar(tmp_path, BASLIK + '''_("o'nun \\"tırnak\\" hâli")\n''')
    assert "tırnak" in cikti
    ast.parse(cikti)  # üretilen dosya geçerli Python olmalı


def test_uretilen_dosya_hep_gecerli_python(tmp_path):
    kaynak = BASLIK + '''
a = _("satır\\nsonu")
b = _('ters\\\\bölü')
c = _("yüzde %s ve {süslü}")
'''
    ast.parse(_cikar(tmp_path, kaynak))


# --- çıkarılamayan çağrılar uyarı vermeli ---


def test_degisken_alan_cagri_uyarir(tmp_path, capsys):
    src = tmp_path / "m.py"
    src.write_text(BASLIK + "mesaj = 'x'\n_(mesaj)\n", encoding="utf-8")
    dst = tmp_path / "o.py"
    extract_tr.main(["extract_tr.py", str(src), str(dst)])
    assert "sabit dizge almıyor" in capsys.readouterr().err


def test_bozuk_dosya_hata_koduyla_doner(tmp_path, capsys):
    src = tmp_path / "bozuk.py"
    src.write_text("def (:\n", encoding="utf-8")
    rc = extract_tr.main(["extract_tr.py", str(src), str(tmp_path / "o.py")])
    assert rc == 1
    assert "ayrıştırılamadı" in capsys.readouterr().err


# --- katalog eksiksizliği (asıl kapı) ---


def _katalog_kaynaklari() -> set[str]:
    """.ts içindeki KULLANILABİLİR <source> metinleri (vanished/obsolete hariç)."""
    ts = _TS_EN.read_text(encoding="utf-8")
    canli = set()
    for blok in re.findall(r"<message>.*?</message>", ts, re.S):
        if 'type="vanished"' in blok or 'type="obsolete"' in blok:
            continue
        m = re.search(r"<source>(.*?)</source>", blok, re.S)
        if m:
            canli.add(m.group(1).replace("&amp;", "&")
                      .replace("&lt;", "<").replace("&gt;", ">"))
    return canli


def _kaynak_dizgeleri() -> list[tuple[str, int, str]]:
    """Koddaki tüm _( "sabit" ) çağrıları: (dosya, satır, metin)."""
    ciktilar = subprocess.run(
        ["git", "ls-files", "desktop/gui", "desktop/main.py"],
        cwd=_REPO, capture_output=True, text=True, check=True, encoding="utf-8").stdout.split()
    bulunan = []
    for rel in ciktilar:
        if not rel.endswith(".py"):
            continue
        tree = ast.parse((_REPO / rel).read_text(encoding="utf-8"))
        for lineno, metin in extract_tr.topla(tree)[0]:
            bulunan.append((rel, lineno, metin))
    return bulunan


@pytest.mark.skipif(not _TS_EN.exists(), reason="çeviri kataloğu yok")
def test_tum_cevrilebilir_dizgeler_katalogda():
    """Koddaki her _() dizgesi İngilizce katalogda canlı bir girdi olmalı.

    Bu testin kırılması demek: o metin İngilizce arayüzde Türkçe görünüyor.
    Düzeltme — WSL/Linux'ta:
        PATH=/usr/lib/qt6/bin:$PATH bash scripts/update_translations.sh
    ardından latexeditor_en.ts içindeki yeni unfinished girdileri doldur.
    """
    canli = _katalog_kaynaklari()
    eksik = [(f, ln, m) for f, ln, m in _kaynak_dizgeleri() if m not in canli]
    assert not eksik, "katalogda karşılığı olmayan dizgeler:\n" + "\n".join(
        f"  {f}:{ln}  {m[:70]!r}" for f, ln, m in eksik)


@pytest.mark.skipif(not _TS_EN.exists(), reason="çeviri kataloğu yok")
def test_katalogda_bitmemis_ceviri_yok():
    """CI kapısının aynısı; yerelde de kırmızı yansın."""
    ts = _TS_EN.read_text(encoding="utf-8")
    assert 'type="unfinished"' not in ts, "latexeditor_en.ts içinde unfinished çeviri var"
