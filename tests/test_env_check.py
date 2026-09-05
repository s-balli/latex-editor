"""core.env_check — ortam denetimi kontrolleri (Qt'süz) + dialog duman testi."""

import sys
import time

import pytest

from core import env_check
from core.env_check import (ZAMAN_ASIMI, TOOLS, _parse_tool_lines,
                            report_text, run_checks)


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


def test_iki_WSL_durumu_AYRI_komut_veriyor(monkeypatch):
    """"wsl yok" ile "dagitim yok" ayni sey degil.

    Ikisine de `wsl --install` deniyordu. Ikinci durumda wsl'in KENDISI
    kurulu; o komut "zaten kurulu" deyip cikiyor ve kullanici tikaniyor.
    Eksik olan dagitim, dolayisiyla `-d Ubuntu` gerekiyor.
    """
    monkeypatch.setattr(sys, "platform", "win32")

    yok = {r.name: r for r in
           run_checks(runner=lambda cmd: (None, "wsl bulunamadı"))}
    dagitimsiz = {r.name: r for r in run_checks(runner=lambda cmd: (1, ""))}

    assert "-d Ubuntu" not in yok["WSL"].fix_hint
    assert "-d Ubuntu" in dagitimsiz["WSL"].fix_hint
    assert yok["WSL"].fix_hint != dagitimsiz["WSL"].fix_hint


def test_WSL_eksikken_SONRAKI_ADIM_da_soyleniyor(monkeypatch):
    """WSL kurulunca is bitmiyor: taze dagitimda TeX de yok.

    Eskiden yedi ayri `apt-get install` satiri veriliyordu ama tek komutluk
    tam kurulum hic gosterilmiyordu; gerekcesi "WSL yokken arac durumu
    bilinmiyor" idi. Dogru ama eksik: sonraki adim her hâlukârda TeX Live.

    "info" olarak ekleniyor, "missing" degil: arac durumu gercekten
    bilinmiyor, bu bir tespit degil yol tarifi.
    """
    monkeypatch.setattr(sys, "platform", "win32")
    for runner in (lambda cmd: (None, "wsl bulunamadı"), lambda cmd: (1, "")):
        by = {r.name: r for r in run_checks(runner=runner)}
        adim = by.get("Sonraki adım")
        assert adim is not None, "sonraki adım satırı yok"
        assert adim.status == "info"
        assert "texlive-base" in adim.fix_hint
        assert "apt-get update" in adim.fix_hint


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
    assert "WSL" not in by            # yerel Linux'ta WSL satırı olmamalı
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


def test_tum_motorlar_eksikse_tam_kurulum_onerisi(monkeypatch):
    """Üç motorun hepsi yoksa sonda tek komutluk tam kurulum önerilmeli."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(env_check.shutil, "which",
                        lambda t: "" if t in env_check.ENGINES else f"/usr/bin/{t}")

    results = run_checks()
    tail = [r for r in results if r.name == "TeX Live kurulumu"]
    assert tail, "tam kurulum önerisi satırı yok: " + repr([r.name for r in results])
    row = tail[0]
    assert row is results[-1]                     # en sonda, satırları ezmeden
    for paket in ("texlive-latex-extra", "texlive-lang-european",
                  "python3-pygments", "pandoc"):
        assert paket in row.fix_hint


def test_tek_motor_eksikse_tam_kurulum_onerisi_yok(monkeypatch):
    """Tek motoru eksik kullanıcıya minimal öneri yeter; tam kurulum gürültü."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(env_check.shutil, "which",
                        lambda t: "" if t == "xelatex" else f"/usr/bin/{t}")

    results = run_checks()
    assert not [r for r in results if r.name == "TeX Live kurulumu"]
    by = {r.name: r for r in results}
    assert "texlive-xetex" in by["xelatex"].fix_hint   # minimal öneri duruyor


# --- Zaman aşımı (WSL var ama yanıt vermiyor) ---


def test_zaman_asimi_WSL_YOK_diye_raporlanmiyor(monkeypatch):
    """Yanıt vermeyen WSL "kurulu değil" sayılmamalı.

    ``subprocess.TimeoutExpired``, ``subprocess.SubprocessError`` ALT SINIFI.
    _run yalnız SubprocessError yakalayıp (None, ...) döndürdüğü için
    run_checks bunu "WSL yok" okuyor ve `wsl --install` öneriyordu. O komut
    wsl'in kurulu olduğu makinede "zaten kurulu" deyip çıkıyor; kullanıcı
    tıkanıyor. Aynı ders `rc != 0` dalında zaten öğrenilmişti.
    """
    monkeypatch.setattr(sys, "platform", "win32")
    by = {r.name: r for r in run_checks(runner=lambda cmd: (ZAMAN_ASIMI, ""))}

    assert by["WSL"].status == "error"            # "missing" DEĞİL
    assert "yanıt vermedi" in by["WSL"].detail
    assert "wsl --shutdown" in by["WSL"].fix_hint
    assert "wsl --install" not in by["WSL"].fix_hint
    assert all(by[t].status == "error" for t in TOOLS)


