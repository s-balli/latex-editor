"""Çeviri çıkarımı — scripts/extract_tr.py ve katalog eksiksizliği.

Regresyon: dönüşüm tek satırlık bir regex'ti, çok satırlı _() çağrılarını
görmüyordu. O dizgeler katalogdan type="vanished" olarak düşüyor, uygulama
İngilizceye alınsa bile ilgili dialoglar Türkçe kalıyordu. CI yalnız
"unfinished" saydığı için sessizce kaçıyordu — bu dosyadaki
test_tum_cevrilebilir_dizgeler_katalogda o boşluğu kapatır.
"""

import ast
import importlib.util
import pathlib
import re
import subprocess

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_TS_EN = _REPO / "desktop" / "translations" / "latexeditor_en.ts"


def _yukle():
    yol = _REPO / "scripts" / "extract_tr.py"
    spec = importlib.util.spec_from_file_location("extract_tr", yol)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


extract_tr = _yukle()


def _cikar(tmp_path, kaynak: str) -> str:
    src = tmp_path / "modul.py"
    src.write_text(kaynak, encoding="utf-8")
    dst = tmp_path / "cikti.py"
    rc = extract_tr.main(["extract_tr.py", str(src), str(dst)])
    assert rc == 0
    return dst.read_text(encoding="utf-8")


BASLIK = ('from PyQt6.QtCore import QCoreApplication\n'
          '_ = lambda s: QCoreApplication.translate("Ctx", s)\n')


# --- bağlam çıkarımı ---


def test_baglam_lambdadan_okunur(tmp_path):
    cikti = _cikar(tmp_path, BASLIK + '_("merhaba")\n')
    assert "QCoreApplication.translate('Ctx', 'merhaba')" in cikti


def test_baglam_yoksa_cikti_bos(tmp_path):
    """Çeviri kısayolu tanımlamayan dosyadan çıkarılacak bir şey yok."""
    assert _cikar(tmp_path, 'x = 1\ndef f(): return 2\n') == ""


# --- asıl regresyon: çok satırlı çağrılar ---


def test_cok_satirli_cagri_cikarilir(tmp_path):
    kaynak = BASLIK + '''
msg = _(
    "{f} diskte değiştirildi.\\n\\n"
    "Kaydedilmemiş değişiklikleriniz var."
).format(f="a.tex")
'''
    cikti = _cikar(tmp_path, kaynak)
    assert "{f} diskte değiştirildi.\\n\\nKaydedilmemiş değişiklikleriniz var." in cikti


def test_ic_ice_parantezli_cok_satirli(tmp_path):
    kaynak = BASLIK + '''
dlg.setText(_(
    "bir "
    "iki"
).format(x=1))
'''
    assert "'bir iki'" in _cikar(tmp_path, kaynak)


def test_satir_numarasi_korunur(tmp_path):
    """<location line=...> kaynakla eşleşmeli; çevirmen bağlamı bulabilsin."""
    kaynak = BASLIK + "\n" * 8 + '_("onuncu satır")\n'
    cikti = _cikar(tmp_path, kaynak)
    satirlar = cikti.split("\n")
    (idx,) = [i for i, s in enumerate(satirlar) if "onuncu satır" in s]
    kaynak_satiri = kaynak.split("\n").index('_("onuncu satır")')
    assert idx == kaynak_satiri


def test_ayni_satirda_iki_cagri(tmp_path):
    cikti = _cikar(tmp_path, BASLIK + '999 if _("bir") else _("iki")\n')
    assert "'bir'" in cikti and "'iki'" in cikti


# --- regex sürümünün patladığı yerler ---


def test_fstring_icindeki_cagri(tmp_path):
    """Regex sürümü burada tırnak çakıştırıp 'Invalid syntax' veriyordu."""
    kaynak = BASLIK + "ad = 'x'\nmesaj = f\"{_('etiket')}: {ad}\"\n"
    assert "'etiket'" in _cikar(tmp_path, kaynak)


def test_tek_tirnakli_cagri(tmp_path):
    assert "'tek tırnak'" in _cikar(tmp_path, BASLIK + "_('tek tırnak')\n")


def test_icinde_tirnak_gecen_dizge(tmp_path):
    cikti = _cikar(tmp_path, BASLIK + '''_("o'nun \\"tırnak\\" hâli")\n''')
    assert "tırnak" in cikti
    ast.parse(cikti)  # üretilen dosya geçerli Python olmalı


