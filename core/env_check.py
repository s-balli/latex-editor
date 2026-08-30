"""Ortam denetimi: derleme için gereken harici araçları kontrol eder.

Qt'süz saf fonksiyonlar; EnvDoctorDialog (desktop) doğrudan kullanır, web
backend'i ileride yeniden kullanabilir (log_parser/engine_detector deseni).

Tüm araçlar TEK subprocess sorgusuyla denetlenir: Windows'ta her wsl spawn
soğuk başlangıçta 1-3 sn sürer; araç başına ayrı çağrı 6-8 spawn demektir.
"""

import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass

# Denetlenen harici araçlar (derleme zincirinin tamamı)
TOOLS = ("lualatex", "pdflatex", "xelatex", "biber", "pandoc", "synctex", "pygmentize")

# Yoksun araca karşılık gelen Ubuntu/Debian paketi. xelatex önerisi
# engine_detector/derle.sh'tekiyle aynı (texlive-xetex).
APT_HINTS = {
    "lualatex": "texlive-luatex",
    "pdflatex": "texlive-latex-base",
    "xelatex": "texlive-xetex",
    "biber": "biber",
    "pandoc": "pandoc",
    "synctex": "texlive-binaries",
    "pygmentize": "python3-pygments",
}

# Eksikken satırda bağlam verilecek araçlar: minted kullanmayan kullanıcıya
# satırın listede neden durduğu anlaşılsın.
_TOOL_NOTES = {
    "pygmentize": "minted belgeleri için gerekli",
}

# WSL içinde tek seferde tüm araçların yolu: "ad=/yol" veya "ad=YOK" satırları
_WSL_PROBE = (
    "for t in " + " ".join(TOOLS) + "; do "
    'p=$(command -v "$t" 2>/dev/null) && echo "$t=$p" || echo "$t=YOK"; done'
)

# Derleme motorları: üçünün birden eksik olması "TeX Live hiç kurulu değil"
# anlamına gelir (tek motoru eksik olana tam kurulum önerilmez).
ENGINES = ("lualatex", "pdflatex", "xelatex")

# README'deki tek komutluk tam kurulum ile aynı liste. Motor başına minimal
# paketler derlemeyi başlatır ama ilk gerçek belgede texlive-latex-extra /
# texlive-lang-european (Türkçe heceleme) eksikliğiyle tekrar takılır; sıfır
# kurulumlu makinede doğrudan tam kurulum doğru öneri.
_FULL_INSTALL = (
    "sudo apt-get install texlive-base texlive-binaries texlive-latex-base "
    "texlive-latex-extra texlive-latex-recommended texlive-lang-european "
    "texlive-luatex texlive-xetex texlive-fonts-extra texlive-science "
    "texlive-bibtex-extra texlive-font-utils texlive-extra-utils biber "
    "texlive-publishers texlive-humanities texlive-pstricks "
    "python3-pygments pandoc"
)


@dataclass
class CheckResult:
    name: str              # kontrol adı ("WSL", "lualatex", ...)
    status: str            # "ok" | "missing" | "error" | "info"
    detail: str = ""       # yol / açıklama / sürüm bilgisi
    fix_hint: str = ""     # eksikse çözüm komutu (boş olabilir)


def _run(cmd: list[str], timeout: float = 20.0) -> tuple[int | None, str]:
    """argv-list komut çalıştır -> (exit kodu, stdout). Başlatılamazsa (None, neden)."""
    flags = 0
    if sys.platform == "win32":
        # Paketlenmiş GUI uygulamada konsol penceresi açılmasın
        flags = subprocess.CREATE_NO_WINDOW
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=flags)
        return r.returncode, (r.stdout or "").strip()
    except FileNotFoundError:
        return None, "wsl bulunamadı"
    except subprocess.SubprocessError as e:
        return None, str(e)


def _parse_tool_lines(out: str) -> dict[str, str]:
    """'lualatex=/usr/bin/lualatex\\npdflatex=YOK' -> {"lualatex": "/usr/bin/...",
    "pdflatex": ""} (YOK/boş yol = kurulu değil). Tanınmayan satırlar atlanır."""
    paths = {}
    for line in out.splitlines():
        if "=" in line:
            name, _, val = line.partition("=")
            name, val = name.strip(), val.strip()
            if name in TOOLS:
                paths[name] = "" if val == "YOK" else val
    return paths


