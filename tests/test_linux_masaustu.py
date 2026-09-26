# -*- coding: utf-8 -*-
"""Linux masaüstü dosyası ve AppImage'ın AppStream bilgisi.

AppImageHub kataloğu (appimage.github.io/LaTeX_Editor) açıklamayı masaüstü
dosyasından aldı ve YALNIZ Türkçe yazdı: "LaTeX editörü ve derleyici".
İngilizce masaüstünde uygulama menüsü de aynı metni gösteriyordu. AppStream
bilgisi hiç yoktu; katalogda lisans boş (`license: null`), ekran görüntüsü
otomatik testte çekilen dar pencereydi (ölçüldü 2026-09-26, sitenin kendi
beslemesinden).

appimagetool metainfo'yu masaüstü dosyasının adıyla arıyor ve appstreamcli
kuruluysa `validate-tree` ile doğruluyor: uyarı bile paketlemeyi durduruyor
(bkz. build_appimage.sh). O yüzden ad, kimlik ve dosya ayrı ayrı sınanıyor.
"""

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LINUX = os.path.join(_KOK, "desktop", "linux")
_ID = "io.github.s_balli.latex_editor"
_MASAUSTU = os.path.join(_LINUX, _ID + ".desktop")
_METAINFO = os.path.join(_LINUX, _ID + ".appdata.xml")
_XML_DIL = "{http://www.w3.org/XML/1998/namespace}lang"


def _alanlar(metin: str) -> dict:
    """[Desktop Entry] satırları: anahtar -> değer (yorum ve boş satır yok)."""
    out = {}
    for satir in metin.splitlines():
        if "=" in satir and not satir.startswith(("#", "[")):
            k, v = satir.split("=", 1)
            out[k] = v
    return out


def _masaustu():
    with open(_MASAUSTU, encoding="utf-8") as f:
        return _alanlar(f.read())


def _metainfo():
    return ET.parse(_METAINFO).getroot()


def test_MASAUSTU_varsayilan_aciklama_INGILIZCE_turkcesi_ayri():
    """Kırılırsa: katalogda ve İngilizce menüde yine Türkçe açıklama çıkar."""
    a = _masaustu()
    assert a.get("Comment"), "varsayılan Comment yok"
    assert not re.search("[çğıöşüÇĞİÖŞÜ]", a["Comment"]), (
        "varsayılan açıklama Türkçe: %s" % a["Comment"])
    assert a.get("Comment[tr]"), "Türkçe karşılık (Comment[tr]) yok"


def test_MASAUSTU_iki_kopyasi_AYNI_alanlari_tasiyor(monkeypatch, tmp_path):
    """`main.py` AppImage'ı kullanıcının menüsüne KENDİ metniyle yazıyor;
    paketteki dosyayla ayrışırsa menü ile katalog farklı şey söyler. Exec
    bilerek farklı (AppImage'ın gerçek yolu)."""
    from tests.test_dosya_iliskilendirme import _desktop_uret

    calisma = _alanlar(_desktop_uret(monkeypatch, tmp_path,
                                     "/home/k/LaTeX Editor.AppImage"))
    paket = _masaustu()
    for k in (calisma, paket):
        k.pop("Exec", None)
    assert calisma == paket


def test_METAINFO_kimlik_ad_ve_yapi_betigi_TUTARLI():
    """Dosya adı, bileşen kimliği ve `<launchable>` aynı kimliği taşımalı;
    yapı betiği de onu kopyalamalı. Ölçüldü (appstreamcli 1.0.2): ad kimlikle
    eşleşmeyince ya da kimlik ters alan adı olmayınca `validate-tree` uyarı
    verip 3 ile çıkıyor, appimagetool da paketlemeyi durduruyor."""
    kok = _metainfo()
    assert kok.findtext("id") == _ID
    launch = kok.find("launchable[@type='desktop-id']")
    assert launch is not None and launch.text == _ID + ".desktop"
    assert os.path.isfile(_MASAUSTU)
    with open(os.path.join(_KOK, "desktop", "build_appimage.sh"),
              encoding="utf-8") as f:
        betik = f.read()
    assert 'MASAUSTU_ID="%s"' % _ID in betik
    assert "usr/share/metainfo/${MASAUSTU_ID}.appdata.xml" in betik


