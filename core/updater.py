"""Otomatik güncelleme kontrolü — GitHub Releases API ile sürüm karşılaştırma.

Check-and-notify modeli: sessiz kurulum yok, sadece yeni sürüm varsa kullanıcıya
bildir ve Release sayfasına yönlendir.

Çalışma: latest release'ın tag_name'ini alır (v1.0.0 formatında), çalışan
VERSION ile semver karşılaştırması yapar. Network hatası için 5s timeout.

Cache: Açılış kontrolleri 24 saatte bir ile sınırlıdır (GitHub API rate limit
koruması). Manuel kontrol (Yardım menüsü) cache'i bypass eder.
"""

import json
import time
import urllib.request
import urllib.error
import re
from typing import Optional, Tuple

from core.version import VERSION

GITHUB_OWNER = "s-balli"
GITHUB_REPO = "latex-editor"
API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
TIMEOUT = 5
# Yanıt üst sınırı (bkz. fetch_latest_release).
_MAX_YANIT = 1024 * 1024
CACHE_INTERVAL = 86400  # 24 saat (saniye)

# Diyalogda gosterilecek not tavani. Eskiden 500'du ve v1.0.19'un 3577
# karakterlik changelog'unun %86'si kayboluyordu (13 maddeden 2'si yarim
# goruunuyordu). Tavan tamamen kalkarsa QMessageBox kaydirilamadigi icin
# diyalog ekrandan tasar; kirpildiginda kullaniciya soyleniyor.
_NOT_TAVANI = 1500
_RE_BASLIK = re.compile(r"\s*#{1,6}\s")

# In-memory cache — process içinde tekrar tekrar API çağrısı yapma
_cached_result: Optional[dict] = None
_cached_time: float = 0


def _parse_semver(tag: str) -> Tuple[int, int, int]:
    """'v1.2.3' -> (1, 2, 3). Geçersizse (0, 0, 0)."""
    tag = tag.lstrip("vV")
    parts = tag.split(".")
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return (0, 0, 0)


def _is_newer(latest: str, current: str) -> bool:
    """latest > current mi?"""
    return _parse_semver(latest) > _parse_semver(current)


def _extract_changelog(body: str) -> str:
    """Release body'den sadece changelog kısmını ayıkla.

    Release body yapısı: '## What's Changed\\n...\\n---\\n## Installation...'
    Sadece '---' ayırıcısından önceki changelog kısmını alır.
    """
    # Önce spesifik ayırıcı dene (güvenli)
    for sep in ("---\n\n## Installation", "---\n\n## Kurulum", "---"):
        if sep in body:
            body = body.split(sep)[0]
            break
    # Baştaki markdown başlığını at: "## What's Changed" diyalogda ham metin
    # olarak görünüyordu (ölçüldü 2026-09-02, v1.0.19 yanıtı) ve zaten
    # "Sürüm notları:" etiketinin altında duruyor.
    satirlar = body.strip().splitlines()
    while satirlar and (not satirlar[0].strip()
                        or _RE_BASLIK.match(satirlar[0])):
        satirlar.pop(0)
    return "\n".join(satirlar).strip()


def _satira_hizali_kirp(metin: str, tavan: int) -> Tuple[str, bool]:
    """Tavanı aşmayan, SATIR sınırında biten parça ve kırpıldı mı bilgisi.

    Düz `metin[:tavan]` cümlenin ortasında kesiyordu; kullanıcı 13 maddenin
    ikisini yarım görüyor ve devamı olduğunu anlamıyordu. Tek bir satır bile
    tavandan uzunsa sert kesime düşülüyor, o zaman da kırpıldığı söyleniyor.
    """
    if len(metin) <= tavan:
        return metin, False
    kesik = metin[:tavan]
    son = kesik.rfind("\n")
    if son > 0:
        kesik = kesik[:son]
    return kesik.rstrip(), True


