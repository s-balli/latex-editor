"""Windows/WSL köprüsü — GERÇEK bir alt süreç üzerinden.

Depodaki mevcut WSL testleri `subprocess.run`ı mock'layıp argv'yi denetliyor.
Bu dosya bir adım aşağı iniyor: PATH'e gerçek bir çalıştırılabilir `wsl`
konuyor ve köprü gerçekten süreç açıyor. Mock'un göremediği üç şey burada
sınanıyor — argümanların süreç sınırından geçişi (boşluk, Türkçe harf),
boruların KODLAMASI, ve çıkış kodu/zaman aşımı davranışı.

SAHTE `wsl` UYDURMA DEĞİL: davranışı bu makinede gerçek wsl.exe ölçülerek
yazıldı (2026-08-31, Windows 10 / WSL2 Ubuntu):

  wsl -d YokBoyleBirDagitim -e true
      rc     : 4294967295
      stdout : 160 bayt, UTF-16LE — 'Sağlanan ada sahip dağıtım yok.\\r\\n
               Hata kodu: Wsl/Service/WSL_E_DISTRO_NOT_FOUND\\r\\n'
      stderr : BOŞ            <- hata STDERR'e değil STDOUT'a gidiyor
  wsl -e printf 'Çıktı: başarılı — 0 hata'
      stdout : düz UTF-8, dönüşüm yok
  wsl -e sh -c 'exit N'
      rc     : N (0, 3, 42 denendi)

NE KAPSAMIYOR: Microsoft'un ikilisinin kendisi. Gerçek wsl.exe'ye karşı
koşacak bir kapı hiçbir CI job'ında koşamıyor — ubuntu runner'da WSL yok,
windows runner'ında da dağıtım kurulu değil (ci.yml'in test-windows job'ı
bunu log'a yazıyor). O yüzden kapı, ÖLÇÜLEN sözleşmeye karşı BİZİM kodumuzu
sınıyor; sözleşme değişirse yukarıdaki ölçüm elle tekrarlanmalı.

Sahte `wsl` bir kabuk betiği olduğu için yalnız POSIX'te kuruluyor: Windows'ta
CreateProcess uzantısız ada `.exe` ekleyerek arar, `.bat`/`.py` gölgeleyemez.
Köprü kodu platformdan bağımsız Python; `_PLATFORM` yamalanarak WSL kolu
seçiliyor.
"""

import json
import os
import subprocess
import sys

import pytest

if os.name == "nt":  # pragma: no cover
    pytest.skip("sahte `wsl` yalnız POSIX'te PATH'ten gölgelenebilir",
                allow_module_level=True)

from gui import synctex  # noqa: E402

# wsl.exe'nin bilinmeyen dağıtımda döndürdüğü hata (ölçülen metin)
_WSL_HATA = "Sağlanan ada sahip dağıtım yok.\r\nHata kodu: Wsl/Service/WSL_E_DISTRO_NOT_FOUND\r\n"

_SAHTE = r'''#!{python}
# -*- coding: utf-8 -*-
"""wsl.exe taklidi — davranisi test docstring'inde olculdu."""
import json, os, sys, time

argv = sys.argv[1:]
kayit = os.environ.get("SAHTE_WSL_KAYIT")
if kayit:
    with open(kayit, "a", encoding="utf-8") as f:
        f.write(json.dumps(argv) + "\n")

mod = os.environ.get("SAHTE_WSL_MOD", "normal")

if mod == "dagitim_yok":
    # GERCEK DAVRANIS: hata STDOUT'a, UTF-16LE, rc != 0
    sys.stdout.buffer.write({hata!r}.encode("utf-16-le"))
    sys.stdout.buffer.flush()
    sys.exit(1)

if mod == "askida":
    time.sleep(30)
    sys.exit(0)

if mod == "cikis3":
    sys.exit(3)

if argv[:1] == ["-e"]:
    argv = argv[1:]

if argv[:2] == ["synctex", "view"]:
    # Gercek `synctex view` ciktisinin bicimi
    sys.stdout.buffer.write(
        ("This is SyncTeX command line utility\n"
         "SyncTeX result begin\n"
         "Output:{cikti}\n"
         "Page:7\n"
         "x:133.768\n"
         "y:412.5\n"
         "h:120.0\n"
         "W:355.0\n"
         "H:9.9\n"
         "SyncTeX result end\n").encode("utf-8"))
    sys.exit(0)

if argv[:2] == ["synctex", "edit"]:
    sys.stdout.buffer.write(
        ("SyncTeX result begin\n"
         "Input:/mnt/c/Users/Serif Cagri/Tez Calismasi/bolum ozet.tex\n"
         "Line:314\n"
         "Column:-1\n"
         "SyncTeX result end\n").encode("utf-8"))
    sys.exit(0)

if not argv:
    sys.exit(0)
os.execvp(argv[0], argv)
'''


