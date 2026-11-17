# -*- coding: utf-8 -*-
"""wsl.exe'nin Job Object'e atanması: uygulama ölünce derleme sahipsiz kalmasın.

ÖLÇÜM (2026-11-17, gerçek exe'de, Claude'un denemesi; bu dosyadaki
testler kendisi o ölçümü yapmadı): sonsuz döngüye giren belge derlenirken
uygulama `taskkill /F` ile öldürüldü; derlemeyi taşıyan wsl.exe ve WSL
içindeki pdflatex %100 CPU ile 40+ sn koşmaya devam etti, kendiliğinden
durmadı. Dıştaki wsl.exe elle öldürülünce WSL içindeki ağaç ~4 sn içinde
düştü. Düzeltme (core/win_job.py): wsl.exe'yi
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE bayraklı bir job'a atamak; uygulama
ölünce çekirdek son job tutamacını kapatır ve job üyeleri (wsl.exe,
torunları) ölür.

ASIL KAPI (yalnız Windows'ta koşar): yardımcı bir ebeveyn süreç
uygulamanın yerine geçer, uzun ömürlü bir çocuk başlatır ve projenin job
yardımcısıyla onu job'a atar; test ebeveyni `taskkill /F` ile öldürür.
Job'a atanan çocuk birkaç saniye içinde bitmelidir. Denetim kolu:
ATANMAYAN çocuk ebeveyn ölümünde YAŞAMALI; düşerse ölüm job'tan değil,
ölçüm yönteminden geliyordur.

GERÇEK LatexCompiler Windows YOLU NEDEN YOK: CreateProcess aranabilir ad
için uygulama dizinine, geçerli dizine ve System32'ye PATH'ten ÖNCE
bakar; System32'de gerçek wsl.exe durur, PATH'e konacak sahte bir wsl
onu gölgeleyemez (uzantısız "wsl" adı .exe ekiyle aranır, .cmd sahtesi
aramaya girmez; tests/test_wsl_koprusu.py'nin docstring'i aynı dersi
yazıyor). Gerçek wsl.exe'yi koşturmaksa kullanıcının WSL dağıtımını ayağa
kaldırır, test özselleştirilemez. Bunun yerine: _start_windows'un atamayı
`started` sinyaline bağladığı birim düzeyde (TestStartWindowsBaglanti),
atama hata yolunun süreci bozmadığı gerçek QProcess'le
(TestAtamaHatasiYolu) sınanıyor.

R0: bu dosya düzeltmeden ÖNCE de koşmalı. Düzeltmesiz kodda:
 - TestStartWindowsBaglanti.test_baglanti DÜŞER (_wsl_joba_ata yok),
 - TestWindowsDisinda.test_atama_noop DÜŞER (core/win_job yok),
 - Windows'ta asıl kapı DÜŞER: yardımcı modül yokluğunda atamayı ATLAR,
   çocuğu yine de başlatır ve ebeveyn ölümünde çocuk YAŞAR (ImportError
   fırlatarak değil; kural bu biçimi istiyor).
"""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import QEventLoop, QProcess, QTimer
from PyQt6.QtWidgets import QApplication

import core.compiler as compiler_mod
from core.compiler import LatexCompiler

try:
    from core import win_job
except ImportError:                  # düzeltilmemiş kod: modül henüz yok
    win_job = None

# QTimer (LatexCompiler watchdog'ı) için bir QApplication gerekir.
_app = QApplication.instance() or QApplication([])

_KOK = str(Path(__file__).resolve().parents[1])


class TestStartWindowsBaglanti:
    """_start_windows atamayı `started` sinyaline bağlamalı (birim düzey).

    QProcess mock'lu: süreç gerçekten başlamıyor, yalnız bağlantı
    deneniyor. Windows'ta gerçek job/çekirdek davranışı TestUygulamaOlunce,
    gerçek sinyal akışı da uygulamanın kendisinde sınanıyor.
    """

    def test_baglanti(self, tmp_path):
        tex = tmp_path / "a.tex"
        tex.write_text("x", encoding="utf-8")
        c = LatexCompiler()
        atayici = getattr(c, "_wsl_joba_ata", None)
        assert atayici is not None, "_wsl_joba_ata yok (düzeltilmemiş kod)"
        with patch("core.compiler.PLATFORM", "win32"), \
             patch("core.compiler.QProcess") as mock_qproc:
            mock_proc = MagicMock()
            mock_qproc.return_value = mock_proc
            assert c.compile(str(tex)) is True
            # Atama started sinyalinde: start() dönüşünde processId()
            # henüz güvenilir olmayabilir.
            mock_proc.started.connect.assert_called_once_with(atayici)
        c._timeout_timer.stop()


@pytest.mark.skipif(sys.platform == "win32",
                    reason="Windows'ta atama gerçekte yapılır; bu kapı "
                           "Windows dışındaki no-op davranışı sınar")
