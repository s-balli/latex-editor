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


def _sahte_paket(kok, dic_bayt=None):
    """Onedir bicimli, digerleri TAM bir paket agaci kur.

    `dic_bayt` verilirse `tr_TR.dic` o boyuta kirpilir.
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
