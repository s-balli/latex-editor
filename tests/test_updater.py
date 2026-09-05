
import pytest
"""updater.py — güncelleme kontrolü testleri."""

import json as _json

from core.updater import (
    _parse_semver, _is_newer, check_for_update, _extract_changelog,
    _satira_hizali_kirp, clear_cache, VERSION,
)


class TestParseSemver:
    def test_v_prefix(self):
        assert _parse_semver("v1.2.3") == (1, 2, 3)

    def test_no_prefix(self):
        assert _parse_semver("1.2.3") == (1, 2, 3)

    def test_uppercase_v(self):
        assert _parse_semver("V2.0.0") == (2, 0, 0)

    def test_two_parts(self):
        assert _parse_semver("v1.0") == (1, 0, 0)

    def test_invalid_letters(self):
        assert _parse_semver("vabc") == (0, 0, 0)

    def test_empty(self):
        assert _parse_semver("") == (0, 0, 0)


class TestIsNewer:
    def test_higher_major(self):
        assert _is_newer("v2.0.0", "1.0.0") is True

    def test_higher_minor(self):
        assert _is_newer("v1.1.0", "1.0.0") is True

    def test_higher_patch(self):
        assert _is_newer("v1.0.1", "1.0.0") is True

    def test_same_version(self):
        assert _is_newer("v1.0.0", "1.0.0") is False

    def test_lower_version(self):
        assert _is_newer("v0.9.9", "1.0.0") is False

    def test_equal_current_version(self):
        assert _is_newer(VERSION, VERSION) is False


class TestExtractChangelog:
    def test_with_installation_separator(self):
        body = "## What's Changed\n\n- Fix X\n\n---\n\n## Installation\n\n..."
        result = _extract_changelog(body)
        assert "Fix X" in result
        assert "Installation" not in result

    def test_with_kurulum_separator(self):
        body = "## What's Changed\n\n- Fix X\n\n---\n\n## Kurulum\n\n..."
        result = _extract_changelog(body)
        assert "Fix X" in result
        assert "Kurulum" not in result

    def test_with_plain_separator(self):
        body = "## What's Changed\n\n- Fix X\n\n---\n\nSome other content"
        result = _extract_changelog(body)
        assert "Fix X" in result
        assert "Some other" not in result

    def test_no_separator(self):
        body = "Just changelog content"
        assert _extract_changelog(body) == "Just changelog content"

    def test_empty_body(self):
        assert _extract_changelog("") == ""


class TestCheckForUpdate:
    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    def test_returns_network_error_on_failure(self, monkeypatch):
        """Network hatası {'error': 'network'} döndürmeli — crash değil."""
        import core.updater as mod
        monkeypatch.setattr(mod, "fetch_latest_release", lambda: None)
        result = check_for_update()
        assert result is not None
        assert result.get("error") == "network"

    def test_returns_none_when_up_to_date(self, monkeypatch):
        import core.updater as mod
        monkeypatch.setattr(mod, "fetch_latest_release", lambda: {"tag_name": "v" + VERSION})
        assert check_for_update() is None

    def test_returns_info_when_newer(self, monkeypatch):
        import core.updater as mod
        monkeypatch.setattr(mod, "fetch_latest_release", lambda: {
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/s-balli/latex-editor/releases/v99.0.0",
            "body": "New release",
        })
        result = check_for_update()
        assert result is not None
        assert result["tag"] == "v99.0.0"
        assert "html_url" not in result
        assert result["url"] == "https://github.com/s-balli/latex-editor/releases/v99.0.0"
        assert result["notes"] == "New release"

    def test_returns_network_error_when_tag_missing(self, monkeypatch):
        """Tag yoksa {'error': 'network'} döndürmeli."""
        import core.updater as mod
        monkeypatch.setattr(mod, "fetch_latest_release", lambda: {"body": "no tag"})
        result = check_for_update()
        assert result is not None
        assert result.get("error") == "network"

    def test_force_bypasses_cache(self, monkeypatch):
        """force=True cache'i bypass etmeli."""
        import core.updater as mod
        call_count = [0]
        def mock_fetch():
            call_count[0] += 1
            return {"tag_name": "v99.0.0", "html_url": "url", "body": "x"}
        monkeypatch.setattr(mod, "fetch_latest_release", mock_fetch)
        check_for_update()
        assert call_count[0] == 1
        check_for_update(force=True)
        assert call_count[0] == 2

    def test_cache_prevents_repeat_calls(self, monkeypatch):
        """Cache 24h içinde tekrar API çağrısı yapmamalı."""
        import core.updater as mod
        call_count = [0]
        def mock_fetch():
            call_count[0] += 1
            return {"tag_name": "v99.0.0", "html_url": "url", "body": "x"}
        monkeypatch.setattr(mod, "fetch_latest_release", mock_fetch)
        check_for_update()
        check_for_update()
        check_for_update()
        assert call_count[0] == 1

    def test_cache_prevents_repeat_calls_when_up_to_date(self, monkeypatch):
        """'Güncelleme yok' durumu da cache'lenmeli — tekrar API çağrısı yapmamalı.

        Regression: eskiden sadece 'yeni sürüm var' (positive) cache'leniyordu;
        up-to-date durumunda _cached_result=None set edilmesine rağmen cache kontrolü
        'is not None' gerektirdiği için her çağrıda yeniden fetch edilirdi.
        """
        import core.updater as mod
        call_count = [0]
        def mock_fetch():
            call_count[0] += 1
            return {"tag_name": "v" + VERSION}  # mevcut sürüm → güncelleme yok
        monkeypatch.setattr(mod, "fetch_latest_release", mock_fetch)
        assert check_for_update() is None
        assert check_for_update() is None
        assert check_for_update() is None
        assert call_count[0] == 1  # tek fetch — sonraki çağrılar cacheden döner

    def test_cache_returns_same_result(self, monkeypatch):
        """Cache aynı sonucu döndürmeli."""
        import core.updater as mod
        monkeypatch.setattr(mod, "fetch_latest_release", lambda: {
            "tag_name": "v99.0.0", "html_url": "url", "body": "x"
        })
        r1 = check_for_update()
        r2 = check_for_update()
        assert r1 == r2
        assert r1 is not None