def test_METAINFO_lisans_adres_ve_ekran_goruntusu_DEPOYLA_ayni():
    """Katalog bu alanları olduğu gibi gösteriyor: yanlış lisans, ölü ana
    sayfa ya da olmayan görsel doğrudan kullanıcıya gider."""
    kok = _metainfo()
    with open(os.path.join(_KOK, "pyproject.toml"), encoding="utf-8") as f:
        lisans = re.search(r'^license\s*=\s*"([^"]+)"', f.read(), re.M).group(1)
    # pyproject'teki "GPL-3.0", SPDX'in eski yazımı; karşılığı -only.
    assert kok.findtext("project_license") == {"GPL-3.0": "GPL-3.0-only"}.get(
        lisans, lisans)

    with open(os.path.join(_KOK, "docs", "index.html"), encoding="utf-8") as f:
        kanonik = re.search(r'<link rel="canonical" href="([^"]+)"',
                            f.read()).group(1)
    assert kok.findtext("url[@type='homepage']") == kanonik

    gorseller = [i.text for i in kok.iter("image")]
    assert gorseller, "ekran görüntüsü yok"
    for adres in gorseller:
        assert adres.startswith(kanonik), adres
        yerel = os.path.join(_KOK, "docs", *adres[len(kanonik):].split("/"))
        assert os.path.isfile(yerel), "sitede olmayan görsel: %s" % adres


def test_METAINFO_iki_dilli_ozet():
    kok = _metainfo()
    ozetler = {s.get(_XML_DIL, "en"): s.text for s in kok.findall("summary")}
    assert set(ozetler) == {"en", "tr"}, ozetler
    assert not re.search("[çğıöşüÇĞİÖŞÜ]", ozetler["en"]), ozetler["en"]


def test_METAINFO_en_ustteki_surum_VERSION_ile_ayni():
    """Sürüm çıkarken `<releases>` en üstüne yeni sürüm eklenmeli; unutulursa
    paket eski sürüm numarasını söyler."""
    from core.version import VERSION

    surumler = _metainfo().findall("releases/release")
    assert surumler, "<releases> boş"
    assert surumler[0].get("version") == VERSION, (
        "metainfo'nun en üstteki sürümü %s, core/version.py %s"
        % (surumler[0].get("version"), VERSION))
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", surumler[0].get("date") or "")


@pytest.mark.skipif(shutil.which("appstreamcli") is None,
                    reason="appstreamcli yok (CI makinesinde de yok)")
def test_METAINFO_appstreamcli_validate_tree_TEMIZ(tmp_path):
    """appimagetool'un koşturduğu doğrulamanın aynısı, yapının kuracağı
    dizin düzeniyle. Kırılırsa: appstreamcli kurulu makinede AppImage
    paketlemesi durur. Ağ kapalı: görselin varlığını yukarıdaki kapı
    depodan sınıyor."""
    for alt in ("usr/share/applications", "usr/share/metainfo",
                "usr/share/icons/hicolor/256x256/apps"):
        (tmp_path / alt).mkdir(parents=True)
    shutil.copy(_MASAUSTU, tmp_path / (_ID + ".desktop"))
    shutil.copy(_MASAUSTU, tmp_path / "usr/share/applications" / (_ID + ".desktop"))
    shutil.copy(_METAINFO, tmp_path / "usr/share/metainfo" / (_ID + ".appdata.xml"))
    shutil.copy(os.path.join(_LINUX, "latex-editor.png"),
                tmp_path / "usr/share/icons/hicolor/256x256/apps/latex-editor.png")
    r = subprocess.run(["appstreamcli", "validate-tree", "--no-net", "--explain",
                        str(tmp_path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-500:]