def test_zaman_asimi_ham_argv_dokumu_sizdirmiyor(monkeypatch):
    """str(TimeoutExpired) kaçışlı bir Python argv listesi; arayüze sızmamalı."""
    monkeypatch.setattr(sys, "platform", "win32")
    by = {r.name: r for r in run_checks(runner=lambda cmd: (ZAMAN_ASIMI, ""))}
    assert "Command '[" not in by["WSL"].detail
    assert "\\\\" not in by["WSL"].detail


def test_zaman_asiminda_TeX_Live_gurultusu_eklenmiyor(monkeypatch):
    """WSL çalışıyor, yalnız yavaş: araç durumu bilinmiyor.

    "Sonraki adım" (WSL kurulumundan sonraki TeX Live) ve "TeX Live kurulumu"
    satırları burada yol tarifi değil gürültü olurdu.
    """
    monkeypatch.setattr(sys, "platform", "win32")
    adlar = [r.name for r in run_checks(runner=lambda cmd: (ZAMAN_ASIMI, ""))]
    assert "Sonraki adım" not in adlar
    assert "TeX Live kurulumu" not in adlar


def test_uc_WSL_durumu_UC_AYRI_komut_veriyor(monkeypatch):
    """wsl yok / dağıtım yok / yanıt yok: üçü ayrı teşhis, ayrı komut."""
    monkeypatch.setattr(sys, "platform", "win32")
    yok = {r.name: r for r in
           run_checks(runner=lambda cmd: (None, "wsl bulunamadı"))}["WSL"]
    dagitimsiz = {r.name: r for r in run_checks(runner=lambda cmd: (1, ""))}["WSL"]
    yanitsiz = {r.name: r for r in
                run_checks(runner=lambda cmd: (ZAMAN_ASIMI, ""))}["WSL"]

    komutlar = {yok.fix_hint, dagitimsiz.fix_hint, yanitsiz.fix_hint}
    assert len(komutlar) == 3


