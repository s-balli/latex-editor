"""Kurulum listesi tutarlılık testi.

TeX Live kurulum komutu dört yüzeyde elle yaşar: README (TR/EN),
yayın notu şablonu (scripts/release_notes.sh) ve landing page
(docs/index.html). v1.0.12'de
python3-pygments README'lere eklenmiş ama diğer kopyalar sürüklenmişti;
release sayfası eski listeyle yayınlandı. Bu test sapmayı CI'da yakalar:
'tam kurulum' bloklarının (texlive-latex-extra içerenler; minimum kurulum
bilinçli olarak eksiktir) standart paket kümesinin tamamını taşıdığını
her yüzeyde doğrular.
"""

import os
import re

import pytest

_ROOT = os.path.join(os.path.dirname(__file__), "..")

# Standart tam kurulum paketleri. Bu küme testin doğruluk kaynağıdır: listeye
# yeni paket eklenirse önce buraya, sonra dört yüzeye eklenir; biri unutulursa
# test kırmızı olur. (libxcb-cursor0 bilinçli olarak yok: Linux'a özgü ek.)
FULL_PKGS = {
    "texlive-base", "texlive-binaries", "texlive-latex-base",
    "texlive-latex-extra", "texlive-latex-recommended",
    "texlive-lang-european", "texlive-luatex", "texlive-xetex",
    "texlive-fonts-extra", "texlive-science", "texlive-bibtex-extra",
    "texlive-font-utils", "texlive-extra-utils", "biber",
    "texlive-publishers", "texlive-humanities", "texlive-pstricks",
    "python3-pygments", "pandoc",
}

# Satır sonu '\\' devamı: README/HTML'de '\', release.yml echo'sunda '\\"'
_CONT = re.compile(r'\\\s*"?\s*$')

_SURFACES = {
    "README.tr.md": "README.tr.md",
    "README.md": "README.md",
    # release.yml'in gömülü ~100 satırlık notu scripts/release_notes.sh'e
    # taşındı (iki job'da kopyaydı). Yüzey artık o betik.
    "release_notes.sh": os.path.join("scripts", "release_notes.sh"),
    "landing page": os.path.join("docs", "index.html"),
}


def _install_commands(text: str) -> list[set[str]]:
    """Metindeki tüm 'sudo apt-get install ...' komutlarını paket kümesi olarak
    döndürür. Satır-sonu '\\' devam satırları (README/HTML'de '\', yml echo
    satırlarında '\\' + tırnak) birleştirilir."""
    lines = text.splitlines()
    cmds = []
    i = 0
    while i < len(lines):
        if "sudo apt-get install" not in lines[i]:
            i += 1
            continue
        parts = [lines[i]]
        while _CONT.search(parts[-1]) and i + 1 < len(lines):
            i += 1
            parts.append(lines[i])
        joined = " ".join(
            p.rstrip().rstrip("\\").strip().strip('"').strip() for p in parts)
        # HTML yüzeyinde son paket etikete yapışır ('pandoc</code></pre>...')
        toks = {t.strip("`'\"").split("<")[0] for t in joined.split()}
        toks -= {"sudo", "apt-get", "install", "&&", "update", ""}
        cmds.append(toks)
        i += 1
    return cmds


@pytest.mark.parametrize("name", sorted(_SURFACES))
def test_tam_kurulum_listesi_tutarli(name):
    path = os.path.join(_ROOT, _SURFACES[name])
    with open(path, encoding="utf-8") as f:
        cmds = _install_commands(f.read())

    # 'tam kurulum' bloğu: texlive-latex-extra içerir (minimum kurulum
    # bilinçli olarak kısa; tablo satırları install komutu değildir)
    full = [c for c in cmds if "texlive-latex-extra" in c]
    assert full, f"{name}: tam kurulum bloğu hiç ayıklanamadı (parser bozulmuş olabilir)"

    for c in full:
        missing = FULL_PKGS - c
        assert not missing, (
            f"{name}: tam kurulum listesinde eksik paketler: {sorted(missing)} "
            "(README/landing/yayın notu kopyalarından biri sürüklendi; dört "
            "yüzeyi de güncelle)"
        )


def test_ayiklayici_devam_satirlarini_birlestirir():
    """Parser güvenliği: çok satırlı komut tek küme olarak gelmeli."""
    text = ("sudo apt-get install a-pkg b-pkg \\\n"
            "  c-pkg d-pkg\n"
            "sudo apt-get install x-pkg\n")
    cmds = _install_commands(text)
    assert cmds[0] == {"a-pkg", "b-pkg", "c-pkg", "d-pkg"}
    assert cmds[1] == {"x-pkg"}


# --- Landing page: vaat edilen kısayollar gerçekten var mı ---

_KISAYOL = re.compile(
    r'\b(?:Ctrl\+(?:Shift\+)?[A-Za-z0-9/]|Alt\+[A-Za-z]|F\d{1,2})\b')