# --- Bozuk GitHub yanıtı güncelleme kontrolünü öldürmesin ---


class _SahteYanit:
    """urlopen dönüşü: bağlam yöneticisi + read."""

    def __init__(self, veri: bytes):
        self._veri = veri

    def read(self, n=-1):
        return self._veri

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _yanitla(monkeypatch, ham: str):
    import core.updater as up
    up._cached_time = 0.0
    up._cached_result = None
    monkeypatch.setattr(up.urllib.request, "urlopen",
                        lambda *a, **k: _SahteYanit(ham.encode("utf-8")))
    return up


@pytest.mark.parametrize("ham,aciklama", [
    ('{"tag_name": "v99.0.0", "body": null, "html_url": "u"}', "body: null"),
    ('{"tag_name": "v99.0.0", "html_url": "u"}', "body alanı yok"),
    ('[1, 2, 3]', "JSON dizi"),
    ('"metin"', "JSON metin"),
    ('null', "JSON null"),
    ('42', "JSON sayı"),
    ('{"tag_name": 12345}', "tag_name sayı"),
    ('{"tag_name": "v99.0.0", "html_url": 7}', "html_url sayı"),
])
def test_bozuk_yanit_guncelleme_kontrolunu_oldurmuyor(monkeypatch, ham, aciklama):
    """GitHub açıklamasız release'de `body` alanını NULL gönderiyor.

    `release.get("body", "")` varsayılanı devreye girmiyor ve `in` denetimi
    TypeError atıyordu; nesne olmayan JSON ise `.get`te AttributeError
    veriyordu. GUI yuttuğu için süreç çökmüyordu ama güncelleme kontrolü her
    seferinde "ağ hatası" sanılıyordu (ölçüldü 2026-09-02, dış güvenlik
    raporu 5. bulgu). `tag_name` sayı gelirse `_is_newer` içindeki lstrip de
    patlıyordu; o rapordan bağımsız çıktı.
    """
    up = _yanitla(monkeypatch, ham)
    sonuc = up.check_for_update(force=True)          # istisna atmamalı
    assert sonuc is None or isinstance(sonuc, dict), aciklama


def test_normal_yanit_hala_calisiyor(monkeypatch):
    """Sertleştirme geçerli yanıtı bozmamalı."""
    up = _yanitla(
        monkeypatch,
        '{"tag_name": "v99.0.0", "body": "## Yenilikler\\n- şey", "html_url": "https://x"}')
    sonuc = up.check_for_update(force=True)
    assert sonuc["tag"] == "v99.0.0"
    assert sonuc["url"] == "https://x"