def test_run_gercek_zaman_asiminda_ayri_kod_donduruyor():
    """_run gerçek bir zaman aşımını ayrı raporlamalı (uçtan uca).

    Aynı zamanda `timeout=` parametresinin subprocess çağrısında durduğunu
    da bağlar: kaldırılırsa çocuk süreç sonuna kadar beklenir ve rc 0 döner.
    """
    rc, out = env_check._run(
        [sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.5)
    assert rc == ZAMAN_ASIMI
    assert "Command '[" not in out


def test_ZAMAN_ASIMI_gercek_cikis_koduyla_cakismiyor():
    """Sinyalle sonlanan süreç -1..-64 döndürür; sentinel onun dışında olmalı."""
    assert ZAMAN_ASIMI < -256


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


# --- Dialog: dış kaynaklı değerler HTML'e KAÇIŞLI gömülmeli ---
#
# `_render_html` `name`/`detail`/`fix_hint`i doğrudan HTML'e yazıyor ve bu üçü
# DIŞARIDAN geliyor: `detail`, kurulu araçta `shutil.which`/WSL çıktısındaki
# araç YOLU, başarısız dalda `_run`ın döndürdüğü ham hata metni. Kaçışsızken
# QTextBrowser `<...>` içeren bir yolu bilinmeyen etiket sanıp YUTUYORDU
# (ölçüldü 2026-09-05): `/home/x/<deneme>/bin/pdflatex` kullanıcıya
# `/home/x//bin/pdflatex` görünüyor, yani var olmayan bir dizine
# yönlendiriyordu; adı `<...>` olan bir satır ise tamamen adsız kalıyordu.
# Bu diyaloğun tek işi "araç nerede, neden yok" sorusunu yanıtlamak.


@pytest.fixture(scope="session")
def qapp():
    """QApplication'a PYTHON TARAFINDA referans tutar.

    Referansı tutmayan bir kurulum (`QApplication.instance() or
    QApplication([])` sonucunu atmak) süreci abort ettiriyordu: nesne GC'ye
    düşünce C++ tarafı da yıkılıyor ve sonraki widget yaratımı çöküyor
    (ölçüldü: pytest çıkış 127, traceback yok).
    """
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover
        pytest.skip("PyQt6 gerekli")
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def diyalog(qapp, monkeypatch):
    try:
        from gui.env_doctor import EnvDoctorDialog
        from gui.theme import THEMES
    except ImportError:  # pragma: no cover
        pytest.skip("gui modülleri gerekli")
    # Denetim koşmasın: burada sınanan tek şey render
    monkeypatch.setattr(EnvDoctorDialog, "_start", lambda self: None)
    d = EnvDoctorDialog(theme=THEMES["dark"])
    yield d
    d.deleteLater()
    qapp.processEvents()


def _goruntulenen(d, sonuclar):
    """Kullanıcının GÖRDÜĞÜ düz metin (ham HTML değil)."""
    d._view.setHtml(d._render_html(sonuclar))
    return d._view.toPlainText()


@pytest.mark.parametrize("ad,durum,detay,ipucu,beklenen", [
    ("pdflatex", "ok", "/home/kullanici/<deneme>/bin/pdflatex", "",
     "/home/kullanici/<deneme>/bin/pdflatex"),
    ("<arac>", "ok", "/usr/bin/x", "", "<arac>"),
    ("x", "missing", "kurulu değil", "sudo apt-get install <paket>",
     "sudo apt-get install <paket>"),
    ("pdflatex", "ok", "/home/kullanici/a&amp;b/pdflatex", "",
     "/home/kullanici/a&amp;b/pdflatex"),
])
def test_html_ozel_karakterli_deger_oldugu_gibi_gorunuyor(
        diyalog, ad, durum, detay, ipucu, beklenen):
    from core.env_check import CheckResult
    metin = _goruntulenen(diyalog, [CheckResult(ad, durum, detay, ipucu)])
    assert beklenen in metin, (
        "değer yutuldu veya bozuldu: %r -> %r" % (beklenen, metin))


def test_kacis_ham_html_de_uygulanmis(diyalog):
    """Düz metin sınamasının yanına ham HTML sınaması: kaçış GERÇEKTEN var mı."""
    from core.env_check import CheckResult
    ham = diyalog._render_html([CheckResult("p", "ok", "/a/<b>/c")])
    assert "&lt;" in ham, "değer kaçışlanmamış"
    assert "/a/<b>/c" not in ham, "çıplak değer HTML'e sızmış"
    # `<b>` biçim etiketi olarak ad için hâlâ kullanılıyor: tam bir tane
    assert ham.count("<b>") == 1


@pytest.mark.parametrize("deger", [
    "/usr/bin/pdflatex",
    "C:/Program Files/MiKTeX/pdflatex.exe",
    "sudo apt-get update && sudo apt-get install biber",
    "v1.0.20 | Windows 10 | Python 3.12.14",
    '/home/kullanici/"tirnak"/pdflatex',
])
def test_normal_degerler_bozulmadan_geciyor(diyalog, deger):
    """AŞIRI DÜZELTME KAPISI: kaçış, olağan değerleri değiştirmemeli."""
    from core.env_check import CheckResult
    assert deger in _goruntulenen(diyalog, [CheckResult("t", "ok", deger)])


def test_bicimlendirme_ve_eski_davranis_korunuyor(diyalog):
    """Kaçış eklenirken renk/işaret/satır yapısı ve `ok` kuralı bozulmamalı."""
    from core.env_check import CheckResult
    from gui.theme import THEMES

    html = diyalog._render_html([
        CheckResult("a", "ok", "/x"),
        CheckResult("b", "missing", "kurulu değil", "ipucu"),
        CheckResult("c", "info", "bilgi"),
    ])
    t = THEMES["dark"]
    assert t["sem_error"] in html            # missing satırı hata renginde
    assert t["fg_muted"] in html             # info satırı soluk
    assert html.count("<br><br>") == 2       # üç satır, iki ayraç
    assert html.count("<b>") == 3            # her satırın adı kalın
    assert "✅" in html and "❌" in html and "ℹ️" in html

    # `ok` satırında düzeltme ipucu GÖSTERİLMEZ, `missing` satırında gösterilir
    assert "kurma ipucu" not in _goruntulenen(
        diyalog, [CheckResult("p", "ok", "/usr/bin/p", "kurma ipucu")])
    assert "kurma ipucu" in _goruntulenen(
        diyalog, [CheckResult("p", "missing", "kurulu değil", "kurma ipucu")])


def test_turkce_yerellestirme_kacistan_once_calisiyor(diyalog):
    """Kaçış `_yerellestir`den SONRA uygulanmalı, çeviri yolu bozulmamalı."""
    from core.env_check import CheckResult
    metin = _goruntulenen(diyalog, [CheckResult(
        "pdflatex", "missing", "kurulu değil (minted belgeleri için gerekli)")])
    assert "kurulu değil" in metin and "minted" in metin
