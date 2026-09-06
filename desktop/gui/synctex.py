"""SyncTeX bridge — ileri/geri arama via synctex CLI."""

import subprocess
import sys
from dataclasses import dataclass

from core.log import get_logger
from core.paths import clean_child_env, windows_to_wsl, wsl_to_windows

_logger = get_logger("synctex")

_PLATFORM = sys.platform

# synctex çağrılarının zaman aşımı. 3 sn'ydi ve DAR bir bütçeydi: sıcak WSL'de
# tüm çağrı ~85 ms sürüyor (ölçüldü — 181 sayfalık belgede de aynı, maliyetin
# tamamı `wsl -e` süreç açılışı, synctex ayrıştırması ihmal edilebilir), yani
# 3 sn aslında SOĞUK WSL başlangıcı için ayrılmış bir bütçe. Bu makinedeki
# dağıtım systemd + snapd + unattended-upgrades ile açılıyor; soğuk başlangıç
# saniyeler sürebiliyor ve bütçeyi aşarsa ileri-arama sessizce düşüyor
# (yalnız log'a warning). Kullanıcının SyncTeX'i ilk denediği an ise tam da
# bilgisayarı yeni açtığı andır — hatanın en olası olduğu yer en görünür yer.
# Uzatmanın bedeli yok: bu çağrılar SyncTexWorker thread'inde koşuyor, UI
# beklemiyor; 15 sn yalnızca gerçekten asılmış bir sürecin warning'ini geciktirir.
_ZAMAN_ASIMI = 15

# Windows'ta konsol penceresi açılmasını engelle
_SUBPROCESS_FLAGS = 0
_SI = None
if _PLATFORM == "win32":
    _SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW
    _SI = subprocess.STARTUPINFO()
    _SI.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _SI.wShowWindow = 0  # SW_HIDE


class _AracYok:
    """`synctex` ÇALIŞTIRILAMADI işareti; `None` "koştu, eşleşme yok" demek.

    Üç durum vardı ve üçü de `None` dönüyordu, yani kullanıcı üçünde de
    "SyncTeX: Eşleşme bulunamadı" görüyordu. ÖLÇÜLDÜ (2026-09-06):

        synctex kurulu değil (native)   FileNotFoundError
        WSL var, TeX Live yok           çıkış 127, stderr "command not found"
        koştu, o noktada eşleşme yok    çıkış 255, stdout'ta sürüm başlığı

    İlk ikisinde kullanıcı konumu yanlış sanıp aynı yeri tekrar deniyordu;
    yapması gereken TeX Live kurmaktı. Aynı ders `.synctex.gz` denetiminde
    bir kez alınmıştı (bkz. `synctex_ops._on_reverse_search` yorumu).

    FALSY: `if result:` yazan çağıranlar bugünkü davranışı sürdürsün,
    ayrımı isteyen `result is ARAC_YOK` diye sorsun. Böylece işaret bir yerde
    unutulursa sessizce "eşleşme var" sanılmıyor.
    """

    __slots__ = ()

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:                       # pragma: no cover
        return "ARAC_YOK"


ARAC_YOK = _AracYok()

# `wsl -e <komut>` komutu bulamazsa kabuk 127 döndürüyor (ölçüldü). synctex'in
# kendi "eşleşme yok" çıkışı 255; ikisi karışmıyor.
_KOMUT_YOK = 127


@dataclass
class ForwardResult:
    page: int
    x: float
    y: float
    left: float = 0.0   # h alanı — satır sol kenarı
    width: float = 0.0   # W alanı — satır genişliği
    height: float = 0.0  # H alanı — metin yüksekliği


@dataclass
class ReverseResult:
    file_path: str
    line: int
    col: int = 0


def _parse_forward(output: str) -> ForwardResult | None:
    # Birden fazla sonuç var — ilkini al (en yakın eşleşme)
    page = x = y = left = width = height = None
    for ln in output.split('\n'):
        ln = ln.strip()
        if ln.startswith("Page:"):
            if page is not None and x is not None and y is not None:
                break  # İlk sonuç tamam, döngüden çık
            page = int(ln.split(":")[1].strip())
        elif ln.startswith("x:"):
            x = float(ln.split(":")[1].strip())
        elif ln.startswith("y:"):
            y = float(ln.split(":")[1].strip())
        elif ln.startswith("h:"):
            left = float(ln.split(":")[1].strip())
        elif ln.startswith("W:"):
            width = float(ln.split(":")[1].strip())
        elif ln.startswith("H:"):
            height = float(ln.split(":")[1].strip())
    if page is not None and x is not None and y is not None:
        return ForwardResult(page=page, x=x, y=y,
                             left=left or 0.0, width=width or 0.0, height=height or 0.0)
    return None


def _parse_reverse(output: str) -> ReverseResult | None:
    input_file = line = col = None
    for ln in output.split('\n'):
        ln = ln.strip()
        if ln.startswith("Input:"):
            input_file = ln.split(":", 1)[1].strip()
        elif ln.startswith("Line:"):
            line = int(ln.split(":")[1].strip())
        elif ln.startswith("Column:"):
            c = ln.split(":")[1].strip()
            col = int(c) if c != "-1" else 0
    if input_file and line is not None:
        return ReverseResult(file_path=input_file, line=line, col=col or 0)
    return None


def forward_search(tex_path: str, line: int, col: int, pdf_path: str,
                   synctex_dir: str = "") -> ForwardResult | None:
    if _PLATFORM == "win32":
        return _forward_wsl(tex_path, line, col, pdf_path, synctex_dir)
    return _forward_native(tex_path, line, col, pdf_path, synctex_dir)