def test_url_yoksa_release_sayfasina_dusuyor(monkeypatch):
    up = _yanitla(monkeypatch, '{"tag_name": "v99.0.0"}')
    sonuc = up.check_for_update(force=True)
    assert sonuc["url"].startswith("https://github.com/")


# --- Bozuk KODLAMA da "ağ hatası" olmalı, istisna değil (2026-09-05) ---
#
# `resp.read(...).decode("utf-8")` geçersiz bayt dizisinde UnicodeDecodeError
# atıyor ve o, yakalanan listede YOKTU. Fonksiyonun sözleşmesi ("None: Hata
# veya bağlantı yok") kırılıyor, `check_for_update` de dict/None yerine
# istisna fırlatıyordu. JSONDecodeError ile UnicodeDecodeError'in ikisi de
# ValueError altında (UnicodeDecodeError OSError altında DEĞİL), yani birini
# yakalayıp diğerini atlamak karar değil gözden kaçmaydı. Arayüz kendi geniş
# `except Exception`ı ile örtüyordu; örtmeyen her çağıran patlıyordu.


def _bayt_yanitla(monkeypatch, veri: bytes):
    """Ham BAYT yanıtı: `_yanitla` metni utf-8'e kodluyor, bozuk kodlama
    oradan ifade edilemiyor."""
    import core.updater as up
    up._cached_time = 0.0
    up._cached_result = None
    monkeypatch.setattr(up.urllib.request, "urlopen",
                        lambda *a, **k: _SahteYanit(veri))
    return up


_BOZUK_KODLAMA = [
    (b'\xff\xfe{"tag_name": "v9"}', "geçersiz başlangıç baytı"),
    ('{"tag_name": "v9"}'.encode("utf-16"), "UTF-16"),
    ('{"tag_name": "v9"}'.encode("utf-32"), "UTF-32"),
    (b'{"a": "\xc3', "yarım UTF-8 dizisi"),
    (b'\x80', "tek devam baytı"),
]


@pytest.mark.parametrize("veri,aciklama", _BOZUK_KODLAMA)
def test_bozuk_kodlama_None_donuyor(monkeypatch, veri, aciklama):
    """Kırılırsa: UnicodeDecodeError yakalanan listeden düşmüş demektir."""
    up = _bayt_yanitla(monkeypatch, veri)
    assert up.fetch_latest_release() is None, aciklama


@pytest.mark.parametrize("veri,aciklama", _BOZUK_KODLAMA)
def test_bozuk_kodlama_check_for_update_i_OLDURMUYOR(monkeypatch, veri,
                                                     aciklama):
    up = _bayt_yanitla(monkeypatch, veri)
    assert up.check_for_update(force=True) == {"error": "network"}, aciklama


@pytest.mark.parametrize("veri,aciklama", _BOZUK_KODLAMA)
def test_vakalar_GERCEKTEN_cozulemiyor(veri, aciklama):
    """Kapı boş koşmasın: baytlar utf-8 ile gerçekten çözülememeli.

    Biri çözülebilir hâle gelirse yukarıdaki testler düzeltme geri alınsa
    bile yeşil kalır ve hiçbir şey kanıtlamaz.
    """
    with pytest.raises(UnicodeDecodeError):
        veri.decode("utf-8")


def test_gecerli_JSON_ama_bozuk_BAYT_de_None(monkeypatch):
    """Yapısı sağlam ama içinde geçersiz bayt olan yanıt da reddedilmeli.

    `errors="replace"` ile çözmek bu yanıtı U+FFFD'lerle GEÇİRİRDİ: sürüm
    notu sessizce bozuk gösterilir, hata da hiç görünmezdi. Kapı o kestirme
    çözümü burada engelliyor.
    """
    up = _bayt_yanitla(
        monkeypatch, b'{"tag_name": "v99.0.0", "body": "bozuk \xff nota"}')
    assert up.fetch_latest_release() is None
    up = _bayt_yanitla(
        monkeypatch, b'{"tag_name": "v99.0.0", "body": "bozuk \xff nota"}')
    assert up.check_for_update(force=True) == {"error": "network"}


def test_bozuk_kodlama_onbellege_YAZILMIYOR(monkeypatch):
    """Ağ hatası cache'lenmemeli; bozuk kodlama da öyle."""
    up = _bayt_yanitla(monkeypatch, b'\xff')
    up.check_for_update(force=False)
    assert up._cached_time == 0.0
    # Sonraki çağrı API'ye gitmeli (cache engellememeli)
    up = _bayt_yanitla(monkeypatch, b'{"tag_name": "v0.0.1"}')
    assert up.check_for_update(force=False) is None


