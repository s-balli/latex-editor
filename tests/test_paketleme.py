"""Paketleme ve yayın hattının kapıları (BACKLOG "CI / paketleme").

İki sürükleme kaynağı vardı, ikisi de kapatıldı:

1. ÜÇ AYRI PAKETLEME TANIMI — `LaTeX Editor.spec`, `Exe Olustur.bat`,
   `Sikistirilmis Exe Olustur.bat`. Üçü farklı exe üretiyordu (birinde hiç
   `--exclude-module` yoktu) ve dahası: sıkıştırılmış betik ÇALIŞMIYORDU.
   Satır devamı (`^`) ile bağlanmış bir komutun ortasına konan `REM` satırları
   yorum değil ARGÜMAN olur ve komutu orada bitirir. Ölçüldü — PyInstaller'a
   ne bir `--exclude-module`, ne `--strip`, ne de `main.py` geçiyordu; hemen
   ardından `'--exclude-module' is not recognized` gelip "Hata olustu!"
   yazılıyordu. Bozulma `973f504` ile girmişti: hariç tutma listesini
   AÇIKLAYAN yorum, listeyi taşıyan komutu bozmuştu.

2. YAYIN NOTUNUN İKİ KOPYASI — release.yml'in build-windows ve build-linux
   job'larında ~100 satır birebir aynı echo bloğu. scripts/release_notes.sh'e
   indirildi; çıktının bayt bayt aynı kaldığı üç tag mesajı biçimiyle
   doğrulandı (tek satır, çok satır, HTML kaçışı gerektiren).

Bu dosya test_platform_portability.py'deki
`test_paketleme_haric_listeleri_ayrismiyor`ı da devraldı: o test "spec ile
.bat'ın hariç tutma listeleri aynı olsun" diyordu; artık liste TEK olduğu
için kural "listeyi .bat'ta yeniden tanımlama"ya dönüştü.
"""

import os
import re
import shutil
import subprocess

import pytest

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MASAUSTU = os.path.join(_KOK, "desktop")
_SPEC = os.path.join(_MASAUSTU, "LaTeX Editor.spec")
_NOTLAR = os.path.join(_KOK, "scripts", "release_notes.sh")
_RELEASE_YML = os.path.join(_KOK, ".github", "workflows", "release.yml")

_YAPI_BATLARI = ["Exe Olustur.bat", "Sikistirilmis Exe Olustur.bat"]


def _oku(yol):
    with open(yol, encoding="utf-8") as f:
        return f.read()


def _bat_yollari():
    return [os.path.join(_MASAUSTU, ad)
            for ad in sorted(os.listdir(_MASAUSTU)) if ad.endswith(".bat")]


# --------------------------------------------------------------------------
# 1a) Batch satır devamı — asıl hatanın sınıfı
# --------------------------------------------------------------------------

def _devam_icinde_yorum(metin: str):
    """`^` ile devam eden bir komutun içinde kalan REM/:: satırlarını bul.

    cmd.exe'de satır sonundaki `^` bir sonraki satırı AYNI komuta bağlar.
    Bağlanan satır `REM`/`::` ile başlıyorsa yorum sayılmaz; metni argüman
    olur ve satır `^` ile bitmediği için komut orada KESİLİR. Sonraki
    satırlar da ayrı komut olarak çalışmaya çalışılır.
    """
    bulgular = []
    devam = False
    for no, ham in enumerate(metin.splitlines(), 1):
        satir = ham.rstrip("\r\n")
        cikartilmis = satir.strip()
        if devam and re.match(r'(?i)^(rem\b|::)', cikartilmis):
            bulgular.append((no, cikartilmis))
        devam = satir.rstrip().endswith("^")
    return bulgular


