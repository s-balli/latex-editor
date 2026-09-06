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

import functools
import os
import re
import shutil
import subprocess
import sys
import tempfile

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


def _bash_adaylari():
    adaylar = []
    bulunan = shutil.which("bash")
    if bulunan:
        adaylar.append(bulunan)
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    adaylar += [os.path.join(pf, "Git", "bin", "bash.exe"),
                os.path.join(pf, "Git", "usr", "bin", "bash.exe")]
    return adaylar


def _bash_calisiyor_mu(aday: str) -> bool:
    """Aday bash, testlerin ondan İSTEDİĞİ şeyi yapabiliyor mu.

    Eskiden `-c "echo ok"` sınanıyordu ve bu YETMİYOR: WSL'in bash'i
    (C:\\WINDOWS\\system32\\bash.exe) dağıtım kuruluyken bunu sorunsuz
    geçiyor, ama testlerin verdiği `C:\\...` biçimli betik yolunu açamıyor —
    `/mnt/c/...` bekliyor, sonuç exit 127 "No such file or directory".
    Yani aday seçiliyor, sonra üç TestYayinNotu testi düşüyordu; WSL kurulu
    HER Windows makinesinde. CI bunu yapısal olarak göremiyor çünkü runner
    imajında dağıtım yok (bkz. ci.yml'deki "WSL durumu" adımı).

    Bu yüzden sonda artık gerçek bir betiği YERLİ YOLUYLA çalıştırıyor.
    Elenen aday `_bash()` döngüsünde atlanıyor ve sıra Git Bash'e geliyor;
    o Windows yollarını açabildiği için testler atlanmak yerine KOŞUYOR.
    """
    if not aday or not os.path.exists(aday):
        return False
    with tempfile.TemporaryDirectory() as gecici:
        betik = os.path.join(gecici, "sonda.sh")
        # Satır sonu LF olmalı: CRLF'te bash `$'\r'` diye takılır.
        with open(betik, "wb") as f:
            f.write(b"echo ok\n")
        try:
            r = subprocess.run([aday, betik], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=60)
        except OSError:
            return False
    return r.returncode == 0 and (r.stdout or "").strip() == "ok"


