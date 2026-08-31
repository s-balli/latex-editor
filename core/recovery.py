"""Çökme kurtarma — kirli arabelleklerin disk anlık görüntüleri.

Kapatılan delik: uygulama çöker, öldürülür ya da elektrik giderse
kaydedilmemiş içerik tamamen gidiyordu. 2026-08-30 turunda kapatılan üç veri
kaybı yolu ("uygulama çalışıyordu ve yanlış davrandı" türü) bunu KAPSAMIYOR —
burada uygulama hiç konuşamadan ölüyor, yani soracak bir an yok.

Tasarım: kirli sekmelerin içeriği periyodik olarak uygulama veri dizinine
yazılır. Açılışta artık dosya varsa kullanıcıya SORULUR; temiz kapanışta
dosyalar silinir. Kullanıcının kendi .tex dosyasına periyodik yazmak
REDDEDİLDİ: yarım düzenleme derlemeyi bozar, dosyalar sürümlemede izleniyor ve
"kaydetmedim" beklentisini ihlal eder.

Bu modül Qt'süz ve saf: dizin dışarıdan verilir, GUI katmanı (mixins/
recovery_ops.py) zamanlayıcıyı ve diyaloğu sağlar. Böylece testler pencere
açmadan koşar.
"""

import json
import os
import tempfile
import time
from dataclasses import dataclass

# Anlık görüntü biçimi sürümü. Okurken uyuşmayan sürüm sessizce ATILIR:
# eski biçimli bir artığı yanlış yorumlayıp kullanıcının içeriğini bozmaktansa
# kurtarmayı atlamak yeğdir.
SURUM = 1

_UZANTI = ".snapshot.json"


@dataclass
class Snapshot:
    """Tek bir kirli sekmenin kurtarılabilir hâli."""
    snap_id: str
    file_path: str      # "" → hiç kaydedilmemiş yeni dosya
    content: str
    encoding: str
    newline: str
    saved_at: float

    @property
    def display_name(self) -> str:
        return os.path.basename(self.file_path) if self.file_path else "Yeni Dosya"


def _yol(dizin: str, snap_id: str) -> str:
    return os.path.join(dizin, snap_id + _UZANTI)


def _yaz_atomik(yol: str, veri: bytes) -> None:
    """Aynı dizinde geçici dosyaya yaz, fsync et, atomik replace.

    Çökme kurtarma dosyasının kendisi çökmede yarım kalırsa hiçbir işe
    yaramaz — o yüzden burada da tmp + fsync + replace şart. Geçici dosya
    hedefle AYNI dizinde tutulur ki os.replace gerçekten atomik olsun.
    (editor._write_atomic ile aynı desen; orası metin + kodlama round-trip'i
    ile ilgilendiği, burası ham bayt yazdığı için ayrı duruyorlar.)
    """
    d = os.path.dirname(yol)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(veri)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, yol)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def yaz(dizin: str, snap_id: str, *, file_path: str, content: str,
        encoding: str = "utf-8", newline: str = "lf") -> bool:
    """Bir sekmenin anlık görüntüsünü yaz. Başarılıysa True.

    İçerik JSON içinde saklanır: kodlama/satır sonu bilgisi içerikle BİRLİKTE
    taşınmalı, yoksa cp1254 bir dosyayı geri yüklerken hangi kodlamayla
    kaydedileceği bilinmez. Dosyanın kendisi her zaman UTF-8'dir.
    """
    try:
        os.makedirs(dizin, exist_ok=True)
        gövde = {
            "version": SURUM,
            "file_path": file_path,
            "encoding": encoding,
            "newline": newline,
            "saved_at": time.time(),
            "content": content,
        }
        _yaz_atomik(_yol(dizin, snap_id),
                    json.dumps(gövde, ensure_ascii=False).encode("utf-8"))
        return True
    except (OSError, ValueError, TypeError):
        return False


def sil(dizin: str, snap_id: str) -> None:
    """Bir anlık görüntüyü sil (yoksa sessiz)."""
    try:
        os.unlink(_yol(dizin, snap_id))
    except OSError:
        pass


def oku(dizin: str) -> list[Snapshot]:
    """Dizindeki tüm geçerli anlık görüntüler (en yeniden eskiye).

    Bozuk/eksik/yabancı sürümlü dosyalar atlanır — kurtarma akışı hiçbir
    koşulda istisna fırlatmamalı, yoksa açılışı komple engeller.
    """
    out: list[Snapshot] = []
    try:
        adlar = sorted(os.listdir(dizin))
    except OSError:
        return out
    for ad in adlar:
        if not ad.endswith(_UZANTI):
            continue
        try:
            with open(os.path.join(dizin, ad), "r", encoding="utf-8") as f:
                g = json.load(f)
            if g.get("version") != SURUM:
                continue
            out.append(Snapshot(
                snap_id=ad[:-len(_UZANTI)],
                file_path=g["file_path"],
                content=g["content"],
                encoding=g.get("encoding", "utf-8"),
                newline=g.get("newline", "lf"),
                saved_at=float(g.get("saved_at", 0.0)),
            ))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    out.sort(key=lambda s: s.saved_at, reverse=True)
    return out


def hepsini_sil(dizin: str) -> int:
    """Tüm anlık görüntüleri (ve yarım kalmış .tmp artıklarını) sil; sayıyı döndür."""
    n = 0
    try:
        adlar = os.listdir(dizin)
    except OSError:
        return 0
    for ad in adlar:
        if not (ad.endswith(_UZANTI) or ad.endswith(".tmp")):
            continue
        try:
            os.unlink(os.path.join(dizin, ad))
            n += 1
        except OSError:
            pass
    return n


def kayip_var_mi(snap: Snapshot) -> bool:
    """Bu anlık görüntü GERÇEKTEN kurtarılacak bir şey taşıyor mu?

    Diskteki dosya zaten aynı içeriği taşıyorsa kayıp yoktur: kullanıcı
    kaydetmiş, sonra uygulama çökmüş olabilir. O durumda "kaydedilmemiş
    değişiklik bulundu" demek yanıltıcı olur ve kullanıcıyı boşuna korkutur.

    Hiç kaydedilmemiş dosya (file_path boş) her zaman kayıptır.
    Dosya okunamıyorsa (silinmiş, erişilemez) da kayıp sayılır — içerik
    yalnızca anlık görüntüde duruyor demektir.
    """
    if not snap.file_path:
        return True
    try:
        with open(snap.file_path, "r", encoding=snap.encoding, errors="replace") as f:
            diskteki = f.read()
    except OSError:
        return True
    # Satır sonu stilini normalize et: editör CRLF'i kayıtta üretiyor,
    # anlık görüntü ise arabellek metnini (LF) taşıyor — fark gerçek değil.
    return _lf(diskteki) != _lf(snap.content)


def _lf(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")