class TestBatchSatirDevami:

    @pytest.mark.parametrize("yol", _bat_yollari(), ids=os.path.basename)
    def test_devam_eden_komutun_icinde_yorum_yok(self, yol):
        bulgular = _devam_icinde_yorum(_oku(yol))
        assert not bulgular, (
            f"{os.path.basename(yol)}: `^` ile devam eden komutun içinde "
            f"REM/:: satırı var — cmd bunu yorum SAYMAZ, argüman yapar ve "
            f"komutu orada keser: {bulgular}"
        )

    def test_ayiklayici_gercek_hatayi_yakaliyor(self):
        """Kapının kendisi: bozuk kalıp verilince ısırmalı, sağlamda susmalı."""
        bozuk = (
            'python -m PyInstaller --onefile ^\r\n'
            '    --add-data "gui;gui" ^\r\n'
            'REM Haric tutma listesi spec ile ayni olmali\r\n'
            '    --exclude-module tkinter ^\r\n'
            '    main.py\r\n'
        )
        assert _devam_icinde_yorum(bozuk), "ayıklayıcı bilinen bozuk kalıbı görmüyor"

        saglam = (
            'REM Haric tutma listesi spec ile ayni olmali\r\n'
            'python -m PyInstaller --onefile ^\r\n'
            '    --add-data "gui;gui" ^\r\n'
            '    main.py\r\n'
            ':: sonrasinda yorum serbest\r\n'
        )
        assert not _devam_icinde_yorum(saglam)

    @pytest.mark.parametrize("yol", _bat_yollari(), ids=os.path.basename)
    def test_satir_sonlari_crlf(self, yol):
        """.gitattributes `*.bat text eol=crlf` diyor; LF'li bat cmd'yi şaşırtır."""
        with open(yol, "rb") as f:
            ham = f.read()
        lf = ham.count(b"\n")
        crlf = ham.count(b"\r\n")
        assert lf == crlf, f"{os.path.basename(yol)}: {lf - crlf} satır CRLF değil"


# --------------------------------------------------------------------------
# 1b) Paketleme TEK KAYNAK: spec
# --------------------------------------------------------------------------

class TestTekPaketlemeTanimi:

    # Exe'nin İÇERİĞİNİ belirleyen argümanlar. Bunlar .bat'ta geçiyorsa
    # ikinci bir tanım doğmuş demektir.
    _ICERIK_ARG = ["--add-data", "--exclude-module", "--hidden-import",
                   "--icon", "--onefile", "--windowed", "--name"]

    @pytest.mark.parametrize("ad", _YAPI_BATLARI)
    def test_bat_spec_i_cagiriyor(self, ad):
        metin = _oku(os.path.join(_MASAUSTU, ad))
        assert '"LaTeX Editor.spec"' in metin, f"{ad} spec'i çağırmıyor"

    @pytest.mark.parametrize("ad", _YAPI_BATLARI)
    def test_bat_icerik_argumani_tekrarlamiyor(self, ad):
        metin = _oku(os.path.join(_MASAUSTU, ad))
        # Yorum satırları hariç: yorumda "--add-data YAZMA" demek serbest
        kod = "\n".join(s for s in metin.splitlines()
                        if not re.match(r'(?i)^\s*(rem\b|::)', s))
        gorulen = [a for a in self._ICERIK_ARG if a in kod]
        assert not gorulen, (
            f"{ad}: exe içeriğini belirleyen argüman(lar) .bat'ta: {gorulen}. "
            "Bunlar 'LaTeX Editor.spec'te yaşamalı — üç ayrı tanım yeniden doğdu."
        )

    def test_spec_haric_tutma_listesi_ve_email_kurali(self):
        metin = _oku(_SPEC)
        m = re.search(r"excludes=\[(.*?)\]", metin, re.S)
        assert m, "spec'te excludes listesi bulunamadı"
        liste = {p.strip().strip("'\"") for p in m.group(1).split(",") if p.strip()}
        assert {"tkinter", "unittest", "pip", "setuptools"} <= liste
        assert "email" not in liste, (
            "email hariç tutulamaz: urllib.request -> http.client -> email "
            "zinciri kopar, core.updater import edilemez ve kullanıcı "
            "güncellemelerden habersiz kalır (E6)"
        )

    @pytest.mark.parametrize("ortam,beklenen", [
        ({}, True),
        ({"CI": "true"}, False),
        ({"LE_HIZLI": "1"}, False),
        ({"CI": "true", "LE_HIZLI": "1"}, False),
    ])
    def test_spec_sikistirma_anahtari(self, ortam, beklenen):
        """strip/upx: CI'da kapalı (python312.dll bozuluyor), LE_HIZLI ile de."""
        metin = _oku(_SPEC)
        ust = metin.split("a = Analysis")[0]
        ad = {}
        eski = {k: os.environ.get(k) for k in ("CI", "LE_HIZLI")}
        try:
            for k in ("CI", "LE_HIZLI"):
                os.environ.pop(k, None)
            os.environ.update(ortam)
            exec(compile(ust, _SPEC, "exec"), ad)
        finally:
            for k, v in eski.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        assert ad["_sikistir"] is beklenen

    def test_duz_yapi_CI_ile_ayni_exe_yi_uretir(self):
        """`Exe Olustur.bat` LE_HIZLI=1 kurmalı — yayınlanan exe'nin aynısı."""
        metin = _oku(os.path.join(_MASAUSTU, "Exe Olustur.bat"))
        assert re.search(r'(?m)^\s*set LE_HIZLI=1\s*$', metin)

    def test_sikistirilmis_yapi_bayragi_disaridan_devralmiyor(self):
        """Aynı pencerede önce düz yapı koşulursa LE_HIZLI sızardı."""
        metin = _oku(os.path.join(_MASAUSTU, "Sikistirilmis Exe Olustur.bat"))
        assert re.search(r'(?m)^\s*setlocal\s*$', metin)
        assert re.search(r'(?m)^\s*set LE_HIZLI=\s*$', metin)
        assert "--upx-dir" in metin, "sıkıştırılmış yapı UPX'i göstermiyor"


