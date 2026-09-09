# -*- coding: utf-8 -*-
"""Çeviri kataloğu kapsamı: İngilizce arayüzde Türkçe metin kalmasın.

SINIF KAPISI, tek kusurun kapısı değil. Kaynakta `_("...")` ile işaretlenen
bir dizgi kataloğa girmediyse İngilizce arayüzde Türkçe görünüyor ve bunu
hiçbir test yakalamıyordu: kusur ancak biri arayüzü İngilizce'ye alıp o
ekranı açtığında görülüyor. Depo bu bedeli bir kez ödedi (bkz.
`synctex_ops` içindeki not: bağlamsız gönderilen "Satır" kelimesi
katalogda "Row" olmuş, oysa satır numarası kastediliyordu).

Kapı üç şeyi birden tutuyor:
  1. kaynaktaki her dizgi `.ts` içinde VAR
  2. hiçbiri `unfinished` ya da boş DEĞİL
  3. derlenmiş `.qm` katalogla AYNI (yani `lrelease` koşulmuş)

Düşerse yapılacak iş: `scripts/update_translations.sh` (WSL'de).
"""

import ast
import io
import os
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TS_EN = os.path.join(KOK, "desktop", "translations", "latexeditor_en.ts")
QM_EN = os.path.join(KOK, "desktop", "translations", "latexeditor_en.qm")

# `type="vanished"`: lupdate artık kaynakta olmayan dizgiyi böyle işaretliyor
# ve lrelease onu `.qm`e KOYMUYOR. Kalıntı olmaları normal, kapı onları
# beklemiyor.
_OLU_TIPLER = {"vanished", "obsolete"}


def _kaynak_dosyalari() -> list[str]:
    # `encoding` ŞART: Türkçe Windows'ta varsayılan cp1254 ve dosya adı
    # Türkçe harf taşıyabiliyor (deponun kendi taşınabilirlik kapısı bu
    # satırı yakaladı, bkz. test_platform_portability).
    r = subprocess.run(["git", "ls-files", "core/*.py", "desktop/**/*.py"],
                       cwd=KOK, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return [x for x in r.stdout.split("\n") if x.strip()]


def _kaynak_dizgileri() -> dict:
    """`_("...")` / `translate("Bağlam", "...")` ile işaretli dizgiler."""
    out = defaultdict(set)
    for rel in _kaynak_dosyalari():
        yol = os.path.join(KOK, rel)
        try:
            agac = ast.parse(io.open(yol, encoding="utf-8",
                                     errors="replace").read())
        except (OSError, SyntaxError):
            continue
        for d in ast.walk(agac):
            if not isinstance(d, ast.Call):
                continue
            ad = d.func.id if isinstance(d.func, ast.Name) else (
                d.func.attr if isinstance(d.func, ast.Attribute) else "")
            if ad not in ("_", "translate", "tr"):
                continue
            # DİKKAT: her modülün başındaki
            # `_ = lambda s: QCoreApplication.translate("MainWindow", s)`
            # satırında ikinci argüman DEĞİŞKEN. İlk ölçümde bağlam adları
            # ("MainWindow", "OutputPanel"...) çevrilecek dizgi sanılıp 26
            # sahte eksik üretilmişti; sabit olmayanı atlamak şart.
            if ad == "translate":
                if len(d.args) < 2 or not _sabit_dizgi(d.args[1]):
                    continue
                metin = d.args[1].value
            else:
                if not d.args or not _sabit_dizgi(d.args[0]):
                    continue
                metin = d.args[0].value
            if metin.strip():
                out[metin].add(rel)
    return out


def _sabit_dizgi(dugum) -> bool:
    return isinstance(dugum, ast.Constant) and isinstance(dugum.value, str)


def _katalog() -> tuple[dict, set]:
    """(kaynak metni -> (bağlam, çeviri, tip)), ölü olmayanların kümesi."""
    agac = ET.parse(TS_EN)
    kayit, canli = {}, set()
    for ctx in agac.getroot().iter("context"):
        ad_dugum = ctx.find("name")
        baglam = ad_dugum.text if ad_dugum is not None else ""
        for msg in ctx.iter("message"):
            src = msg.find("source")
            tr = msg.find("translation")
            if src is None or src.text is None:
                continue
            tip = (tr.get("type") or "") if tr is not None else ""
            metin = (tr.text or "") if tr is not None else ""
            kayit.setdefault(src.text, []).append((baglam, metin, tip))
            if tip not in _OLU_TIPLER:
                canli.add(src.text)
    return kayit, canli


def test_KAYNAKTAKI_her_dizgi_katalogda_VE_cevrili():
    """Kırılırsa İngilizce arayüzde o metin Türkçe kalır."""
    kaynak = _kaynak_dizgileri()
    kayit, _canli = _katalog()

    eksik = sorted(s for s in kaynak if s not in kayit)
    assert eksik == [], (
        "Katalogda olmayan %d dizgi (scripts/update_translations.sh):\n%s"
        % (len(eksik), "\n".join(repr(s)[:90] for s in eksik[:10])))

    bitmemis = []
    for s in kaynak:
        girdiler = kayit[s]
        # Aynı dizgi birden çok bağlamda olabiliyor; HEPSİ çevrili olmalı.
        for baglam, metin, tip in girdiler:
            if tip in _OLU_TIPLER:
                continue
            if tip == "unfinished" or not metin.strip():
                bitmemis.append((baglam, s))
    assert bitmemis == [], (
        "Çevirisi bitmemiş %d dizgi:\n%s"
        % (len(bitmemis),
           "\n".join("[%s] %s" % (b, repr(s)[:80]) for b, s in bitmemis[:10])))


def test_DERLENMIS_qm_katalogla_ayni():
    """`.ts` dolu olsa da uygulama `.qm` okuyor; bayat `.qm` sessizdir."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtCore import QCoreApplication, QTranslator
    from PyQt6.QtWidgets import QApplication

    assert os.path.isfile(QM_EN), "latexeditor_en.qm yok (lrelease koşulmadı)"
    app = QApplication.instance() or QApplication([])
    t = QTranslator()
    assert t.load(QM_EN), "qm yüklenemedi"
    app.installTranslator(t)
    try:
        kayit, _canli = _katalog()
        gelmeyen = []
        for src, girdiler in kayit.items():
            for baglam, metin, tip in girdiler:
                if tip in _OLU_TIPLER or not metin.strip():
                    continue
                if QCoreApplication.translate(baglam, src) != metin:
                    gelmeyen.append((baglam, src, metin))
        assert gelmeyen == [], (
            "%d dizgi .ts'de var ama .qm'den gelmiyor (lrelease):\n%s"
            % (len(gelmeyen),
               "\n".join("[%s] %s" % (b, repr(s)[:70])
                         for b, s, _m in gelmeyen[:10])))
    finally:
        app.removeTranslator(t)


def test_OLCUM_TUZAGI_baglam_adi_dizgi_sayilmiyor():
    """Kapının kendi kapısı: çıkarıcı bağlam adını çevrilecek dizgi sanmasın.

    İlk ölçümde tam bu yüzden 26 sahte eksik çıkmıştı, yani kapı yanlış
    yere bakarken de "kırmızı" verebiliyor.
    """
    kaynak = _kaynak_dizgileri()
    for ad in ("MainWindow", "OutputPanel", "EditorWidget", "PdfViewer"):
        assert ad not in kaynak, (
            "%r bağlam adı; çevrilecek dizgi olarak sayılmış" % ad)
