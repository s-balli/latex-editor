r"""derle.sh bekçisi: uygulama ölünce derleme sahipsiz kalmasın.

ÖLÇÜLDÜ (2026-11-17, WSLg, kaynaktan çalışan uygulama, sonsuz döngüye giren
belge): derleme sürerken uygulama `kill -9` ile öldürülünce `pdflatex`
sahipsiz kaldı, %100 CPU ile 74+ sn koştu ve kendiliğinden durmadı. Zaman
aşımı zamanlayıcısı uygulamayla birlikte ölüyor; derle.sh'te süre sınırı
yok. Temiz kapanış, Durdur ve zaman aşımı `_sureci_oldur` ile ağacı zaten
öldürüyor; eksik olan yalnız uygulamanın ÇÖKMESİ/ÖLDÜRÜLMESİ.

Gerçek TeX GEREKMİYOR: PATH'in başına konan sahte `pdflatex` motoru
`exec sleep 300` ile derle.sh'in motoru nasıl çağırdığını taklit ediyor
(derle.sh motoru `$(...)` ikamesinin alt kabuğunda koşuyor, bkz.
`compiler._sureci_oldur` belge dizisi).

Yardımcı ebeveyn (YARDIMCI_KOD) uygulamanın rolünü oynuyor: derle.sh'i
YENİ OTURUMDA (QProcess'in CreateNewSession'ı gibi) ve
`LATEX_EDITOR_PID=<kendi pid>` ile başlatıyor; test ebeveyni SIGKILL ile
öldürüyor. Her bekleme üst sınırlı; finally blokları kalan her şeyi
süreç grubunu öldürerek temizliyor.
"""

import os
import signal
import subprocess
import sys
import time

import pytest

from tests.kabuk import calisan_bash

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "core", "derle.sh")
BASH = calisan_bash()

_ATLAMA = (
    "çalışan bash yok" if not BASH
    else "Windows'ta süreç grubu/oturum yok; bekçi yerli yol" if sys.platform == "win32"
    else "")
pytestmark = pytest.mark.skipif(bool(_ATLAMA), reason=_ATLAMA)

# Uygulamanın rolünü oynayan yardımcı süreç: kendi PID'ini basar, derle.sh'i
# yeni oturumda başlatır, derle.sh'in PID'ini basar ve bekler. BEKCI_PID_VER
# verilirse LATEX_EDITOR_PID'i de koyar (compiler._start_native gibi).
# p.wait() QProcess'in hasat davranışını taklit ediyor: biten çocuk zombi
# olarak kalmaz. Bekçinin ölçütü `kill -0` ve zombi sürece de başarılı
# döner; hasatsız derle.sh bittikten sonra bile yaşıyor görünürdü (gerçek
# uygulamada QProcess çocukları hasat ediyor).
YARDIMCI_KOD = (
    "import os, subprocess, sys, time\n"
    "print(os.getpid(), flush=True)\n"
    "ortam = dict(os.environ)\n"
    "if os.environ.get('BEKCI_PID_VER'):\n"
    "    ortam['LATEX_EDITOR_PID'] = str(os.getpid())\n"
    "p = subprocess.Popen(sys.argv[1:], start_new_session=True, env=ortam,\n"
    "                     stdout=subprocess.DEVNULL,\n"
    "                     stderr=subprocess.DEVNULL)\n"
    "print(p.pid, flush=True)\n"
    "p.wait()\n"
    "time.sleep(300)\n"
)


def _sahte_motor(bin_dizini, sure):
    """PATH'in başına konacak sahte pdflatex: PID'ini bildirir, uyur.

    `exec sleep` sayesinde motor süreci uykunun KENDİSİ olur: bekçi grubu
    öldürmese uyku 300 sn sürer, yani "motor yaşıyor" ölçülebilir.
    """
    motor = bin_dizini / "pdflatex"
    motor.write_text('#!/bin/sh\necho $$ > "$MOTOR_PID_DOSYASI"\n'
                     'exec sleep %d\n' % sure, encoding="utf-8")
    motor.chmod(0o755)
    return motor


def _bekle(kosul, sure, adim=0.2):
    """kosul() doğru olana kadar en çok `sure` sn bekle; sonucu döndür."""
    son = time.monotonic() + sure
    while True:
        try:
            if kosul():
                return True
        except OSError:
            pass
        if time.monotonic() >= son:
            return False
        time.sleep(adim)