# --------------------------------------------------------------------------
# 2) Yayın notu tek kaynakta
# --------------------------------------------------------------------------

class TestYayinNotu:

    def test_release_yml_govdeyi_gomulu_tutmuyor(self):
        metin = _oku(_RELEASE_YML)
        assert "} > release-notes.md" not in metin, (
            "yayın notu gövdesi release.yml'e geri gömülmüş"
        )
        cagrilar = re.findall(r'(?m)^\s*\|\s*bash scripts/release_notes\.sh\b', metin)
        assert len(cagrilar) == 2, (
            f"iki yapı job'ı da betiği çağırmalı, bulunan: {len(cagrilar)}"
        )
        # Kopya blok geri gelirse bu sayı fırlar
        assert metin.count("## Installation") == 0

    def test_betik_iki_dilde_ve_iki_artefaktla_uretiyor(self):
        if shutil.which("bash") is None:
            pytest.skip("bash yok")
        r = subprocess.run(["bash", _NOTLAR, "9.9.9"], input="Deneme notu",
                           capture_output=True, text=True, encoding="utf-8",
                           cwd=_KOK)
        assert r.returncode == 0, r.stderr
        c = r.stdout
        assert "## What's Changed" in c and "Deneme notu" in c
        assert "## Installation" in c and "## Kurulum" in c
        assert "LaTeX_Editor_v9.9.9_Windows.exe" in c
        assert "LaTeX_Editor_v9.9.9_Linux_x86_64.AppImage" in c
        assert "__V__" not in c, "sürüm yer tutucusu doldurulmamış"

    def test_betik_tag_mesajini_HTML_kacisiyla_gomiyor(self):
        """Tag mesajı Release gövdesine HTML olarak giriyor."""
        if shutil.which("bash") is None:
            pytest.skip("bash yok")
        r = subprocess.run(["bash", _NOTLAR, "1.0.0"],
                           input="<b>kalin</b> & 3>2", capture_output=True,
                           text=True, encoding="utf-8", cwd=_KOK)
        assert r.returncode == 0, r.stderr
        assert "&lt;b&gt;kalin&lt;/b&gt; &amp; 3&gt;2" in r.stdout
        assert "<b>kalin</b>" not in r.stdout

    def test_betik_cok_satirli_mesaji_koruyor(self):
        if shutil.which("bash") is None:
            pytest.skip("bash yok")
        r = subprocess.run(["bash", _NOTLAR, "1.0.0"],
                           input="ilk satir\n- madde\n- madde2",
                           capture_output=True, text=True, encoding="utf-8",
                           cwd=_KOK)
        assert r.returncode == 0, r.stderr
        assert "ilk satir\n- madde\n- madde2" in r.stdout.replace("\r\n", "\n")

    def test_surum_argumani_zorunlu(self):
        if shutil.which("bash") is None:
            pytest.skip("bash yok")
        r = subprocess.run(["bash", _NOTLAR], input="x", capture_output=True,
                           text=True, encoding="utf-8", cwd=_KOK)
        assert r.returncode != 0, "sürümsüz çağrı sessizce geçmemeli"
