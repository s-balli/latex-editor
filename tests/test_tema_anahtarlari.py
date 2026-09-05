"""Tema sözleşmesi: okunan her anahtar var mı, hover kuralları iş yapıyor mu.

İki gerçek kusur bu iki kapının yokluğundan geçti (2026-09-05):

F1. `editor.py` derleme hata işaretini `t.get("error", "#c62828")` ile
    boyuyordu; `theme.py` hiçbir temada `error` tanımlamıyor. Yedek değer
    yedek değil TEK değerdi: render'dan ölçüldü, yedi temada da aynı koyu
    kırmızı çiziliyordu ve beş temada kenar boşluğu zeminine karşıtlığı
    3.0'ın altındaydı (nord 2.22, dracula 2.53, gruvbox 2.62, monokai 2.64,
    dark 2.97). `sem_error` ile 4.29-4.96'ya çıkıyor.
    `_validate_themes()` bunu göremezdi: yalnız REQUIRED_KEYS listesine
    bakıyor, kodun okuduğu anahtarlara bakmıyor. Üstelik uyarıyı yalnız
    log'a yazıyor, hiçbir şeyi düşürmüyor.

F2. `stylesheet.py`'deki `QToolBar QToolButton:hover` bloğu taban blokla
    BİREBİR aynı `background` ve `border` değerlerini veriyordu, yani araç
    çubuğu düğmelerinde hover geri bildirimi yoktu. Yedi temada da, ilk
    commit'ten beri. Kardeş kurallar (`QPushButton:hover`, `:pressed`) değer
    değiştirdiği için etkisizlik kasıtlı değildi.

Kapsam notu: hover taraması ÜRETİLEN KÜRESEL stylesheet'i tarıyor, kusur
oradaydı. Widget'ların kendi stilleri ayrıca ölçüldü (FileTree, OutputPanel;
yedi tema) ve etkisiz blok çıkmadı.
"""

import ast
import pathlib
import re

import pytest

try:
    from gui.stylesheet import build_stylesheet
    from gui.theme import REQUIRED_KEYS, THEMES
except ImportError:  # pragma: no cover
    pytest.skip("gui modülleri gerekli", allow_module_level=True)

_REPO = pathlib.Path(__file__).resolve().parents[1]
_TARANAN = [_REPO / "desktop" / "gui", _REPO / "core"]

# Tema sözlüğünü taşıyan yaygın değişken adları. Yeni bir ad kullanılırsa
# buraya eklenmeli, yoksa o dosya sessizce taranmamış olur.
_TEMA_ADLARI = {"theme", "_theme", "t", "tema", "THEME"}

# `.get(anahtar, varsayilan)` yalnızca varsayılan bir RENGE benziyorsa tema
# okuması sayılıyor. Aksi hâlde adı `t` olan alakasız bir sözlük yanlışlıkla
# işaretlenirdi.
_RENK = re.compile(r"^(#[0-9a-fA-F]{3,8}$|rgba?\()")


def _tema_mi(node):
    if isinstance(node, ast.Name):
        return node.id in _TEMA_ADLARI
    if isinstance(node, ast.Attribute):
        return node.attr in _TEMA_ADLARI
    return False


def _okunan_anahtarlar(tree):
    """(satır, anahtar) ikilileri: kodun tema sözlüğünden okuduğu anahtarlar."""
    for n in ast.walk(tree):
        if (isinstance(n, ast.Subscript) and _tema_mi(n.value)
                and isinstance(n.slice, ast.Constant)
                and isinstance(n.slice.value, str)):
            yield n.lineno, n.slice.value
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr == "get" and _tema_mi(n.func.value)
              and len(n.args) == 2
              and all(isinstance(a, ast.Constant) and isinstance(a.value, str)
                      for a in n.args)
              and _RENK.match(n.args[1].value)):
            yield n.lineno, n.args[0].value


def test_kodun_okudugu_her_tema_anahtari_TANIMLI():
    """Okunan her anahtar hem REQUIRED_KEYS'te hem yedi temada olmalı.

    Kırılırsa: ya anahtarı `theme.py`'ye (REQUIRED_KEYS + yedi tema) ekleyin,
    ya da çağrıyı var olan anahtara çevirin. Tema sözlüğü olmayan bir
    değişkeniniz `t`/`theme` adını taşıyorsa yeniden adlandırın.
    """
    eksik = []
    denetlenen = 0
    for kok in _TARANAN:
        for y in sorted(kok.rglob("*.py")):
            tree = ast.parse(y.read_text(encoding="utf-8"))
            for ln, anahtar in _okunan_anahtarlar(tree):
                denetlenen += 1
                yoklar = [ad for ad, t in THEMES.items() if anahtar not in t]
                if anahtar not in REQUIRED_KEYS or yoklar:
                    eksik.append(
                        "  %s:%d  '%s'  (REQUIRED_KEYS: %s, eksik tema: %s)"
                        % (y.relative_to(_REPO).as_posix(), ln, anahtar,
                           anahtar in REQUIRED_KEYS, yoklar or "yok"))

    assert denetlenen > 40, \
        "yalnız %d okuma görüldü, tarama bozuk olabilir" % denetlenen
    assert not eksik, (
        "kod tanımlı olmayan tema anahtarı okuyor (yedek değer TEK değer "
        "hâline gelir):\n" + "\n".join(eksik))