def fetch_latest_release() -> Optional[dict]:
    """GitHub API'den en son release'i döndür.

    Returns:
        dict: Release verisi (başarılı)
        None: Hata veya bağlantı yok
    """
    req = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"LaTeX-Editor/{VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            # SINIRLI okuma: `read()` sınırsızdır. GitHub'ın release yanıtı
            # birkaç KB; 1 MB tavan hem fazlasıyla geniş hem de ele geçirilmiş
            # ya da yalnızca bozuk bir uca karşı belleği koruyor.
            veri = json.loads(
                resp.read(_MAX_YANIT + 1)[:_MAX_YANIT].decode("utf-8"))
            # Gecerli JSON ama NESNE olmayabilir (dizi, metin, sayi, null).
            # O zaman asagidaki `.get` AttributeError atiyordu ve GUI bunu
            # yuttugu icin her kontrol "ag hatasi" gibi goruunuyordu
            # (olculdu 2026-09-02, dis guvenlik raporu 5. bulgu).
            return veri if isinstance(veri, dict) else None
    # UnicodeDecodeError LİSTEDE OLMALIYDI, değildi: `.decode("utf-8")` geçersiz
    # bayt dizisinde onu atıyor ve fonksiyonun sözleşmesi ("None: Hata veya
    # bağlantı yok") kırılıyordu. JSONDecodeError ile ikisi de ValueError
    # altında, yani birini yakalayıp diğerini atlamak karar değil gözden
    # kaçmaydı. Arayüz kendi geniş `except Exception`ı ile örtüyordu, yani
    # kullanıcıya çökme olarak yansımıyordu; örtmeyen her çağıran patlıyordu.
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, UnicodeDecodeError, TimeoutError, OSError):
        return None


def check_for_update(force: bool = False) -> Optional[dict]:
    """Güncelleme varsa release dict'i, yoksa None döndür.

    Args:
        force: True ise cache'i bypass et (manuel kontrol için).

    Returns:
        Release dict: {'tag': 'v1.1.0', 'url': 'https://...', 'notes': '...'}
        None: Güncelleme yok, ağ hatası, veya cache geçerli.

        Network hatası durumunda dict 'error' anahtarı ile döner:
        {'error': 'network'} — arayüz bu durumda farklı mesaj gösterir.
    """
    global _cached_result, _cached_time

    # Cache kontrolü — 24 saat geçmediyse ve force değilse cached sonucu döndür.
    # _cached_time > 0 ile kontrol et: "güncelleme yok" (None) sonucu da cache'lenir,
    # böylece her çağrıda API tekrar sorulmaz. Ağ hatası _cached_time'ı güncellemediği
    # için cache'lenmez (tekrar denenebilir).
    now = time.time()
    if not force and _cached_time > 0 and now - _cached_time < CACHE_INTERVAL:
        return _cached_result

    release = fetch_latest_release()
    if not release:
        # Ağ hatası / rate limit — cache'e kaydetme (tekrar denenebilir)
        return {"error": "network"}
    tag = release.get("tag_name")
    # tag_name metin olmayabilir: sayi gelince `_is_newer` icindeki lstrip
    # AttributeError atiyordu.
    if not isinstance(tag, str) or not tag:
        return {"error": "network"}
    if not _is_newer(tag, VERSION):
        # Güncelleme yok — cache'e None kaydet (24h tekrar sorma)
        _cached_result = None
        _cached_time = now
        return None
    # `release.get("body", "")` YETMIYOR: GitHub aciklamasiz release'de alani
    # null gonderiyor, varsayilan da devreye girmiyordu ve `in` denetimi
    # TypeError atiyordu. `or ""` de YETMIYOR: sayi/dizi/nesne gibi TRUTHY ama
    # metin olmayan bir deger gecip _extract_changelog icinde patliyor
    # (dis dogrulama, 2026-09-02). tag_name ve html_url'de isinstance vardi,
    # burada unutulmustu.
    body = release.get("body")
    if not isinstance(body, str):
        body = ""
    changelog = _extract_changelog(body)
    url = release.get("html_url")
    if not isinstance(url, str) or not url:
        url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    notlar, kirpildi = _satira_hizali_kirp(changelog, _NOT_TAVANI)
    result = {
        "tag": tag,
        "url": url,
        "notes": notlar,
        "kirpildi": kirpildi,
    }
    # Cache'e kaydet
    _cached_result = result
    _cached_time = now
    return result


def clear_cache() -> None:
    """Cache'i temizle (test için)."""
    global _cached_result, _cached_time
    _cached_result = None
    _cached_time = 0