class TestWindowsDisinda:
    """Windows dışında yeni kod hiçbir şey yapmamalı.

    ctypes.windll Windows'a özeldir; modül Windows dışında da içe
    aktarılabilir olmalı ve çağrılar no-op olmalı.
    """

    def test_atama_noop(self):
        assert win_job is not None, "core/win_job yok (düzeltilmemiş kod)"
        # Bu süreçte job açılmaz, OpenProcess çağrılmaz; dönüş False.
        assert win_job.sureci_joba_ata(os.getpid()) is False

    def test_native_yol_atamayi_cagirmiyor(self, tmp_path, monkeypatch):
        """Yerli yol (Linux/macOS) job ataması yapmamalı.

        Aşırı düzeltme kapısı: job wsl.exe sahipsiz kalmasın diye; yerli yolun
        bekçisi derle.sh'te (LATEX_EDITOR_PID), Windows'a taşınmaz.
        """
        if win_job is None:
            pytest.skip("core/win_job yok (düzeltilmemiş kod); bağlantı "
                        "kapısı zaten kırmızı)")
        cagrilar = []

        def _kaydet(pid):
            cagrilar.append(pid)
            return True

        monkeypatch.setattr(win_job, "sureci_joba_ata", _kaydet)
        betik = tmp_path / "sahte_derle.sh"
        betik.write_text("#!/bin/bash\nsleep 30\n", encoding="utf-8")
        monkeypatch.setattr(compiler_mod, "_find_derle_sh",
                            lambda: str(betik))
        tex = tmp_path / "a.tex"
        tex.write_text("x", encoding="utf-8")
        c = LatexCompiler()
        try:
            assert c.compile(str(tex)) is True
            assert c.process.waitForStarted(10000)
            dongu = QEventLoop()
            QTimer.singleShot(1500, dongu.quit)
            dongu.exec()
            assert cagrilar == [], "yerli yol job ataması yapıyor"
        finally:
            c.stop()


class TestAtamaHatasiYolu:
    """Atama hatası derleme akışını bozmamalı (gerçek QProcess, her platform).

    2026-11-17 tasarım kuralı: atama yalnız uygulama ölünce devreye giren
    bir sigortadır; başarısızlığı derlemeyi ASLA durduramaz, sebep günlüğe
    yazılır. Windows kolunun çağrısı yamalı; süreç ve _wsl_joba_ata GERÇEK.
    """

    def test_atama_hatasi_sureci_bozmuyor(self, monkeypatch, caplog):
        assert win_job is not None, "core/win_job yok (düzeltilmemiş kod)"
        c = LatexCompiler()
        atayici = getattr(c, "_wsl_joba_ata", None)
        assert atayici is not None, "_wsl_joba_ata yok (düzeltilmemiş kod)"

        def _patla(pid):
            raise RuntimeError("yamalanmış atama hatası")

        monkeypatch.setattr(win_job, "sureci_joba_ata", _patla)
        c.process = QProcess()
        c.process.start(sys.executable,
                        ["-c", "import time; time.sleep(30)"])
        assert c.process.waitForStarted(10000), "yardımcı süreç başlamadı"
        try:
            caplog.set_level(logging.WARNING, logger="latex_editor.compiler")
            atayici()            # started sinyalinin yerine: aynı çağrı
            _app.processEvents()
            assert c.process.state() == QProcess.ProcessState.Running, \
                "atama hatası derlemeyi durdurdu"
            assert any(r.levelno >= logging.WARNING
                       and "job" in r.getMessage()
                       for r in caplog.records), \
                "atama hatası günlüğe yazılmadı:\n" + caplog.text
        finally:
            c.process.kill()
            c.process.waitForFinished(5000)


# Yardımcı ebeveyn: UYGULAMANIN yerine geçen süreç. Çocuk başlatır, mod
# "job" ise projenin job yardımcısıyla onu job'a atar; modül yoksa
# (düzeltilmemiş kod) atamayı atlar ve çocuğu yine de bırakır: asıl kapının
# R0'da çocuğun YAŞADIĞINI göstermesi için. Bilgi dosyasına PID'leri
# yazar, sonra bekler.
YARDIMCI_KAYNAGI = '''\
# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import tempfile
import time

mod, bilgi_yolu = sys.argv[1], sys.argv[2]

# Günlük gerçek kullanıcı dosyasına gitmesin (tests/conftest.py dersidir;
# yardımcı pytest altında değil): core.log'u win_job importundan ÖNCE
# geçici dizine hapsediyoruz.
import core.log as gunluk
gunluk.LOG_DIR = tempfile.mkdtemp(prefix="win-job-test-")
gunluk.LOG_FILE = os.path.join(gunluk.LOG_DIR, "latex-editor.log")

cocuk = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(300)"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

atanmis = None
if mod == "job":
    atanmis = False
    try:
        from core import win_job
    except ImportError:
        atanmis = None     # düzeltme yok: atama yok, çocuk yine de başladı
    else:
        atanmis = bool(win_job.sureci_joba_ata(cocuk.pid))

with open(bilgi_yolu, "w", encoding="utf-8") as f:
    json.dump({"cocuk": cocuk.pid, "ebeveyn": os.getpid(),
               "atanmis": atanmis}, f)
time.sleep(300)
'''