def test_uretilen_dosya_hep_gecerli_python(tmp_path):
    kaynak = BASLIK + '''
a = _("satır\\nsonu")
b = _('ters\\\\bölü')
c = _("yüzde %s ve {süslü}")
'''
    ast.parse(_cikar(tmp_path, kaynak))


# --- çıkarılamayan çağrılar uyarı vermeli ---


def test_degisken_alan_cagri_uyarir(tmp_path, capsys):
    src = tmp_path / "m.py"
    src.write_text(BASLIK + "mesaj = 'x'\n_(mesaj)\n", encoding="utf-8")
    dst = tmp_path / "o.py"
    extract_tr.main(["extract_tr.py", str(src), str(dst)])
    assert "sabit dizge almıyor" in capsys.readouterr().err


def test_bozuk_dosya_hata_koduyla_doner(tmp_path, capsys):
    src = tmp_path / "bozuk.py"
    src.write_text("def (:\n", encoding="utf-8")
    rc = extract_tr.main(["extract_tr.py", str(src), str(tmp_path / "o.py")])
    assert rc == 1
    assert "ayrıştırılamadı" in capsys.readouterr().err


# --- katalog eksiksizliği (asıl kapı) ---


def _katalog_kaynaklari() -> set[str]:
    """.ts içindeki KULLANILABİLİR <source> metinleri (vanished/obsolete hariç)."""
    ts = _TS_EN.read_text(encoding="utf-8")
    canli = set()
    for blok in re.findall(r"<message>.*?</message>", ts, re.S):
        if 'type="vanished"' in blok or 'type="obsolete"' in blok:
            continue
        m = re.search(r"<source>(.*?)</source>", blok, re.S)
        if m:
            canli.add(m.group(1).replace("&amp;", "&")
                      .replace("&lt;", "<").replace("&gt;", ">"))
    return canli


# Kapının taradığı ağaçlar, `update_translations.sh`in beslediğiyle AYNI
# olmalı. `core` SONRADAN eklendi: ikisi de yalnız `desktop/`e bakıyordu ve
# core/compiler.py'nin dört kullanıcı mesajı katalogda hiç yoktu. Kapı da aynı
# kör noktada olduğu için bunu göremiyordu (ölçüldü 2026-09-05: `Compiler`
# bağlamı iki `.ts` dosyasında da yok, mesajlar Windows'ta WSL kurulu
# değilken Log ve Öneriler sekmelerinde Türkçe çıkıyordu).
_TARANAN = ["desktop/gui", "desktop/main.py", "core"]


def _kaynak_dizgeleri() -> list[tuple[str, int, str]]:
    """Koddaki tüm _( "sabit" ) çağrıları: (dosya, satır, metin)."""
    ciktilar = subprocess.run(
        ["git", "ls-files"] + _TARANAN,
        cwd=_REPO, capture_output=True, text=True, check=True, encoding="utf-8").stdout.split()
    bulunan = []
    for rel in ciktilar:
        if not rel.endswith(".py"):
            continue
        tree = ast.parse((_REPO / rel).read_text(encoding="utf-8"))
        for lineno, metin in extract_tr.topla(tree)[0]:
            bulunan.append((rel, lineno, metin))
    return bulunan


@pytest.mark.skipif(not _TS_EN.exists(), reason="çeviri kataloğu yok")
def test_tum_cevrilebilir_dizgeler_katalogda():
    """Koddaki her _() dizgesi İngilizce katalogda canlı bir girdi olmalı.

    Bu testin kırılması demek: o metin İngilizce arayüzde Türkçe görünüyor.
    Düzeltme — WSL/Linux'ta:
        PATH=/usr/lib/qt6/bin:$PATH bash scripts/update_translations.sh
    ardından latexeditor_en.ts içindeki yeni unfinished girdileri doldur.
    """
    canli = _katalog_kaynaklari()
    eksik = [(f, ln, m) for f, ln, m in _kaynak_dizgeleri() if m not in canli]
    assert not eksik, "katalogda karşılığı olmayan dizgeler:\n" + "\n".join(
        f"  {f}:{ln}  {m[:70]!r}" for f, ln, m in eksik)


@pytest.mark.skipif(not _TS_EN.exists(), reason="çeviri kataloğu yok")
def test_katalogda_bitmemis_ceviri_yok():
    """CI kapısının aynısı; yerelde de kırmızı yansın."""
    ts = _TS_EN.read_text(encoding="utf-8")
    assert 'type="unfinished"' not in ts, "latexeditor_en.ts içinde unfinished çeviri var"