def _kaynak_metni() -> str:
    """Kısayolların tanımlandığı tüm GUI kaynağı, tek dize."""
    parcalar = []
    for rel in ("desktop/gui/main_window.py", "desktop/gui/editor.py",
                "desktop/gui/find_replace.py", "desktop/gui/pdf_viewer.py"):
        with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
            parcalar.append(f.read())
    for d in ("desktop/gui/mixins", "desktop/gui/pdf_viewer_mixins"):
        tam = os.path.join(_ROOT, d)
        for fn in sorted(os.listdir(tam)):
            if fn.endswith(".py"):
                with open(os.path.join(tam, fn), encoding="utf-8") as f:
                    parcalar.append(f.read())
    return "\n".join(parcalar)


def test_landing_page_var_olmayan_kisayol_vaat_etmiyor():
    """Tanıtım sayfası herkese açık: orada yazan kısayol gerçekten çalışmalı.

    Sayfa kod tabanından bağımsız yaşıyor ve sürükleniyor — `6ebb892` "var
    olan altı özellik sayfada görünmüyordu" diyor, yani drift yönü ikisi de
    olabiliyor. Bu kapı TERS yönü tutuyor: sayfada vaat edilip kodda
    OLMAYAN bir kısayol kalmasın. (Eksik özellik kapıya bağlanamıyor:
    "özellik listesi" diye tek bir doğruluk kaynağı yok.)
    """
    with open(os.path.join(_ROOT, "docs", "index.html"), encoding="utf-8") as f:
        sayfa = f.read()
    metin = re.sub(r"<[^>]+>", " ", sayfa)          # etiketleri at
    sayfada = sorted(set(_KISAYOL.findall(metin)))
    assert len(sayfada) >= 8, f"kapı boş koşuyor, bulunan: {sayfada}"

    kaynak = _kaynak_metni()
    eksik = [k for k in sayfada if k not in kaynak]
    assert not eksik, (
        f"tanıtım sayfası olmayan kısayol(lar) vaat ediyor: {eksik}"
    )


def test_landing_page_yeni_ozellikleri_iceriyor():
    """Son iki turun özellikleri sayfada görünmeli.

    Sayfa güncellenmeden yayınlanan bir sürüm, kullanıcının haberi olmayan
    bir özellik demek; bu depoda bir kez oldu (`6ebb892`).
    """
    with open(os.path.join(_ROOT, "docs", "index.html"), encoding="utf-8") as f:
        sayfa = f.read()
    for beklenen in (
        # v1.0.18
        "Ctrl+Shift+F", "Find in folder", "Klasörde ara",
        "Crash recovery", "Çökme kurtarma",
        # 2026-09-01/02 turu
        "Bibliography tab", "Kaynakça sekmesi",
        "Add a source by DOI", "DOI ile kaynak ekle",
        "File tree operations", "Dosya ağacı işlemleri",
        # var olan iki kartın tazelenmiş metni
        "regular expression", "düzenli ifade",
        "duplicate .bib keys", "mükerrer .bib anahtarını",
        # 2026-09-10 turu: ikisi de sayfada HİÇ YOKTU. Yazım denetimi
        # 2 Eylül'de, otomatik kaydetme 8 Eylül'de yayınlandı; arada iki
        # sürüm çıktı (v1.0.22, v1.0.23) ve sayfa 4 Eylül'den beri
        # değişmemişti.
        "Spell check", "Yazım denetimi",
        "Autosave", "Otomatik kaydetme",
    ):
        assert beklenen in sayfa, f"tanıtım sayfasında yok: {beklenen}"


# Kullanıcıya GÖRÜNMEYEN `feat(` kapsamları: bunlar için sayfada kart
# beklenmiyor. Liste DAR tutuluyor; şüphedeyse kart yazmak doğru olan.
#   docs / seo / pages : sayfanın kendisi ve arama motoru işleri
#   paketleme          : exe/AppImage içine ne girdiği
#   core               : arayüzü olmayan çekirdek katman
_TANITIM_DISI_KAPSAM = {"docs", "seo", "pages", "paketleme", "core"}
_RE_FEAT = re.compile(r"^feat(?:\(([^)]*)\))?:")