def reverse_search(page: int, x: float, y: float, pdf_path: str,
                   synctex_dir: str = "") -> ReverseResult | None:
    if _PLATFORM == "win32":
        return _reverse_wsl(page, x, y, pdf_path, synctex_dir)
    return _reverse_native(page, x, y, pdf_path, synctex_dir)


# Bu dosyadaki dört subprocess.run çağrısı da encoding="utf-8" GEÇMEK ZORUNDA.
# text=True + encoding yoksa Python locale.getpreferredencoding() kullanır;
# Türkçe Windows'ta bu cp1254'tür. Proje yolu Türkçe karakter içerdiğinde
# (C:\Users\Şerif\... çok yaygın) synctex çıktısındaki yol UTF-8 gelir ve
# cp1254'te tanımsız bayta denk gelir: 'Ş' = C5 9E, cp1254'te 0x9E YOK.
# Çözme hatası OKUMA THREAD'inde oluştuğu için run() istisna FIRLATMAZ —
# r.stdout None olur, returncode 0 kalır, guard'dan geçer ve _parse_*(None)
# AttributeError verir. except kolu onu yakalamıyor; synctex_worker'ın geniş
# except'i yutuyor ve SyncTeX Türkçe yollu projede sessizce hiç çalışmıyordu.
# 'r.stdout is None' denetimi ikinci savunma hattı: encoding sorunu dışında
# bir nedenle de None gelirse sessiz AttributeError yerine düzgün None dönsün.


def _forward_wsl(tex_path: str, line: int, col: int, pdf_path: str,
                synctex_dir: str = "") -> ForwardResult | None:
    cmd = ["wsl", "-e", "synctex", "view",
           "-i", f"{line}:{col}:{windows_to_wsl(tex_path)}",
           "-o", windows_to_wsl(pdf_path)]
    if synctex_dir:
        cmd += ["-d", windows_to_wsl(synctex_dir)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=_ZAMAN_ASIMI,
                           startupinfo=_SI, creationflags=_SUBPROCESS_FLAGS)
        if r.returncode == _KOMUT_YOK:
            return ARAC_YOK
        if r.returncode != 0 or r.stdout is None:
            return None
        return _parse_forward(r.stdout)
    except subprocess.TimeoutExpired as e:
        _logger.warning("SyncTeX forward (WSL) zaman aşımı: %s:%d (%s)", tex_path, line, e)
        return None
    except (FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX forward (WSL) çalıştırılamadı: %s:%d (%s)", tex_path, line, e)
        return ARAC_YOK


def _forward_native(tex_path: str, line: int, col: int, pdf_path: str,
                    synctex_dir: str = "") -> ForwardResult | None:
    cmd = ["synctex", "view",
           "-i", f"{line}:{col}:{tex_path}",
           "-o", pdf_path]
    if synctex_dir:
        cmd += ["-d", synctex_dir]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=_ZAMAN_ASIMI, env=clean_child_env())
        if r.returncode == _KOMUT_YOK:
            return ARAC_YOK
        if r.returncode != 0 or r.stdout is None:
            return None
        return _parse_forward(r.stdout)
    except subprocess.TimeoutExpired as e:
        _logger.warning("SyncTeX forward (native) zaman aşımı: %s:%d (%s)", tex_path, line, e)
        return None
    except (FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX forward (native) çalıştırılamadı: %s:%d (%s)", tex_path, line, e)
        return ARAC_YOK


def _reverse_wsl(page: int, x: float, y: float, pdf_path: str,
                synctex_dir: str = "") -> ReverseResult | None:
    wsl_pdf = windows_to_wsl(pdf_path)
    cmd = ["wsl", "-e", "synctex", "edit",
           "-o", f"{page}:{int(x)}:{int(y)}:{wsl_pdf}"]
    if synctex_dir:
        cmd += ["-d", windows_to_wsl(synctex_dir)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=_ZAMAN_ASIMI,
                           startupinfo=_SI, creationflags=_SUBPROCESS_FLAGS)
        if r.returncode == _KOMUT_YOK:
            return ARAC_YOK
        if r.returncode != 0 or r.stdout is None:
            return None
        parsed = _parse_reverse(r.stdout)
        if parsed:
            parsed.file_path = wsl_to_windows(parsed.file_path)
        return parsed
    except subprocess.TimeoutExpired as e:
        _logger.warning("SyncTeX reverse (WSL) zaman aşımı: sayfa %d (%s)", page, e)
        return None
    except (FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX reverse (WSL) çalıştırılamadı: sayfa %d (%s)", page, e)
        return ARAC_YOK


def _reverse_native(page: int, x: float, y: float, pdf_path: str,
                    synctex_dir: str = "") -> ReverseResult | None:
    cmd = ["synctex", "edit",
           "-o", f"{page}:{int(x)}:{int(y)}:{pdf_path}"]
    if synctex_dir:
        cmd += ["-d", synctex_dir]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=_ZAMAN_ASIMI, env=clean_child_env())
        if r.returncode == _KOMUT_YOK:
            return ARAC_YOK
        if r.returncode != 0 or r.stdout is None:
            return None
        return _parse_reverse(r.stdout)
    except subprocess.TimeoutExpired as e:
        _logger.warning("SyncTeX reverse (native) zaman aşımı: sayfa %d (%s)", page, e)
        return None
    except (FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX reverse (native) çalıştırılamadı: sayfa %d (%s)", page, e)
        return ARAC_YOK