# --- .ts ↔ .qm senkronu: uygulamanın GERÇEKTEN yüklediği dosya ---

_QM_EN = _REPO / "desktop" / "translations" / "latexeditor_en.qm"


@pytest.mark.skipif(not (_TS_EN.exists() and _QM_EN.exists()),
                    reason="çeviri kataloğu veya derlenmiş .qm yok")
def test_qm_ts_ile_senkron():
    """Derlenmiş .qm, kaynak .ts ile aynı çevirileri taşımalı.

    CI kapısı ve bu dosyadaki diğer testler yalnız .TS'i okuyor; uygulama ise
    çalışırken .QM yüklüyor (core/i18n.py: translator.load(qm_path)).
    scripts/update_translations.sh içinde lrelease OPSİYONEL — bulunamazsa
    yalnız uyarı basıp çıkıyor. Yani .ts doldurulup lrelease unutulunca her
    şey yeşil kalıyor, İngilizce arayüzde o dialoglar Türkçe görünüyordu.
    Deneyle doğrulandı: .ts'te bir çeviriyi bozup lrelease koşmadan tüm
    paket geçiyordu.

    Düzeltme — WSL/Linux'ta:
        PATH=/usr/lib/qt6/bin:$PATH lrelease desktop/translations/*.ts
    """
    import xml.etree.ElementTree as ET

    QtCore = pytest.importorskip("PyQt6.QtCore")

    # install ETMEDEN doğrudan sorgula: global çevirmen durumuna dokunmayalım,
    # başka testlerin diline karışmasın.
    translator = QtCore.QTranslator()
    assert translator.load(str(_QM_EN)), f"yüklenemedi: {_QM_EN}"

    uyusmayan = []
    kontrol = 0
    for ctx in ET.parse(_TS_EN).getroot().findall("context"):
        ctx_adi = ctx.findtext("name") or ""
        for msg in ctx.findall("message"):
            tr = msg.find("translation")
            if tr is None or tr.get("type") in ("unfinished", "vanished", "obsolete"):
                continue
            kaynak, beklenen = msg.findtext("source"), (tr.text or "")
            if not kaynak or not beklenen:
                continue
            kontrol += 1
            # QTranslator.translate() C++ tarafında const char* alıyor; PyQt6
            # str'i ASCII'ye çevirmeye çalışıp Türkçe karakterde patlıyor.
            # Qt kaynak metni .qm'de UTF-8 tutuyor, bayt geçmek doğrusu.
            bulunan = translator.translate(ctx_adi.encode("utf-8"),
                                           kaynak.encode("utf-8"))
            # Qt çevirisi bulamazsa "" döndürür
            if bulunan != beklenen:
                uyusmayan.append(f"  [{ctx_adi}] {kaynak[:50]!r}\n"
                                 f"     .ts: {beklenen[:50]!r}\n"
                                 f"     .qm: {bulunan[:50]!r}")

    assert kontrol > 100, f"yalnız {kontrol} mesaj denetlendi — ayrıştırma bozuk olabilir"
    assert not uyusmayan, (
        f".qm, .ts ile senkron değil ({len(uyusmayan)}/{kontrol} mesaj). "
        "lrelease koşulmamış olabilir:\n" + "\n".join(uyusmayan[:10]))


# =====================================================================
# Kapının KAPSAMI: çeviri kısayolu tanımlayan her dosya taranmalı
#
# ÖLÇÜLEN KUSUR (2026-09-05): `core/compiler.py` çeviri kısayolunu tanımlıyor
# ve dört kullanıcı mesajını onunla sarıyor, ama `update_translations.sh`
# yalnız `desktop/gui*` + `desktop/main.py` besliyordu. Sonuç: `Compiler`
# bağlamı iki `.ts` dosyasında da YOKTU ve Windows'ta WSL kurulu değilken
# Log sekmesinde Türkçe mesaj çıkıyordu, yani yeni bir kullanıcının ilk
# derlemesinde.
#
# Yukarıdaki `test_tum_cevrilebilir_dizgeler_katalogda` bunu göremiyordu,
# çünkü O DA aynı dar kümeye bakıyordu. Kapının kendi kapsamını denetleyen
# bir şey olmadan aynı kaçak yeni bir pakette sessizce tekrarlanır.
# =====================================================================

# Depoda taranmayacak ağaçlar: yedek, pasif ve üçüncü taraf.
_HARIC = {"tmp", "web", "template", "tests", "node_modules", "__pycache__",
          "build", "dist", "scripts"}


