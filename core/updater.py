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
from typing import Optional, Tuple

from core.version import VERSION

GITHUB_OWNER = "s-balli"
GITHUB_REPO = "latex-editor"
API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
TIMEOUT = 5
CACHE_INTERVAL = 86400  # 24 saat (saniye)

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
            return body.split(sep)[0].strip()
    return body.strip()


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
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError, OSError):
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
    tag = release.get("tag_name", "")
    if not tag:
        return {"error": "network"}
    if not _is_newer(tag, VERSION):
        # Güncelleme yok — cache'e None kaydet (24h tekrar sorma)
        _cached_result = None
        _cached_time = now
        return None
    body = release.get("body", "")
    changelog = _extract_changelog(body)
    result = {
        "tag": tag,
        "url": release.get("html_url", f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"),
        "notes": changelog[:500],
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