def test_anahtar_kapisi_GERCEKTEN_isaretliyor():
    """Kapının boş koşmadığının kanıtı: F1'in birebir kendisi verilir."""
    kaynak = 'x = t.get("error", "#c62828")\ny = theme["sem_error"]\n'
    bulunan = {a for _ln, a in _okunan_anahtarlar(ast.parse(kaynak))}
    assert bulunan == {"error", "sem_error"}, bulunan
    assert "error" not in REQUIRED_KEYS
    assert all("error" not in t for t in THEMES.values())


def test_anahtar_kapisi_tema_DISI_get_cagrisini_isaretlemiyor():
    """Karşı durum: rengi olmayan varsayılanlar tema okuması sayılmamalı."""
    kaynak = ('a = t.get("timeout", 5)\n'
              'b = t.get("ad", "varsayilan")\n'
              'c = ayarlar.get("error", "#c62828")\n')
    assert not list(_okunan_anahtarlar(ast.parse(kaynak)))


def test_her_tema_REQUIRED_KEYS_i_TAM_sagliyor():
    """`_validate_themes()` yalnız log'a uyarı yazıyor; burası düşürüyor."""
    for ad, t in THEMES.items():
        eksik = [k for k in REQUIRED_KEYS if k not in t]
        fazla = [k for k in t if k not in REQUIRED_KEYS]
        assert not eksik, "tema '%s' eksik anahtar: %s" % (ad, eksik)
        assert not fazla, "tema '%s' listede olmayan anahtar: %s" % (ad, fazla)


# --- Hover kuralları iş yapıyor mu ---

_BLOK = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _bloklar(qss):
    qss = re.sub(r"/\*.*?\*/", " ", qss, flags=re.S)
    out = {}
    for m in _BLOK.finditer(qss):
        sec = " ".join(m.group(1).split())
        d = {}
        for parca in m.group(2).split(";"):
            if ":" not in parca:
                continue
            ad, _, deger = parca.partition(":")
            d[ad.strip()] = " ".join(deger.split())
        out.setdefault(sec, {}).update(d)
    return out


def _etkisiz_hoverlar(qss):
    """Taban bloğuyla BİREBİR aynı değer veren `:hover` seçicileri."""
    b = _bloklar(qss)
    return [sec for sec, d in b.items()
            if sec.endswith(":hover") and sec[:-len(":hover")] in b and d
            and all(b[sec[:-len(":hover")]].get(k) == v for k, v in d.items())]


@pytest.mark.parametrize("tema", sorted(THEMES))
def test_hover_kurallari_GERCEKTEN_degistiriyor(tema):
    """Bir `:hover` bloğu taban bloğun değerlerini tekrarlıyorsa etkisizdir.

    Kırılırsa: ya bloğu gerçekten değişen bir değere çevirin ya da hover
    istemiyorsanız bloğu silin; sessiz duran bir kural yanıltıcı.
    """
    etkisiz = _etkisiz_hoverlar(build_stylesheet(THEMES[tema]))
    assert not etkisiz, "etkisiz :hover kuralı (%s): %s" % (tema, etkisiz)


def test_hover_kapisi_sentetik_etkisiz_blogu_YAKALIYOR():
    """Kapının boş koşmadığının kanıtı."""
    assert _etkisiz_hoverlar(
        "QX { background: #111; border: 1px solid #222; }"
        "QX:hover { background: #111; border: 1px solid #222; }"
    ) == ["QX:hover"]
    # Karşı durum: gerçekten değişen blok işaretlenmemeli
    assert _etkisiz_hoverlar(
        "QX { background: #111; }QX:hover { background: #999; }") == []
    # Tabanı olmayan hover bloğu da işaretlenmemeli
    assert _etkisiz_hoverlar("QX:hover { background: #111; }") == []


def test_arac_cubugu_hover_i_bg_hover_ve_accent_kullaniyor():
    """F1/F2'nin somut hâli: yedi temada da hover taban değerlerinden ayrı."""
    for ad, t in THEMES.items():
        b = _bloklar(build_stylesheet(t))
        taban = b["QToolBar QToolButton"]
        hover = b["QToolBar QToolButton:hover"]
        assert hover["background"] == t["bg_hover"], ad
        assert t["accent"] in hover["border"], ad
        assert (hover["background"] != taban["background"]
                or hover["border"] != taban["border"]), ad