def _tool_row(name: str, path: str) -> CheckResult:
    if path:
        return CheckResult(name, "ok", path)
    detail = "kurulu değil"
    if name in _TOOL_NOTES:
        detail += f" ({_TOOL_NOTES[name]})"
    return CheckResult(name, "missing", detail,
                       f"sudo apt-get install {APT_HINTS[name]}")


def _maybe_add_full_install_hint(results: list[CheckResult]) -> None:
    """Üç motorun hepsi eksikse sona tek komutluk tam kurulum önerisi ekle.

    Motor başına üç ayrı minimal komut yerine README'nin tam kurulumu
    önerilir; tek bir motoru eksik kullanıcıya dokunulmaz (minimal öneri
    doğrusu). WSL tamamen yok/çalışmıyorsa bu fonksiyon çağrılmaz: önce WSL
    kurulmalı, araç durumu henüz bilinmiyor.
    """
    by = {r.name: r for r in results}
    if all(by.get(e) is not None and by[e].status == "missing" for e in ENGINES):
        results.append(CheckResult(
            "TeX Live kurulumu", "info",
            "hiç motor kurulu değil; eksik paketleri tek tek kurmak yerine "
            "README'nin tam kurulumu önerilir",
            _FULL_INSTALL,
        ))


def run_checks(runner=None) -> list[CheckResult]:
    """Tüm ortam kontrollerini koş. runner(cmd) -> (rc, stdout) test enjeksiyonu."""
    runner = runner or _run
    results: list[CheckResult] = []

    # Bilgi satırı: raporun kendini tanıması için
    from core.version import VERSION
    results.append(CheckResult(
        "LaTeX Editor", "info",
        f"v{VERSION} | {platform.system()} {platform.release()}"
        f" | Python {platform.python_version()}",
    ))

    if sys.platform == "win32":
        rc, out = runner(["wsl", "-e", "sh", "-c", _WSL_PROBE])
        if rc is None:
            results.append(CheckResult(
                "WSL", "missing", out,
                "wsl --install  (yönetici PowerShell; ardından yeniden başlat)",
            ))
            # WSL yokken araçlar denetlenemez; yanlış "kurulu değil" yerine
            # açıkça bilinmiyor işaretle
            results.extend(
                CheckResult(t, "error", "WSL olmadığından denetlenemedi",
                            f"sudo apt-get install {APT_HINTS[t]}")
                for t in TOOLS)
            return results
        if rc != 0:
            results.append(CheckResult(
                "WSL", "missing",
                "çalıştırılamadı (dağıtım kurulu olmayabilir)",
                "wsl --install",
            ))
            results.extend(
                CheckResult(t, "error", "WSL çalışmadığından denetlenemedi",
                            f"sudo apt-get install {APT_HINTS[t]}")
                for t in TOOLS)
            return results
        results.append(CheckResult("WSL", "ok", "çalışıyor"))
        paths = _parse_tool_lines(out)
        results.extend(_tool_row(t, paths.get(t, "")) for t in TOOLS)
    else:
        # Yerel platformda WSL satırı yok (bilgi taşımaz); subprocess'a da
        # gerek yok: which PATH taraması yapar.
        paths = {t: (shutil.which(t) or "") for t in TOOLS}
        results.extend(_tool_row(t, paths[t]) for t in TOOLS)

    _maybe_add_full_install_hint(results)
    return results


def report_text(results: list[CheckResult]) -> str:
    """Panoya kopyalanacak düz metin rapor (hata bildirimlerine eklemek için)."""
    marks = {"ok": "[OK]  ", "missing": "[YOK] ", "error": "[?]   ", "info": "[i]   "}
    lines = []
    for r in results:
        line = f"{marks.get(r.status, '[?]')} {r.name}"
        if r.detail:
            line += f": {r.detail}"
        if r.fix_hint and r.status != "ok":
            line += f"  ({r.fix_hint})"
        lines.append(line)
    return "\n".join(lines)