def _pid_dosyasi_bekle(dosya, sure=30):
    son = time.monotonic() + sure
    while time.monotonic() < son:
        try:
            return int(dosya.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            time.sleep(0.2)
    raise AssertionError("sahte motor %s sn içinde başlamadı" % sure)


def _yasiyor(pid):
    """Süreç yaşıyor mu? Zombi (ps durumu Z) ölü sayılır: kill -0 zombide
    başarılı döner, grubun bittiğini göstermez."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    r = subprocess.run(["ps", "-o", "state=", "-p", str(pid)],
                       capture_output=True, text=True, encoding="utf-8")
    return not r.stdout.strip().startswith("Z")


def _ps_satirlari(*alanlar):
    args = ["ps", "-ax"]
    for alan in alanlar:
        args += ["-o", alan]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    return [satir.split(None, 1) for satir in r.stdout.splitlines() if satir.strip()]


def _grup_uyeleri(pgid):
    """Süreç grubunun zombi olmayan üyelerinin args satırları."""
    uyeler = []
    for parca in _ps_satirlari("pgid=", "state=", "args="):
        if len(parca) < 2 or parca[0] != str(pgid) or parca[1].startswith("Z"):
            continue
        # state= tek harf; args= kalanı
        satir = parca[1].split(None, 1)
        uyeler.append(satir[1] if len(satir) > 1 else "")
    return uyeler


def _grupta_bekci_uykusu_var(pgid):
    """Bekçinin `sleep 2` uykusu bu grupta görünüyor mu?

    Bekçi uykuyu kesintisiz, ~0 boşlukla yineliyor; tek bir ps görüntüsü
    bile onu büyük olasılıkla yakalar, çağıran taraf üst sınırlı döngüde
    sorar. Motorunki `sleep 300`: karışmıyorlar.
    """
    return any(u.strip() == "sleep 2" for u in _grup_uyeleri(pgid))


class TestBekci:
    def _baslat(self, tmp_path, motor_sure=300, bekci_pid_ver=True):
        """Yardımcı ebeveyn + onun yeni oturumda başlattığı derle.sh.

        Dönüş: (yardımcı Popen, ebeveyn_pid, derle_pid). TMPDIR testin
        dizinine alınıyor: gerçek /tmp'deki latex-editor.* dizinlerine
        dokunulmasın (eski_gecicileri_supur).
        """
        taban = tmp_path / "taban"
        taban.mkdir(exist_ok=True)
        bin_dizini = tmp_path / "bin"
        bin_dizini.mkdir(exist_ok=True)
        _sahte_motor(bin_dizini, motor_sure)
        tex = tmp_path / "a.tex"
        tex.write_text("x", encoding="utf-8")
        env = dict(os.environ,
                   PATH="%s:%s" % (bin_dizini, os.environ["PATH"]),
                   TMPDIR=str(taban),
                   MOTOR_PID_DOSYASI=str(tmp_path / "motor.pid"))
        if bekci_pid_ver:
            env["BEKCI_PID_VER"] = "1"
        else:
            env.pop("BEKCI_PID_VER", None)
            env.pop("LATEX_EDITOR_PID", None)
        yardimci = subprocess.Popen(
            [sys.executable, "-c", YARDIMCI_KOD,
             BASH, SCRIPT, str(tex), "--pdflatex"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        try:
            ebeveyn = int(yardimci.stdout.readline().strip())
            derle = int(yardimci.stdout.readline().strip())
        except (ValueError, OSError):
            yardimci.kill()
            yardimci.wait()
            raise
        return yardimci, ebeveyn, derle

    @staticmethod
    def _temizle(yardimci, ebeveyn, derle):
        """Kalan her neyse öldür: önce yardımcı ebeveyn, sonra derle grubu."""
        try:
            os.kill(ebeveyn, signal.SIGKILL)
        except OSError:
            pass
        if yardimci.poll() is None:
            try:
                yardimci.wait(timeout=10)
            except subprocess.TimeoutExpired:
                yardimci.kill()
                yardimci.wait()
        try:
            os.killpg(derle, signal.SIGKILL)
        except OSError:
            pass

    def test_BEKCI_doguyor(self, tmp_path):
        """Değişken verildiyse bekçi gerçekten doğmalı: grubunda bekçinin
        `sleep 2` uykusu görünmeli. Bekçi hiç doğmazsa kalan kapılar bu
        kusuru sessizce geçerdi."""
        yardimci, ebeveyn, derle = self._baslat(tmp_path)
        try:
            _pid_dosyasi_bekle(tmp_path / "motor.pid")
            assert _bekle(lambda: _grupta_bekci_uykusu_var(derle), 15), \
                "grupta bekçi uykusu (sleep 2) yok: bekçi doğmuyor"
        finally:
            self._temizle(yardimci, ebeveyn, derle)

    def test_EBEBEYN_olunce_motor_ve_grup_bitiyor(self, tmp_path):
        """Asıl kusur: ebeveyn (uygulama) SIGKILL ile ölünce sahte motor ve
        derle.sh'in süreci birkaç saniye içinde ölmeli. Düzeltmesiz kodda
        motor yaşıyor ve %100 CPU ile koşmaya devam ediyor.

        Ebeveyn öldürüldükten sonra HASAT edilmeli (wait): bekçinin ölçütü
        `kill -0` ve o zombi sürece de başarılı döner; hasatsız ebeveyn
        hâlâ yaşıyor görünür. Gerçek uygulamada ebeveyni (kabuk, masaüstü
        başlatıcısı) işletim sistemi hasat ediyor."""
        yardimci, ebeveyn, derle = self._baslat(tmp_path)
        try:
            motor = _pid_dosyasi_bekle(tmp_path / "motor.pid")
            assert _yasiyor(motor), "kurgu bozuk: sahte motor koşmuyor"

            os.kill(ebeveyn, signal.SIGKILL)
            assert yardimci.wait(timeout=10) == -signal.SIGKILL

            assert _bekle(lambda: not _yasiyor(motor), 15), \
                "ebeveyn öldü, motor yaşıyor: derleme sahipsiz kaldı"
            assert _bekle(lambda: not _yasiyor(derle), 15), \
                "ebeveyn öldü, derle.sh yaşıyor"
            assert _bekle(lambda: _grup_uyeleri(derle) == [], 15), \
                "grupta süreç kaldı: %s" % _grup_uyeleri(derle)
        finally:
            self._temizle(yardimci, ebeveyn, derle)

    def test_DEGISKEN_YOKKEN_bekci_devreye_girmiyor(self, tmp_path):
        """Değişken yoksa (kullanıcı betiği terminalden çalıştırıyor)
        davranış birebir eskisi gibi: ebeveyn ölse de motor koşmaya devam
        eder, testin kendisi temizler."""
        yardimci, ebeveyn, derle = self._baslat(tmp_path, bekci_pid_ver=False)
        try:
            motor = _pid_dosyasi_bekle(tmp_path / "motor.pid")
            assert _yasiyor(motor), "kurgu bozuk: sahte motor koşmuyor"
            # Bekçi doğmamış olmalı: değişkensiz koşuda grup içinde bekçi
            # uykusu görünmesi zaten kusurdu.
            son = time.monotonic() + 3
            while time.monotonic() < son:
                assert not _grupta_bekci_uykusu_var(derle), \
                    "LATEX_EDITOR_PID yokken bekçi doğdu"
                time.sleep(0.5)

            os.kill(ebeveyn, signal.SIGKILL)
            yardimci.wait(timeout=10)
            # İki denetim aralığından fazla bekle: bekçi olsaydı çoktan
            # vurmuş olurdu.
            time.sleep(5)
            assert _yasiyor(derle), "değişken yokken derle.sh öldü"
            assert _yasiyor(motor), \
                "değişken yokken motor öldü: eski davranış bozuldu"
        finally:
            self._temizle(yardimci, ebeveyn, derle)

    def test_NORMAL_BITISTE_arkada_bekci_kalmiyor(self, tmp_path):
        """Motor hemen çıkınca derle.sh normal biter; arkada bekçi (ya da
        onun uykusu) kalmamalı. Bekçi betiğin kendisini de izliyor: betik
        ölünce `kill -0` boşar ve bekçi en geç bir aralık içinde çıkar."""
        yardimci, ebeveyn, derle = self._baslat(tmp_path, motor_sure=0)
        try:
            # derle.sh normal yoldan bitmeli (motor PDF üretmedi: hata
            # yolu, yine de NORMAL bitiş).
            assert _bekle(lambda: not _yasiyor(derle), 30), \
                "derle.sh zamanında bitmedi"
            # Bekçi bir denetim aralığı içinde kendiliğinden çıkmalı.
            assert _bekle(lambda: _grup_uyeleri(derle) == [], 8), \
                "derle.sh bitti ama grupta süreç kaldı: %s" \
                % _grup_uyeleri(derle)
        finally:
            self._temizle(yardimci, ebeveyn, derle)