def _kisayol_tanimlayan_dosyalar() -> list[str]:
    """Çeviri kısayolu tanımlayan VE en az bir sabit `_()` çağrısı olanlar."""
    ciktilar = subprocess.run(
        ["git", "ls-files"], cwd=_REPO, capture_output=True, text=True,
        check=True, encoding="utf-8").stdout.split()
    bulunan = []
    for rel in ciktilar:
        if not rel.endswith(".py"):
            continue
        if rel.split("/")[0] in _HARIC:
            continue
        try:
            tree = ast.parse((_REPO / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        if not extract_tr.bul_baglam(tree):
            continue
        if extract_tr.topla(tree)[0]:
            bulunan.append(rel)
    return bulunan


def _taranan_kapsiyor_mu(rel: str) -> bool:
    return any(rel == t or rel.startswith(t.rstrip("/") + "/")
               for t in _TARANAN)


def test_kisayol_tanimlayan_her_dosya_kapinin_kapsaminda():
    """Yeni bir paket eklenip beslenmezse burada kırmızı yansın.

    Kırılırsa: dosyanın ağacını hem `_TARANAN`a hem de
    `scripts/update_translations.sh`teki `find` listesine ekleyin, sonra
    WSL/Linux'ta `PATH=/usr/lib/qt6/bin:$PATH bash scripts/update_translations.sh`
    koşturup yeni `unfinished` girdileri doldurun. `core/` dışında yeni bir
    kök eklenirse `scripts/ts_yollarini_duzelt.py:_KOKLER` de güncellenmeli.
    """
    dosyalar = _kisayol_tanimlayan_dosyalar()
    # önkoşul: tarama gerçekten bir şey buluyor olmalı
    assert len(dosyalar) > 20, (
        "yalnız %d dosya bulundu, tarama bozuk olabilir" % len(dosyalar))
    disarida = [d for d in dosyalar if not _taranan_kapsiyor_mu(d)]
    assert not disarida, (
        "çevrilebilir dizge taşıyan ama kapının taramadığı dosyalar:\n  "
        + "\n  ".join(disarida))


def test_core_compiler_kapsamda():
    """Kusurun çıktığı dosya adıyla sabitleniyor (kapsam daralırsa görünür)."""
    assert _taranan_kapsiyor_mu("core/compiler.py")
    assert "core/compiler.py" in _kisayol_tanimlayan_dosyalar()


def test_kapi_ve_arac_zinciri_AYNI_agaclara_bakiyor():
    """`_TARANAN` ile `update_translations.sh`in beslediği küme ayrışmasın.

    İkisi ayrışırsa kapı yeşil kalırken katalog eksik kalır; kusur tam
    olarak buydu (ikisi de dar, ikisi de aynı yönde yanlış).
    """
    betik = (_REPO / "scripts" / "update_translations.sh").read_text(
        encoding="utf-8")
    m = re.search(r"for src in \$\(find ([^)]*?) -name", betik)
    assert m, "update_translations.sh içindeki find satırı bulunamadı"
    besleyen = set(m.group(1).split())
    # `desktop/main.py` find'in dışında, döngü satırının sonunda duruyor
    assert "desktop/main.py" in betik
    besleyen.add("desktop/main.py")
    assert besleyen == set(_TARANAN), (
        "kapı %s tarıyor, betik %s besliyor" % (sorted(_TARANAN),
                                                sorted(besleyen)))


# =====================================================================
# Parçalardan kurulan cümle: çevirmen bağlamı göremiyor
#
# ÖLÇÜLEN KUSUR (2026-09-05): `synctex_ops.py` durum mesajını
# `"SyncTeX: " + _("Satır") + ...` diye kuruyordu. Çevirmene bağlamsız tek
# bir "Satır" kelimesi gidiyor; katalogda "Row" olarak çevrilmişti ve
# İngilizce arayüzde "SyncTeX: Row 42 → Page 3" yazıyordu. "Row" tablo
# satırı demek. Aynı tuzak imleç konumunda da vardı ("Row 12, Column 4").
# =====================================================================

_QM_EN2 = _REPO / "desktop" / "translations" / "latexeditor_en.qm"


@pytest.fixture(scope="module")
def ceviri():
    """Kurulu bir QTranslator üzerinden İngilizce çeviri fonksiyonu."""
    QtWidgets = pytest.importorskip("PyQt6.QtWidgets")
    QtCore = pytest.importorskip("PyQt6.QtCore")
    if not _QM_EN2.exists():
        pytest.skip("derlenmiş .qm yok")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    t = QtCore.QTranslator()
    assert t.load(str(_QM_EN2)), _QM_EN2
    app.installTranslator(t)
    yield lambda ctx, s: QtCore.QCoreApplication.translate(ctx, s)
    app.removeTranslator(t)


@pytest.mark.parametrize("sablon,par,beklenen", [
    ("SyncTeX: Satır {satir} → Sayfa {sayfa}",
     {"satir": 42, "sayfa": 3}, "SyncTeX: Line 42 → Page 3"),
    ("SyncTeX: Sayfa {sayfa} → {dosya}:{satir}",
     {"sayfa": 3, "dosya": "main.tex", "satir": 42},
     "SyncTeX: Page 3 → main.tex:42"),
])
def test_synctex_durum_mesaji_ingilizce_dogru(ceviri, sablon, par, beklenen):
    assert ceviri("SyncTexMixin", sablon).format(**par) == beklenen


def test_kaynak_satiri_Row_diye_cevrilmiyor():
    """'Row' yalnız GERÇEK tablo satırında doğru.

    Bağlamsız tek kelime çevrildiğinde "satır" tablo satırı sanılıyor.
    TableWizardDialog'da doğru; başka hiçbir canlı girdide olmamalı.
    """
    import xml.etree.ElementTree as ET

    kotu = []
    for ctx in ET.parse(_TS_EN).getroot().findall("context"):
        ad = ctx.findtext("name") or ""
        for msg in ctx.findall("message"):
            tr = msg.find("translation")
            if tr is None or tr.get("type") in ("vanished", "obsolete"):
                continue
            if (tr.text or "") == "Row" and ad != "TableWizardDialog":
                kotu.append((ad, msg.findtext("source")))
    assert not kotu, (
        "kaynak satırı 'Row' diye çevrilmiş (doğrusu 'Line'): %s" % kotu)


def _formatlanan_dizgeler() -> set[str]:
    """Kodda `_("...").format(...)` diye kullanılan dizgeler.

    YALNIZ bunlar sınanabilir. Katalogda `{ad}` geçen her dizge yer tutucu
    değil: `"\\begin{ad}'a \\end{ad} otomatik kapanır"` düz LaTeX metni ve
    çevirisinde `{name}` olması DOĞRU. Kaynağa bakmadan ikisi ayrılamıyor.
    """
    bulunan = set()
    for rel in subprocess.run(
            ["git", "ls-files"] + _TARANAN, cwd=_REPO, capture_output=True,
            text=True, check=True, encoding="utf-8").stdout.split():
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse((_REPO / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "format"):
                continue
            ic = n.func.value
            if (isinstance(ic, ast.Call) and isinstance(ic.func, ast.Name)
                    and ic.func.id == "_" and len(ic.args) == 1
                    and isinstance(ic.args[0], ast.Constant)
                    and isinstance(ic.args[0].value, str)):
                bulunan.add(ic.args[0].value)
    return bulunan


def test_ceviriler_yer_tutuculari_koruyor():
    """`{ad}` yer tutucusu düşerse `.format()` KeyError atar, mesaj kaybolur.

    Parçalı cümleleri tek parçaya çevirmek yer tutucu kullanmayı yaygın
    hâle getiriyor; bu kapı onunla birlikte gelmeli.
    """
    import xml.etree.ElementTree as ET

    formatlanan = _formatlanan_dizgeler()
    desen = re.compile(r"\{([a-zA-Z_][a-zA-Z_0-9]*)\}")
    kotu = []
    kontrol = 0
    for ctx in ET.parse(_TS_EN).getroot().findall("context"):
        ad = ctx.findtext("name") or ""
        for msg in ctx.findall("message"):
            tr = msg.find("translation")
            if tr is None or tr.get("type") in ("unfinished", "vanished",
                                                "obsolete"):
                continue
            kaynak, hedef = msg.findtext("source") or "", tr.text or ""
            if kaynak not in formatlanan:
                continue
            k = set(desen.findall(kaynak))
            if not k:
                continue
            kontrol += 1
            if k != set(desen.findall(hedef)):
                kotu.append((ad, kaynak, hedef))
    assert kontrol > 5, "yer tutuculu girdi az, tarama bozuk olabilir"
    assert not kotu, "çeviride yer tutucu kaybolmuş/değişmiş: %s" % kotu
