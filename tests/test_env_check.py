"""core.env_check — ortam denetimi kontrolleri (Qt'süz) + dialog duman testi."""

import sys
import time

import pytest

from core import env_check
from core.env_check import TOOLS, _parse_tool_lines, report_text, run_checks


def _all_ok_out():
    return "\n".join(f"{t}=/usr/bin/{t}" for t in TOOLS)


def _mixed_out():
    return "\n".join(
        f"{t}=/usr/bin/{t}" if t != "xelatex" else "xelatex=YOK" for t in TOOLS)


# --- Çözümleme ---


def test_parse_tool_lines_yoksuz_ve_taninmayan_satirlar():
    d = _parse_tool_lines("lualatex=/usr/bin/lualatex\njunk=hmm\npdflatex=YOK\n")
    assert d == {"lualatex": "/usr/bin/lualatex", "pdflatex": ""}


# --- Windows (WSL) kolu ---


def test_win32_wsl_yoksa_araclar_denetlenemez(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    results = run_checks(runner=lambda cmd: (None, "wsl bulunamadı"))

    by = {r.name: r for r in results}
    assert by["WSL"].status == "missing"
    assert "wsl --install" in by["WSL"].fix_hint
    tools = [r for r in results if r.name in TOOLS]
    assert len(tools) == len(TOOLS)
    assert all(t.status == "error" for t in tools)


def test_win32_wsl_calismiyorsa_ayni_sekilde_korunur(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    results = run_checks(runner=lambda cmd: (1, ""))
    by = {r.name: r for r in results}
    assert by["WSL"].status == "missing"
    assert all(r.status == "error" for r in results if r.name in TOOLS)


def test_win32_wsl_probu_tek_cagriyla_araclari_getirir(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    seen = []

    def fake_runner(cmd):
        seen.append(cmd)
        return 0, _mixed_out()

    results = run_checks(runner=fake_runner)

    # Tek spawn: WSL'de araç başına ayrı çağrı soğuk başlangıçta çok pahalı
    assert len(seen) == 1
    assert seen[0][:3] == ["wsl", "-e", "sh"]

    by = {r.name: r for r in results}
    assert by["WSL"].status == "ok"
    assert by["lualatex"].status == "ok"
    assert by["lualatex"].detail == "/usr/bin/lualatex"
    assert by["xelatex"].status == "missing"
    assert "texlive-xetex" in by["xelatex"].fix_hint


# --- Yerel (Linux) kolu ---


def test_native_which_kullanir(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(env_check.shutil, "which",
                        lambda t: f"/usr/bin/{t}" if t != "biber" else None)

    results = run_checks()
    by = {r.name: r for r in results}
    assert by["WSL"].status == "info"
    assert by["biber"].status == "missing"
    assert "sudo apt-get install biber" in by["biber"].fix_hint
    assert by["synctex"].status == "ok"


def test_pygmentize_satiri_minted_baglami_tasir(monkeypatch):
    """pygmentize eksikse satır minted bağlamını ve python3-pygments
    önerisini taşımeli (minted kullanmayan kullanıcıya satır açıklaması)."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(env_check.shutil, "which",
                        lambda t: f"/usr/bin/{t}" if t != "pygmentize" else None)

    by = {r.name: r for r in run_checks()}
    assert by["pygmentize"].status == "missing"
    assert "minted belgeleri için gerekli" in by["pygmentize"].detail
    assert "python3-pygments" in by["pygmentize"].fix_hint


# --- Rapor ---


def test_report_text_tum_araclari_icerir(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(env_check.shutil, "which", lambda t: f"/usr/bin/{t}")

    text = report_text(run_checks())
    for t in TOOLS:
        assert t in text
    assert "[OK]" in text and "[YOK]" not in text


def test_report_text_yoksun_arac_ipucu_tasir(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(env_check.shutil, "which", lambda t: None)

    text = report_text(run_checks())
    assert text.count("[YOK]") == len(TOOLS)
    assert "texlive-xetex" in text


# --- Dialog (GUI duman testi) ---


def test_dialog_sonuclari_render_eder(monkeypatch):
    try:
        from PyQt6.QtWidgets import QApplication
        from gui.env_doctor import EnvDoctorDialog
        from gui.theme import THEMES
        from core.env_check import CheckResult
    except ImportError:  # pragma: no cover
        pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)

    qapp = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "core.env_check.run_checks",
        lambda: [CheckResult("LaTeX Editor", "info", "v1.0.11"),
                 CheckResult("lualatex", "ok", "/usr/bin/lualatex"),
                 CheckResult("xelatex", "missing", "kurulu değil",
                             "sudo apt-get install texlive-xetex")])

    dlg = EnvDoctorDialog(theme=THEMES["dark"])
    # Arka plan thread'i bitip sinyali UI tarafına bırakana kadar dön
    for _ in range(200):
        qapp.processEvents()
        if dlg._results is not None:
            break
        time.sleep(0.02)

    assert dlg._results is not None
    text = dlg._view.toPlainText()
    assert "lualatex" in text
    assert "xelatex" in text
    assert "texlive-xetex" in text          # düzeltme ipucu satırda
    assert dlg._copy_btn.isEnabled() and dlg._rerun_btn.isEnabled()
    dlg.deleteLater()