def test_yakalanan_liste_HALA_dar(monkeypatch):
    """Karşı durum: alakasız istisna yutulmamalı.

    Bu olmadan düzeltme `except Exception`a genişletilebilir ve kapı fark
    etmezdi.
    """
    import core.updater as up
    up._cached_time = 0.0
    up._cached_result = None

    def _patla(*a, **k):
        raise RuntimeError("beklenmedik")

    monkeypatch.setattr(up.urllib.request, "urlopen", _patla)
    with pytest.raises(RuntimeError):
        up.fetch_latest_release()


def test_UnicodeDecodeError_OSError_altinda_DEGIL():
    """Geniş `OSError` yakalaması onu tutmuyor; ayrıca listelenmesi şart."""
    assert issubclass(UnicodeDecodeError, ValueError)
    assert not issubclass(UnicodeDecodeError, OSError)


# ---------------------------------------------------------------------------
# Sürüm notlarının GÖSTERİMİ. Getirme yolunu bugün sertleştirmiştik ama
# gösterime hiç bakmamıştık; v1.0.19 yayınlandıktan sonra gerçek API yanıtıyla
# ölçüldü (2026-09-02):
#
#   "## What's Changed"            diyalogda ham markdown olarak görünüyordu
#   3577 karakterin 500'ü kalıyor  %86 kayıp, kesim cümlenin ortasında
#
# ---------------------------------------------------------------------------

class TestBaslikAtiliyor:
    def test_markdown_basligi_atiliyor(self):
        """'## What's Changed' etiketin altında ikinci kez görünmemeli."""
        assert _extract_changelog("## What's Changed\n\n- Fix X") == "- Fix X"

    def test_alt_seviye_baslik_da_atiliyor(self):
        assert _extract_changelog("### Notlar\n\n- Fix X") == "- Fix X"

    def test_kare_ile_baslayan_metin_baslik_degil(self):
        """'#hashtag' başlık değil: markdown başlığı BOŞLUK ister."""
        assert _extract_changelog("#etiket sayılmaz\n- Fix X").startswith("#etiket")

    def test_ortadaki_baslik_korunuyor(self):
        """Yalnız BAŞTAKİ başlık atılıyor, gövdedeki bilgi silinmemeli."""
        sonuc = _extract_changelog("## Bas\n\n- Fix X\n\n## Ara\n\n- Fix Y")
        assert "## Ara" in sonuc and "Fix Y" in sonuc


class TestSatiraHizaliKirpma:
    def test_tavanin_altinda_kirpilmiyor(self):
        metin = "kisa\nmetin"
        assert _satira_hizali_kirp(metin, 100) == (metin, False)

    def test_satir_sinirinda_kesiliyor(self):
        """Cümlenin ortasında değil, satır sonunda bitmeli."""
        metin = "- birinci madde\n- ikinci madde\n- ucuncu madde"
        kesik, kirpildi = _satira_hizali_kirp(metin, 25)
        assert kirpildi is True
        assert kesik == "- birinci madde"

    def test_tek_uzun_satir_sert_kesiliyor(self):
        """Tavandan uzun TEK satırda satır sınırı yok: sert kesim, ama
        kırpıldığı yine söyleniyor, yoksa kullanıcı eksik olduğunu bilmez."""
        kesik, kirpildi = _satira_hizali_kirp("a" * 100, 30)
        assert kirpildi is True
        assert len(kesik) == 30

    def test_kirpilmis_sonuc_bayrakla_geliyor(self, monkeypatch):
        govde = "\n".join("- %d numarali oldukca uzun bir madde" % i
                          for i in range(200))
        up = _yanitla(
            monkeypatch,
            _json.dumps({"tag_name": "v99.0.0", "body": govde,
                         "html_url": "https://x"}))
        sonuc = up.check_for_update(force=True)
        assert sonuc["kirpildi"] is True
        assert len(sonuc["notes"]) <= up._NOT_TAVANI
        # Satır sınırında bittiği için son satır yarım kalmamalı
        assert sonuc["notes"].endswith("madde")

    def test_kisa_notta_bayrak_dusuk(self, monkeypatch):
        up = _yanitla(
            monkeypatch,
            '{"tag_name": "v99.0.0", "body": "- tek madde", "html_url": "u"}')
        assert up.check_for_update(force=True)["kirpildi"] is False