@pytest.fixture
def sahte_wsl(tmp_path, monkeypatch):
    """PATH'in başına gerçek bir çalıştırılabilir `wsl` koy."""
    bin_dizin = tmp_path / "bin"
    bin_dizin.mkdir()
    betik = bin_dizin / "wsl"
    betik.write_text(
        _SAHTE.format(python=sys.executable, hata=_WSL_HATA, cikti="/mnt/c/x/main.pdf"),
        encoding="utf-8")
    betik.chmod(0o755)

    kayit = tmp_path / "argv.jsonl"
    monkeypatch.setenv("PATH", f"{bin_dizin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("SAHTE_WSL_KAYIT", str(kayit))
    monkeypatch.setattr(synctex, "_PLATFORM", "win32")

    class Kontrol:
        yol = str(betik)

        @staticmethod
        def argv_listesi():
            if not kayit.exists():
                return []
            return [json.loads(s) for s in
                    kayit.read_text(encoding="utf-8").splitlines() if s.strip()]

    return Kontrol


def test_sahte_wsl_gercekten_calisiyor(sahte_wsl):
    """Kapının kapısı: sahte gerçekten PATH'ten bulunup KOŞUYOR mu?

    Bulunmazsa aşağıdaki testler FileNotFoundError'ı yutup None'a düşer ve
    hiçbir şey sınamadan yeşil kalırdı.
    """
    r = subprocess.run(["wsl", "-e", "echo", "merhaba"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0
    assert r.stdout.strip() == "merhaba"
    assert sahte_wsl.argv_listesi() == [["-e", "echo", "merhaba"]]


class TestIleriArama:

    def test_yol_cevirisi_surec_sinirindan_gecti(self, sahte_wsl):
        """Boşluklu ve Türkçe yol, argv dizisi olarak bozulmadan gitmeli."""
        sonuc = synctex.forward_search(
            r"C:\Users\Şerif Çağrı\Tez Çalışması\bölüm özet.tex", 314, 1,
            r"C:\Users\Şerif Çağrı\Tez Çalışması\tez.pdf")
        assert sonuc is not None
        argv = sahte_wsl.argv_listesi()[0]
        assert argv[:3] == ["-e", "synctex", "view"]
        assert argv[4] == "314:1:/mnt/c/Users/Şerif Çağrı/Tez Çalışması/bölüm özet.tex"
        assert argv[6] == "/mnt/c/Users/Şerif Çağrı/Tez Çalışması/tez.pdf"

    def test_cikti_ayristirildi(self, sahte_wsl):
        sonuc = synctex.forward_search(r"C:\x\main.tex", 10, 1, r"C:\x\main.pdf")
        assert sonuc.page == 7
        assert sonuc.x == pytest.approx(133.768)
        assert sonuc.y == pytest.approx(412.5)
        assert sonuc.left == pytest.approx(120.0)
        assert sonuc.width == pytest.approx(355.0)
        assert sonuc.height == pytest.approx(9.9)

    def test_synctex_dizini_aktariliyor(self, sahte_wsl):
        synctex.forward_search(r"C:\x\main.tex", 1, 1, r"C:\x\main.pdf",
                               r"C:\x\.synctex")
        argv = sahte_wsl.argv_listesi()[0]
        assert argv[-2:] == ["-d", "/mnt/c/x/.synctex"]


class TestGeriArama:

    def test_wsl_yolu_windows_yoluna_donuyor(self, sahte_wsl):
        sonuc = synctex.reverse_search(7, 133.7, 412.5, r"C:\x\main.pdf")
        assert sonuc is not None
        assert sonuc.line == 314
        assert sonuc.col == 0          # synctex "-1" -> 0
        # Ters bölü ve boşluklar korunmuş, sürücü harfi büyütülmüş olmalı.
        assert sonuc.file_path == "C:\\Users\\Serif Cagri\\Tez Calismasi\\bolum ozet.tex"

    def test_koordinatlar_tamsayilastiriliyor(self, sahte_wsl):
        synctex.reverse_search(7, 133.768, 412.5, r"C:\x\main.pdf")
        argv = sahte_wsl.argv_listesi()[0]
        assert argv[:3] == ["-e", "synctex", "edit"]
        assert argv[4] == "7:133:412:/mnt/c/x/main.pdf"


class TestHataYollari:
    """wsl.exe'nin ÖLÇÜLEN aksaklıkları — kodun hiçbirinde patlamaması lazım."""

    def test_dagitim_yok_UTF16_stdout_cokmeye_yol_acmiyor(self, sahte_wsl, monkeypatch):
        """Hata STDOUT'a UTF-16LE gidiyor; utf-8 çözücü NUL dolu çöp üretir.

        rc != 0 olduğu için köprü zaten None döner — kritik olan, çözme
        hatasının istisnaya dönüşmemesi (errors='replace').
        """
        monkeypatch.setenv("SAHTE_WSL_MOD", "dagitim_yok")
        assert synctex.forward_search(r"C:\x\a.tex", 1, 1, r"C:\x\a.pdf") is None
        assert synctex.reverse_search(1, 1.0, 1.0, r"C:\x\a.pdf") is None

    def test_UTF16_ciktisi_utf8_cozucude_NUL_uretiyor(self, sahte_wsl, monkeypatch):
        """Sözleşmenin kendisi: compiler'daki UTF-16 sezgisi bu yüzden var."""
        monkeypatch.setenv("SAHTE_WSL_MOD", "dagitim_yok")
        r = subprocess.run(["wsl", "-e", "true"], capture_output=True)
        assert r.returncode != 0
        assert r.stderr == b"", "gerçek wsl.exe hatayı STDERR'e değil STDOUT'a yazıyor"
        assert r.stdout.decode("utf-16-le") == _WSL_HATA
        bozuk = r.stdout.decode("utf-8", "replace")
        assert "\x00" in bozuk, "utf-8 çözücü UTF-16'yı bozmalı — sezginin gerekçesi bu"

    def test_sifir_disi_cikis_kodu_None(self, sahte_wsl, monkeypatch):
        monkeypatch.setenv("SAHTE_WSL_MOD", "cikis3")
        assert synctex.forward_search(r"C:\x\a.tex", 1, 1, r"C:\x\a.pdf") is None

    def test_zaman_asimi_None_donuyor_istisna_sizmiyor(self, sahte_wsl, monkeypatch):
        monkeypatch.setenv("SAHTE_WSL_MOD", "askida")
        monkeypatch.setattr(synctex, "_ZAMAN_ASIMI", 1)
        assert synctex.forward_search(r"C:\x\a.tex", 1, 1, r"C:\x\a.pdf") is None

    def test_wsl_hic_yoksa_ARAC_YOK(self, monkeypatch, tmp_path):
        """WSL kurulu değil: FileNotFoundError yakalanmalı, işaret ARAC_YOK.

        Bu iddia `is None`dı ve `None` artık "koştu, eşleşme yok" demek.
        WSL'in hiç olmaması tam da "araç çalıştırılamadı" hâli; kullanıcıya
        "Eşleşme bulunamadı" denmesi onu konumu yanlış sanmaya götürüyordu
        (bkz. tests/test_synctex_koprusu.py başlığındaki ölçüm).

        `ARAC_YOK` falsy olduğu için `if result:` yazan çağıranlar için
        davranış değişmedi; testin eski niyeti (istisna sızmasın, sonuç
        "yok" sayılsın) korunuyor.
        """
        monkeypatch.setattr(synctex, "_PLATFORM", "win32")
        monkeypatch.setenv("PATH", str(tmp_path))   # `wsl` bulunamaz
        sonuc = synctex.forward_search(r"C:\x\a.tex", 1, 1, r"C:\x\a.pdf")
        assert sonuc is synctex.ARAC_YOK
        assert not sonuc, "falsy kalmalı: eski çağıranlar bozulmasın"


class TestKodlama:
    """Bu depoda kodlama hataları iki kez sessizce SyncTeX'i öldürdü."""

    def test_turkce_ciktinin_tamami_geliyor(self, sahte_wsl):
        """Gerçek boru üzerinden: cp1254 çözümü 'Ş'te (0x9E) patlıyordu."""
        r = subprocess.run(["wsl", "-e", "printf", "Çıktı: başarılı — 0 hata"],
                           capture_output=True)
        assert r.stdout.decode("utf-8") == "Çıktı: başarılı — 0 hata"

    def test_dort_cagri_da_encoding_veriyor(self):
        """text=True + encoding yoksa Python locale'e düşer (Türkçe Windows:
        cp1254) ve çözme hatası OKUMA THREAD'inde olduğu için run() istisna
        FIRLATMAZ: stdout None olur, returncode 0 kalır, _parse_*(None)
        AttributeError verir ve geniş except onu yutar."""
        import ast
        import inspect
        agac = ast.parse(inspect.getsource(synctex))
        cagrilar = [n for n in ast.walk(agac)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == "run"]
        assert len(cagrilar) == 4, f"beklenen 4 subprocess.run, bulunan {len(cagrilar)}"
        for c in cagrilar:
            kw = {k.arg for k in c.keywords}
            assert "encoding" in kw and "errors" in kw