def _git(*args):
    """`git` çıktısı; git yoksa ya da komut düşerse None."""
    import subprocess
    try:
        r = subprocess.run(("git",) + args, cwd=_ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def test_tanitim_sayfasi_YAYINLANAN_ozellikten_geride_kalmiyor():
    """Sayfaya en son dokunulduktan SONRA yayınlanan bir özellik olmasın.

    Yukarıdaki içerik kapısının listesi ELLE yazılı, yani yeni bir özellik
    o listeye eklenmezse kapı boş koşuyor. ÖLÇÜLDÜ (2026-09-10): sayfa
    4 Eylül'den beri değişmemişti ve arada iki sürüm çıkmıştı; yazım
    denetimi (2 Eylül) ile otomatik kaydetme (8 Eylül) sayfada HİÇ yoktu.
    O sırada beş tanıtım kapısının beşi de geçiyordu.

    Bu kapı elle liste tutmuyor: `feat(` commit'lerini sayfaya en son
    dokunan commit'ten sonrasında arıyor. Ölçüt TARİH DEĞİL ATA İLİŞKİSİ
    (`<docs>..HEAD`); rebase edilmiş bir tarih sıralamayı bozabilir.

    NE YAKALAMAZ, açıkça: sayfaya başka bir sebeple dokunulmuşsa (rozet,
    SEO) bu kapı susar, çünkü sayfa "yeni"dir. Yazım denetimi tam bu
    şekilde kaçmıştı: 4 Eylül'deki rozet commit'i sayfayı tazelemiş ama
    kart eklenmemişti. O boşluğu yukarıdaki içerik kapısı kapatıyor;
    ikisi birbirinin yerine geçmiyor.

    Sığ klonda (CI öntanımlısı `fetch-depth: 1`) tarih yok; kapı o hâlde
    ATLANIYOR. `ci.yml` bu yüzden `fetch-depth: 0` istiyor.

    ÇALIŞMA AĞACINDA sayfa değişmişse kapı susuyor: commit'lenmemiş bir
    düzeltme de düzeltmedir. Kapı yalnız commit'lenmiş tarihi görebildiği
    için, bu olmadan "özelliği ve kartı ayrı commit'lerde yazma" akışında
    testler kaçınılmaz olarak kırmızı olurdu. CI'da ağaç temiz, yani orada
    denetim tam.
    """
    if _git("rev-parse", "--git-dir") is None:
        pytest.skip("git yok")
    if _git("rev-parse", "--is-shallow-repository") != "false":
        pytest.skip("sığ klon, git tarihi yok")
    if _git("status", "--porcelain", "--", "docs/index.html"):
        return                       # sayfa şu anda düzenleniyor

    sayfa_commit = _git("log", "-1", "--format=%H", "--", "docs/index.html")
    assert sayfa_commit, "docs/index.html git tarihinde hiç görünmüyor"

    sonrasi = _git("log", "--format=%s", f"{sayfa_commit}..HEAD")
    if sonrasi is None:
        pytest.skip("git log aralığı okunamadı")

    kalanlar = []
    for konu in sonrasi.splitlines():
        m = _RE_FEAT.match(konu.strip())
        if m and (m.group(1) or "") not in _TANITIM_DISI_KAPSAM:
            kalanlar.append(konu.strip())
    assert not kalanlar, (
        "tanıtım sayfasına en son dokunulduktan sonra yayınlanan özellik(ler) "
        "var; sayfaya kart ekleyin ya da kapsamı _TANITIM_DISI_KAPSAM'a "
        "yazın:\n  " + "\n  ".join(kalanlar))


def test_landing_page_kart_yapisi_saglam():
    """Kartlar iki dilli ve dengeli olmalı.

    Elle düzenlenen HTML'de kart eklerken açık/kapalı etiket ya da eksik dil
    bloğu bırakmak kolay; sayfa sessizce bozuk görünür.
    """
    with open(os.path.join(_ROOT, "docs", "index.html"), encoding="utf-8") as f:
        sayfa = f.read()
    assert sayfa.count("<article") == sayfa.count("</article>"), "article dengesiz"

    kartlar = re.findall(
        r'<article class="card feat"><span class="feat-emoji">([^<]*)</span>'
        r'<h3><span class="en">([^<]*)</span><span class="tr">([^<]*)</span>',
        sayfa)
    assert len(kartlar) >= 40, f"kart sayısı beklenenden az: {len(kartlar)}"
    for emoji, en, tr in kartlar:
        assert emoji.strip(), f"emojisiz kart: {en}"
        assert en.strip() and tr.strip(), f"tek dilli kart: {en}|{tr}"

    emojiler = [e for e, _en, _tr in kartlar]
    tekrar = sorted({e for e in emojiler if emojiler.count(e) > 1})
    assert not tekrar, f"aynı emoji birden çok kartta: {tekrar}"


def test_landing_page_em_dash_kullanmiyor():
    """Tanıtım sayfasında em dash (—) yok; üslup kısa cümle ve noktalı virgül.

    Sayfanın 33 kartında hiç em dash yoktu; v1.0.18 kartlarını eklerken iki
    tane sokup üslubu bozdum, kullanıcı fark etti. Kapı yalnız docs/ için:
    README ve kod yorumları bu kuralın dışında.
    """
    with open(os.path.join(_ROOT, "docs", "index.html"), encoding="utf-8") as f:
        sayfa = f.read()
    assert "\u2014" not in sayfa, (
        "tanıtım sayfasında em dash (—) var; kısa cümle ya da noktalı virgül kullan"
    )
    assert "\u2013" not in sayfa, "tanıtım sayfasında en dash (–) var"