@pytest.mark.skipif(sys.platform != "win32",
                    reason="asıl kapı: gerçek Windows job/çekirdek davranışı")
class TestUygulamaOlunce:
    """Ebeveyn `taskkill /F` ile öldürülünce çocuk süreçler.

    Yardımcı (YARDIMCI_KAYNAGI) uygulamayı canlandırır: GERÇEK win_job
    koduyla çocuğu job'a atar. Çekirdek, yardımcı ölünce son job
    tutamacını kapatır ve KILL_ON_JOB_CLOSE işler.
    """

    @staticmethod
    def _hayatta(pid):
        """PID yaşıyor mu: OpenProcess + GetExitCodeProcess (STILL_ACTIVE).

        Çıkmakta olan sürecin çekirdek nesnesi tutamacı olan herkes için
        görünür kalır; yok olmuş süreç için OpenProcess başarısız olur.
        """
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int,
                                    ctypes.c_ulong]
        k32.GetExitCodeProcess.restype = ctypes.c_int
        k32.GetExitCodeProcess.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        # 0x1000: PROCESS_QUERY_LIMITED_INFORMATION
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        try:
            kod = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(kod)):
                return False
            return kod.value == 259              # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)

    @staticmethod
    def _oldur(pid):
        # Gerçek öldürme senaryosunun kendisi: taskkill /F, /T'siz (yalnız
        # ebeveyn; ağacın düşmesi job'un işi olmalı).
        return subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    def _yardimci(self, mod, tmp_path):
        bilgi = tmp_path / ("bilgi_%s.json" % mod)
        kaynak = tmp_path / ("yardimci_%s.py" % mod)
        kaynak.write_text(YARDIMCI_KAYNAGI, encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = _KOK + os.pathsep + env.get("PYTHONPATH", "")
        p = subprocess.Popen(
            [sys.executable, str(kaynak), mod, str(bilgi)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=_KOK, env=env)
        son = time.monotonic() + 60   # soğuk başlangıç: PyQt6 importu ağırdır
        while time.monotonic() < son:
            if bilgi.exists():
                try:
                    return p, json.loads(bilgi.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, ValueError):
                    pass              # yazma ortasında okuduk, tekrar dene
            assert p.poll() is None, "yardımcı beklenmedik öldü"
            time.sleep(0.1)
        p.kill()
        pytest.fail("yardımcı 60 sn içinde bilgi dosyası yazmadı")

    def test_JOBLU_cocuk_ebeveyn_olunce_oliyor(self, tmp_path):
        p, bilgi = self._yardimci("job", tmp_path)
        cocuk = bilgi["cocuk"]
        try:
            assert self._hayatta(cocuk), "çocuk hiç başlamadı"
            assert self._oldur(p.pid).returncode == 0, \
                "yardımcı öldürülemedi"
            son = time.monotonic() + 10
            while time.monotonic() < son and self._hayatta(cocuk):
                time.sleep(0.25)
            assert not self._hayatta(cocuk), (
                "job'a atanan çocuk (%s) ebeveyn ölünce yaşıyor "
                "(atanmis=%r); 2026-11-17'de gerçek exe'de ölçülen sahipsiz "
                "wsl.exe hâli sürüyor" % (cocuk, bilgi["atanmis"]))
        finally:
            self._oldur(p.pid)
            self._oldur(cocuk)

    def test_JOBSUZ_cocuk_yasiyor(self, tmp_path):
        """Denetim kolu: atama YOKSA çocuk ebeveyn ölümünden etkilenmez.

        Bu kol düşerse asıl kapıdaki ölüm job'tan değil, ölçümün kendisinden
        geliyordur (ör. başlatan ortam süreçleri kendi başına bağlıyor).
        """
        p, bilgi = self._yardimci("kontrol", tmp_path)
        cocuk = bilgi["cocuk"]
        try:
            assert bilgi["atanmis"] is None, "kontrol kolunda atama olmaz"
            assert self._hayatta(cocuk)
            assert self._oldur(p.pid).returncode == 0
            time.sleep(3.0)
            assert self._hayatta(cocuk), \
                "atama olmadan çocuk kendiliğinden öldü: ölçüm yöntemi bozuk"
        finally:
            self._oldur(p.pid)
            self._oldur(cocuk)