@functools.lru_cache(maxsize=1)
def _bash():
    """GERÇEKTEN çalışan bir bash bul; yoksa None.

    `shutil.which("bash")` Windows'ta System32'deki WSL SHIM'ini bulabiliyor.
    Dağıtım kurulu değilse o shim UTF-16LE bir "wsl --install -d <Distro>"
    mesajı basıp 1 döndürür — verilen betiği hiç çalıştırmadan. GitHub'ın
    windows-latest runner'ında birebir bu oldu (2026-08-31, run 33374248471):
    üç test "assert 1 == 0" ile düştü, hata metni NUL dolu geldi. Bu yüzden
    adı bulmak yetmiyor, ÇALIŞTIĞI sınanıyor.
    """
    for aday in _bash_adaylari():
        if _bash_calisiyor_mu(aday):
            return aday
    return None


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
        """Kapının kendisi: bozuk kalıp verilince yakalamalı, sağlamda susmalı."""
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
        kabuk = _bash()
        if kabuk is None:
            pytest.skip("çalışan bash yok")
        r = subprocess.run([kabuk, _NOTLAR, "9.9.9"], input="Deneme notu",
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
        kabuk = _bash()
        if kabuk is None:
            pytest.skip("çalışan bash yok")
        r = subprocess.run([kabuk, _NOTLAR, "1.0.0"],
                           input="<b>kalin</b> & 3>2", capture_output=True,
                           text=True, encoding="utf-8", cwd=_KOK)
        assert r.returncode == 0, r.stderr
        assert "&lt;b&gt;kalin&lt;/b&gt; &amp; 3&gt;2" in r.stdout
        assert "<b>kalin</b>" not in r.stdout

    def test_betik_cok_satirli_mesaji_koruyor(self):
        kabuk = _bash()
        if kabuk is None:
            pytest.skip("çalışan bash yok")
        r = subprocess.run([kabuk, _NOTLAR, "1.0.0"],
                           input="ilk satir\n- madde\n- madde2",
                           capture_output=True, text=True, encoding="utf-8",
                           cwd=_KOK)
        assert r.returncode == 0, r.stderr
        assert "ilk satir\n- madde\n- madde2" in r.stdout.replace("\r\n", "\n")

    def test_bash_yoklamasi_calismayan_adayi_eliyor(self, tmp_path):
        """Adı bulmak yetmiyor: WSL shim'i de `bash` adıyla PATH'te duruyor.

        Burada shim taklit ediliyor — UTF-16LE mesaj + sıfır dışı çıkış.
        Yoklama bunu elemezse betik testleri "assert 1 == 0" ile düşer.
        """
        sahte = tmp_path / ("bash.bat" if os.name == "nt" else "bash")
        if os.name == "nt":
            sahte.write_text("@echo off\r\nexit /b 1\r\n", encoding="ascii")
        else:
            sahte.write_text("#!/bin/sh\nprintf 'x' >&2\nexit 1\n", encoding="ascii")
            sahte.chmod(0o755)
        assert not _bash_calisiyor_mu(str(sahte))
        # Gerçek bash varsa yoklama onu KABUL etmeli — kapı hep-False olmasın
        gercek = _bash()
        if gercek is not None:
            assert _bash_calisiyor_mu(gercek)

    def test_surum_argumani_zorunlu(self):
        kabuk = _bash()
        if kabuk is None:
            pytest.skip("çalışan bash yok")
        r = subprocess.run([kabuk, _NOTLAR], input="x", capture_output=True,
                           text=True, encoding="utf-8", cwd=_KOK)
        assert r.returncode != 0, "sürümsüz çağrı sessizce geçmemeli"


def test_appimage_gomulu_python_surumu_sabit():
    """AppImage'a hangi yorumlayıcının gömüleceği TESADÜFE bırakılamaz.

    `build_appimage.sh` sistemin `python3`'ünden venv kuruyor ve PyInstaller
    onu AppImage'a gömüyor. `build-linux` job'ında `setup-python` YOKTU: yani
    kullanıcıya giden Linux sürümü runner imajının sistem Python'unu
    (ubuntu-22.04 → 3.10) taşıyordu. README ise "Python 3.12+" diyor ve
    Windows exe'si 3.12 ile paketleniyor — üç yüzey birbirini tutmuyordu.

    Ayrıca 3.10, CI'da tam suite koşusunun ~%25'inde segfault veren
    yorumlayıcıydı (bkz. tests/test_qt_yasam_dongusu.py), yani bu tesadüf
    kullanıcıyı da ilgilendiriyordu.
    """
    import re
    yol = os.path.join(_KOK, ".github", "workflows", "release.yml")
    kaynak = _oku(yol)
    m = re.search(r"(?s)  build-linux:.*?(?=\n  \w|\Z)", kaynak)
    assert m, "build-linux job'ı bulunamadı"
    job = m.group(0)
    assert "actions/setup-python" in job, (
        "build-linux'ta setup-python yok — AppImage runner'ın sistem "
        "python3'ünü gömer, sürüm tesadüfe kalır"
    )
    surumler = re.findall(r"python-version:\s*'([^']+)'", job)
    assert surumler == ["3.12"], surumler
    # Windows exe'siyle AYNI sürüm olmalı
    mw = re.search(r"(?s)  build-windows:.*?(?=\n  \w|\Z)", kaynak)
    assert re.findall(r"python-version:\s*'([^']+)'", mw.group(0)) == ["3.12"]


# ==========================================================================
# Paket kapisi sozlugun VARLIGINA degil BOYUTUNA da bakmali
#
# `paket_dogrula.py` uzun sure yalniz "dosya pakette var mi" diye soruyordu.
# Yarim acilmis bir sozluk (bkz. scripts/sozluk_ac.py) pakete girip bu
# kapidan "paket tam" diye geciyordu. OLCULDU (2026-09-05): ucte birine
# kirpilmis .dic ile gunluk on Turkce kelimenin sekizi yanlis sayiliyor,
# yani yazim denetimi calisiyor gorunup neredeyse her kelimeyi ciziyor.
#
# Beklenen boyut sabit esik degil, `sozlukler/*.xz`den hesaplaniyor; sozluk
# guncellenince denetim kendiliginden guncel kaliyor.
# ==========================================================================

import importlib.util as _importlib_util


def _paket_dogrula():
    yol = os.path.join(_KOK, "scripts", "paket_dogrula.py")
    spec = _importlib_util.spec_from_file_location("paket_dogrula", yol)
    mod = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_CEVIRI_DIZINI = os.path.join(_MASAUSTU, "translations")


def _sahte_paket(kok, dic_bayt=None, qtbase=("qtbase_tr.qm",)):
    """Onedir bicimli, digerleri TAM bir paket agaci kur.

    `dic_bayt` verilirse `tr_TR.dic` o boyuta kirpilir.
    `qtbase` Qt'nin kendi katalogundan pakete hangilerinin girdigini soyler;
    bos vermek o katalogun hic toplanmadigi durumu kurar.
    """
    import shutil

    os.makedirs(os.path.join(kok, "sozlukler"), exist_ok=True)
    os.makedirs(os.path.join(kok, "spylls", "hunspell", "data", "en"),
                exist_ok=True)
    for ad in ("tr_TR.dic", "tr_TR.aff"):
        kaynak = os.path.join(_KOK, "sozlukler", ad)
        hedef = os.path.join(kok, "sozlukler", ad)
        shutil.copy2(kaynak, hedef)
    if dic_bayt is not None:
        with open(os.path.join(kok, "sozlukler", "tr_TR.dic"), "r+b") as f:
            f.truncate(dic_bayt)
    for ad in ("en_US.dic", "en_US.aff"):
        # İkili mod: bunlar yalnızca "dosya var mı" denetimi için yer tutucu.
        open(os.path.join(kok, "spylls", "hunspell", "data", "en", ad),
             "wb").close()

    # Arayuz dili: bizim kataloglarimiz gercek boyutlariyla kopyalaniyor
    # (kapi boyuta da bakiyor), Qt'ninki yalniz varlik icin yer tutucu.
    hedef = os.path.join(kok, "translations")
    os.makedirs(hedef, exist_ok=True)
    for ad in ("latexeditor_tr.qm", "latexeditor_en.qm"):
        shutil.copy2(os.path.join(_CEVIRI_DIZINI, ad),
                     os.path.join(hedef, ad))
    qt = os.path.join(kok, "PyQt6", "Qt6", "translations")
    os.makedirs(qt, exist_ok=True)
    for ad in qtbase:
        open(os.path.join(qt, ad), "wb").close()
    return kok


@pytest.fixture(scope="module")
def _sozluk_hazir():
    """Ham `.dic`/`.aff` elde olmali; yoksa `.xz`den ac."""
    sys.path.insert(0, os.path.join(_KOK, "scripts"))
    import sozluk_ac
    if not sozluk_ac.ac(sessiz=True):
        pytest.skip("sozlukler/tr_TR.dic yok ve .xz'den acilamadi")


class TestPaketSozlukBoyutu:

    def test_tam_sozluk_temiz_geciyor(self, tmp_path, _sozluk_hazir):
        pd = _paket_dogrula()
        assert pd.dogrula(_sahte_paket(str(tmp_path / "tam"))) == 0

    def test_kirpilmis_sozluk_YAKALANIYOR(self, tmp_path, capsys,
                                          _sozluk_hazir):
        pd = _paket_dogrula()
        tam = os.path.getsize(os.path.join(_KOK, "sozlukler", "tr_TR.dic"))
        paket = _sahte_paket(str(tmp_path / "kirpik"), dic_bayt=tam // 3)
        rc = pd.dogrula(paket)
        cikti = capsys.readouterr().out
        assert rc != 0, "kirpilmis sozluk temiz sayildi"
        assert "KIRPILMIS" in cikti, cikti

    def test_beklenen_boyut_KAYNAKTAN_hesaplaniyor(self, _sozluk_hazir):
        """Sabit esik olsaydi sozluk guncellenince sessizce yanlislasirdi."""
        pd = _paket_dogrula()
        beklenen = pd._beklenen_boyut("tr_TR.dic")
        gercek = os.path.getsize(os.path.join(_KOK, "sozlukler", "tr_TR.dic"))
        assert beklenen == gercek

    def test_kaynak_yoksa_denetim_sessizce_atlaniyor(self, tmp_path,
                                                     monkeypatch,
                                                     _sozluk_hazir):
        """Betik depo disindan kosturulursa boyut denetimi yapilamaz.

        O durumda kapi patlamamali, yalnizca boyut denetimini atlamali.
        """
        pd = _paket_dogrula()
        monkeypatch.setattr(pd, "_KOK", str(tmp_path / "olmayan"))
        tam = os.path.getsize(os.path.join(_KOK, "sozlukler", "tr_TR.dic"))
        paket = _sahte_paket(str(tmp_path / "p"), dic_bayt=tam // 3)
        assert pd.dogrula(paket) == 0

    def test_xz_alt_dize_karismasi_yok(self, tmp_path, capsys, _sozluk_hazir):
        """`sozlukler/tr_TR.dic.xz` adi `.dic`i ALT DIZE olarak iceriyor.

        Boyut karsilastirmasi TAM eslesmeyle yapilmali. Alt dize kullanilirsa
        `.xz`in SIKISTIRILMIS boyutu, `.dic`in acilmis boyutuyla
        karsilastirilir ve kapi uydurma bir "KIRPILMIS" hatasi basar.

        Ayrim ancak `.dic` YOKKEN `.xz` VARKEN goruluyor: ikisi birden varsa
        dogru boyut da listede oldugu icin fark kapaniyor. Vaka o yuzden bu
        sekilde kuruluyor (olculdu 2026-09-05).
        """
        import shutil

        pd = _paket_dogrula()
        paket = _sahte_paket(str(tmp_path / "xzli"))
        os.remove(os.path.join(paket, "sozlukler", "tr_TR.dic"))
        shutil.copy2(os.path.join(_KOK, "sozlukler", "tr_TR.dic.xz"),
                     os.path.join(paket, "sozlukler", "tr_TR.dic.xz"))

        rc = pd.dogrula(paket)
        cikti = capsys.readouterr().out
        assert rc != 0, "`.xz` olu agirligi hata olmali"
        # Asil sorun `.xz`in pakete girmesi; uydurma bir boyut hatasi degil.
        assert "olu agirlik" in cikti, cikti
        assert "KIRPILMIS" not in cikti, (
            "sikistirilmis dosyanin boyutu acilmis boyutla karsilastirilmis:\n"
            + cikti)


# ==========================================================================
# Paket kapisi ARAYUZ DILINI de gormeli
#
# Uygulama iki katalog kullaniyor ve ikisi de ayri sekilde sessizce
# dusebiliyor: bizimki (`translations/latexeditor_<dil>.qm`, spec datas'tan)
# ve Qt'nin kendisi (`qtbase_<dil>.qm`, PyInstaller Qt hook'undan). Ikincinin
# adi bizde HICBIR YERDE gecmiyor; hook degisirse arayuz Turkce acilir ama
# Qt'nin urettigi sag tik menuleri ve dugmeler Ingilizce kalir. Bu tam olarak
# "yalniz paketlenmis urunde gorunen" sinifi: testler paketlenmemis kaynakta
# kosuyor ve orada `QLibraryInfo` dogrudan PyQt6 kurulumunu gosteriyor.
# ==========================================================================

class TestPaketCevirileri:

    def test_TAM_paket_temiz_geciyor(self, tmp_path, _sozluk_hazir):
        pd = _paket_dogrula()
        paket = _sahte_paket(str(tmp_path / "tam"))
        assert pd.dogrula(paket) == 0

    @pytest.mark.parametrize("ad", ["latexeditor_tr.qm", "latexeditor_en.qm"])
    def test_UYGULAMA_katalogu_dusunce_yakalaniyor(self, tmp_path, capsys,
                                                   _sozluk_hazir, ad):
        pd = _paket_dogrula()
        paket = _sahte_paket(str(tmp_path / ("y" + ad[:3])))
        os.remove(os.path.join(paket, "translations", ad))
        rc = pd.dogrula(paket)
        cikti = capsys.readouterr().out
        assert rc != 0, "eksik katalog temiz sayildi"
        assert ad in cikti and "GIRMEMIS" in cikti, cikti

    def test_KIRPILMIS_katalog_yakalaniyor(self, tmp_path, capsys,
                                           _sozluk_hazir):
        """Varlik yetmez: yarim kopyalanmis `.qm` sessizce ise yaramaz."""
        pd = _paket_dogrula()
        paket = _sahte_paket(str(tmp_path / "kirpik_qm"))
        yol = os.path.join(paket, "translations", "latexeditor_tr.qm")
        with open(yol, "r+b") as f:
            f.truncate(os.path.getsize(yol) // 3)
        rc = pd.dogrula(paket)
        cikti = capsys.readouterr().out
        assert rc != 0
        assert "KIRPILMIS" in cikti, cikti

    def test_QT_katalogu_dusunce_yakalaniyor(self, tmp_path, capsys,
                                             _sozluk_hazir):
        """Kullanicinin bildirdigi kusurun paketlenmis surumdeki hali."""
        pd = _paket_dogrula()
        paket = _sahte_paket(str(tmp_path / "qtsuz"), qtbase=())
        rc = pd.dogrula(paket)
        cikti = capsys.readouterr().out
        assert rc != 0, "qtbase katalogu olmadan paket tam sayildi"
        assert "qtbase_tr.qm" in cikti, cikti

    def test_BASKA_dilin_qtbase_i_yerine_gecmiyor(self, tmp_path, capsys,
                                                  _sozluk_hazir):
        """Asiri gevsek kapi kapisi: `qtbase_en.qm` varligi yetmemeli."""
        pd = _paket_dogrula()
        paket = _sahte_paket(str(tmp_path / "yanlisdil"), qtbase=("qtbase_en.qm",))
        assert pd.dogrula(paket) != 0
        assert "qtbase_tr.qm" in capsys.readouterr().out

    def test_TS_kaynaklari_olu_agirlik_sayiliyor(self, tmp_path, capsys,
                                                 _sozluk_hazir):
        """`.ts` ~300 KB; uygulama yalniz `.qm` okuyor."""
        pd = _paket_dogrula()
        paket = _sahte_paket(str(tmp_path / "tsli"))
        shutil.copy2(os.path.join(_CEVIRI_DIZINI, "latexeditor_tr.ts"),
                     os.path.join(paket, "translations", "latexeditor_tr.ts"))
        rc = pd.dogrula(paket)
        cikti = capsys.readouterr().out
        assert rc != 0, "`.ts` olu agirligi temiz sayildi"
        assert "olu agirlik" in cikti, cikti
        # `.qm` de ".ts" ile bitmez; kapi onlari suclamamali.
        assert "latexeditor_tr.qm" not in [
            s for s in cikti.splitlines() if s.startswith("HATA")]

    @pytest.mark.parametrize("spec", ["LaTeX Editor.spec",
                                      "latex-editor-linux.spec"])
    def test_IKI_SPEC_de_ts_yi_disliyor(self, spec):
        """Iki spec ayri dosya; biri otekinden sessizce ayrisabiliyor."""
        metin = _oku(os.path.join(_MASAUSTU, spec))
        assert "endswith('.ts')" in metin, (
            "%s ceviri kaynaklarini paketten dislamiyor" % spec)


# ==========================================================================
# Qt'nin KULLANILMAYAN dil kataloglari pakete girmemeli
#
# PyInstaller'in Qt hook'u `QtCore -> ['qt', 'qtbase']`, `Qsci ->
# ['qscintilla']` ve `QtHelp -> ['qt_help']` eslemelerinden o dizindeki
# BUTUN dilleri topluyor. Yayinlanan v1.0.21 Windows exe'sinde olculdu
# (2026-09-06): 101 katalog, acilmis 6.9 MB. Uygulama bunlardan yalnizca
# `qtbase_tr.qm` ile `qtbase_en.qm`i yukluyor.
#
# Suzgec iki spec'te DEGIL scripts/paket_suzgeci.py'de: bu depo "uc ayri
# paketleme tanimi" sinifindan bir kez yandi ve iki spec ayri dosya.
# ==========================================================================


def _paket_suzgeci():
    yol = os.path.join(_KOK, "scripts", "paket_suzgeci.py")
    spec = _importlib_util.spec_from_file_location("paket_suzgeci", yol)
    mod = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _toc(*hedefler):
    """PyInstaller TOC girdisi: (hedef_ad, kaynak_yol, tur)."""
    return [(h, "/kaynak/" + os.path.basename(h), "DATA") for h in hedefler]


_QT = "PyQt6/Qt6/translations/"
_TAM_TOC = _toc(
    "translations/latexeditor_tr.qm", "translations/latexeditor_en.qm",
    _QT + "qtbase_tr.qm", _QT + "qtbase_en.qm",
    _QT + "qtbase_de.qm", _QT + "qtbase_zh_CN.qm",
    _QT + "qt_tr.qm", _QT + "qt_help_tr.qm", _QT + "qscintilla_fr.qm",
    "sozlukler/tr_TR.dic", "gui/main_window.py",
)


def _adlar(toc):
    return [t[0] for t in toc]


class TestQtCevirileriSuzgeci:

    def test_DILLER_kendi_kataloglarimizdan_okunuyor(self):
        """Dil listesi elle yazilsaydi core.i18n'inkinden ayrisirdi."""
        assert _paket_suzgeci().diller(_TAM_TOC) == {"tr", "en"}

    def test_KULLANILMAYAN_diller_atiliyor(self):
        kalan = _adlar(_paket_suzgeci().qt_cevirilerini_ele(_TAM_TOC))
        for atilmali in (_QT + "qtbase_de.qm", _QT + "qtbase_zh_CN.qm",
                         _QT + "qt_tr.qm", _QT + "qt_help_tr.qm",
                         _QT + "qscintilla_fr.qm"):
            assert atilmali not in kalan, atilmali

    def test_KULLANILAN_diller_KALIYOR(self):
        """Asiri suzme kapisi: `qtbase_tr` giderse arayuz yarim Ingilizce."""
        kalan = _adlar(_paket_suzgeci().qt_cevirilerini_ele(_TAM_TOC))
        assert _QT + "qtbase_tr.qm" in kalan
        assert _QT + "qtbase_en.qm" in kalan

    def test_QT_DISINDAKI_hicbir_sey_atilmiyor(self):
        """Suzgec yalnizca Qt'nin ceviri dizinine dokunmali."""
        kalan = _adlar(_paket_suzgeci().qt_cevirilerini_ele(_TAM_TOC))
        for durmali in ("translations/latexeditor_tr.qm",
                        "translations/latexeditor_en.qm",
                        "sozlukler/tr_TR.dic", "gui/main_window.py"):
            assert durmali in kalan, durmali

    def test_ONEDIR_oneki_ve_TERS_BOLU_de_taniniyor(self):
        """Linux onedir `_internal/` altinda; Windows TOC'u ters bolu verir."""
        pd = _paket_suzgeci()
        toc = _toc("_internal/translations/latexeditor_tr.qm",
                   "_internal\\PyQt6\\Qt6\\translations\\qtbase_tr.qm",
                   "_internal/PyQt6/Qt6/translations/qtbase_de.qm")
        kalan = _adlar(pd.qt_cevirilerini_ele(toc))
        assert "_internal/PyQt6/Qt6/translations/qtbase_de.qm" not in kalan
        assert "_internal\\PyQt6\\Qt6\\translations\\qtbase_tr.qm" in kalan
        # BIZIM katalogumuz da `_internal/translations/` altinda ve olcut
        # yalnizca "/translations/" olsaydi o da atilirdi: Linux yapisinda
        # arayuz komple Ingilizceye donerdi. Onefile yolunda (`translations/`,
        # basta egik cizgi yok) bu ayrim GORUNMUYOR, mutasyon oradan kaciyordu.
        assert "_internal/translations/latexeditor_tr.qm" in kalan

    def test_YENI_DIL_eklenince_kendiliginden_taniniyor(self):
        """Tek kaynak: katalog eklemek disinda hicbir yer degismemeli."""
        pd = _paket_suzgeci()
        toc = _toc("translations/latexeditor_de.qm",
                   _QT + "qtbase_de.qm", _QT + "qtbase_fr.qm")
        kalan = _adlar(pd.qt_cevirilerini_ele(toc))
        assert _QT + "qtbase_de.qm" in kalan
        assert _QT + "qtbase_fr.qm" not in kalan

    def test_KENDI_KATALOGUMUZ_yoksa_suzgec_DEVREYE_GIRMIYOR(self, capsys):
        """Yoksa tutulacak kume bos olur ve bir eksik ikiye katlanirdi."""
        pd = _paket_suzgeci()
        toc = _toc(_QT + "qtbase_tr.qm", _QT + "qtbase_de.qm")
        kalan = pd.qt_cevirilerini_ele(toc)
        assert _adlar(kalan) == _adlar(toc), "her sey silinmis"
        assert "UYARI" in capsys.readouterr().out

    @pytest.mark.parametrize("spec", ["LaTeX Editor.spec",
                                      "latex-editor-linux.spec"])
    def test_IKI_SPEC_de_suzgeci_cagiriyor(self, spec):
        metin = _oku(os.path.join(_MASAUSTU, spec))
        assert "qt_cevirilerini_ele(a.datas)" in metin, (
            "%s Qt cevirilerini suzmuyor" % spec)


class TestPaketKapisiQtCevirileri:

    def test_KULLANILMAYAN_katalog_pakette_YAKALANIYOR(self, tmp_path, capsys,
                                                       _sozluk_hazir):
        """Suzgec sessizce duserse bunu kapi soylemeli."""
        pd = _paket_dogrula()
        paket = _sahte_paket(str(tmp_path / "fazla"),
                             qtbase=("qtbase_tr.qm", "qtbase_de.qm"))
        rc = pd.dogrula(paket)
        cikti = capsys.readouterr().out
        assert rc != 0, "kullanilmayan katalog temiz sayildi"
        assert "kullanilmayan" in cikti and "qtbase_de" in cikti, cikti

    def test_KULLANILAN_diller_kapiyi_dusurmuyor(self, tmp_path,
                                                 _sozluk_hazir):
        """Asiri hassas kapi kapisi: iki dilimiz de serbest gecmeli."""
        pd = _paket_dogrula()
        paket = _sahte_paket(str(tmp_path / "ikidil"),
                             qtbase=("qtbase_tr.qm", "qtbase_en.qm"))
        assert pd.dogrula(paket) == 0
