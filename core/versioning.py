"""Yerel sürümleme — dulwich (saf Python git) ile anlık görüntü ve geçmiş.

Qt bağımlılığı yok; GUI katmanı bunu sarmalar. Standart .git deposu üretir:
gerçek git (git log, git push...) ve dulwich aynı depoda karışık çalışabilir.
Kullanıcı hiçbir git kavramı görmez: "Sürümle" = tüm değişiklikleri tek
anlık görüntüye kaydet, "Geçmiş" = kayıt listesi.
"""

import difflib
import logging
import os
import time
from dataclasses import dataclass

from core import fs_ops

_logger = logging.getLogger("latex_editor.versioning")

try:
    from dulwich import porcelain
    from dulwich.repo import Repo
    DULWICH_AVAILABLE = True
except ImportError:  # pragma: no cover — uygulama dulwich'süz de AÇILMALI
    porcelain = None
    Repo = None
    DULWICH_AVAILABLE = False


def _require():
    """dulwich yoksa anlaşılır hata ver (uygulama başlarken değil, kullanırken)."""
    if not DULWICH_AVAILABLE:
        raise RuntimeError(
            "Sürümleme için 'dulwich' paketi gerekli (pip install dulwich)")

# Kayıt kimliği: kullanıcı git yapılandırmadıysa da kayıt atılabilsin.
# Git kullanan biri kendi kimliğiyle dışarıdan kayıt atmaya devam edebilir.
_AUTHOR = b"LaTeX Editor <latex-editor@local>"

# LaTeX derleme artıkları geri üretilebilir; geçmişe girmesinler. PDF de
# bilinçli olarak dışarıda (sürümleme kaynak kurtarma amaçlı; isteyen
# .gitignore'dan çıkarabilir).
# Liste ELLE YAZILMIYOR: `fs_ops.DERLEME_ARTIKLARI` tek kaynak. Buradaki ve
# dosya ağacındaki kopyalar ayrışmıştı (bkz. o sabitin yorumundaki ölçüm).
IGNORE_TEMPLATE = (
    "# LaTeX derleme artıkları (geri üretilebilir)\n"
    + "".join("*%s\n" % sonek for sonek in fs_ops.DERLEME_ARTIKLARI)
    + "# PDF yeniden derlenebilir; sürümlenmesini isterseniz son satırı silin\n"
      "*.pdf\n"
)


@dataclass
class VersionEntry:
    sha: str        # tam sha (nesne erişimi için)
    timestamp: int  # unix saniye
    message: str
    nfiles: int     # bu sürümde değişen dosya sayısı

    @property
    def short(self) -> str:
        return self.sha[:9]


def is_repo(root: str) -> bool:
    return os.path.isdir(os.path.join(root, ".git"))


@dataclass
class RepoStatus:
    """Sürümlemenin hangi depoya dokunacağının teşhisi.

    'Sürümle' kullanıcının kendi git deposuna commit atabilir: editör depoyu
    ayırt etmez, mevcut .git'i olduğu gibi kullanır. Bu tasarım bilinçlidir
    (gerçek git ile birlikte çalışsın diye) ama kullanıcı bunu bilmeden
    kendi dalına kayıt atarsa — ya da 'Tüm Geçmişi Sil' ile aylarca geçmişi
    çöp kutusuna yollarsa — sürpriz olur. GUI katmanı bu teşhisle uyarır.
    """
    exists: bool          # root'un kendisi bir depo mu
    remotes: list         # tanımlı remote adları (origin, upstream...)
    foreign: bool         # depo VAR ve editörün yarattığı depo değil
    parent_repo: str      # root depo DEĞİLSE, onu kapsayan üst deponun yolu

    @property
    def nested(self) -> bool:
        """Burada 'Sürümle' üst deponun içine iç içe .git yaratır mı?"""
        return not self.exists and bool(self.parent_repo)


def _enclosing_repo(root: str) -> str:
    """root'u kapsayan en yakın üst deponun yolu (yoksa "")."""
    cur = os.path.abspath(root)
    while True:
        parent = os.path.dirname(cur)
        if parent == cur:            # kök dizine ulaşıldı
            return ""
        if os.path.isdir(os.path.join(parent, ".git")):
            return parent
        cur = parent


def repo_status(root: str) -> RepoStatus:
    """Depo teşhisi — GUI uyarıları için. dulwich yoksa da güvenle çağrılır."""
    if not is_repo(root):
        return RepoStatus(exists=False, remotes=[], foreign=False,
                          parent_repo=_enclosing_repo(root))
    remotes: list[str] = []
    foreign = True   # okuyamıyorsak temkinli davran: yabancı say, uyar
    if DULWICH_AVAILABLE:
        try:
            repo = Repo(root)
            cfg = repo.get_config()
            for section in cfg.sections():
                if len(section) == 2 and section[0] == b"remote":
                    remotes.append(section[1].decode("utf-8", "replace"))
            # Editörün kendi deposunda HEAD commit'i _AUTHOR imzalıdır. Remote
            # tanımlıysa zaten kullanıcının deposudur (editör remote eklemez).
            head_author = repo[repo.head()].author
            foreign = bool(remotes) or head_author != _AUTHOR
        except KeyError:
            foreign = bool(remotes)   # kayıtsız (boş) depo: HEAD yok
        except Exception:             # bozuk/erişilemez depo — temkinli kal
            _logger.warning("Depo durumu okunamadı: %s", root, exc_info=True)
    return RepoStatus(exists=True, remotes=remotes, foreign=foreign, parent_repo="")


def init_repo(root: str) -> Repo:
    """Depoyu kur (yoksa) ve .gitignore yaz (yoksa). Varsa olanı döndürür."""
    _require()
    repo = Repo(root) if is_repo(root) else porcelain.init(root)
    gi = os.path.join(root, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8") as f:
            f.write(IGNORE_TEMPLATE)
    return repo


def _commit_nfiles(repo, commit) -> int:
    """Kayıtta değişen dosya sayısı: üst ağaçla fark (ilk kayıtta tümü).

    Sayının TEK KAYNAĞI burasıdır. Eskiden 'Sürümle' sayıyı ``status``
    çıktısındaki girdi sayısından, geçmiş paneli ise buradan alıyordu ve
    ikisi ÇELİŞEBİLİYORDU: dulwich'in status'u tümüyle izlenmeyen bir DİZİNİ
    tek girdi ('bolumler/') olarak döndürüyor, içindeki dosyaları değil.
    Bölümlerini alt klasöre ayıran bir belgede aynı kayıt için durum çubuğu
    "2 dosya", geçmiş paneli "6 dosya" diyordu (ölçüldü).
    """
    from dulwich.diff_tree import tree_changes

    parent_tree = (repo.object_store[commit.parents[0]].tree
                   if commit.parents else None)
    return sum(1 for _ in tree_changes(repo.object_store, parent_tree,
                                       commit.tree))


def _status_paths(status) -> set[str]:
    """GitStatus'ten değişen/izlenmeyen göreli yolları (POSIX ayraçlı) topla."""
    paths: set[bytes] = set()
    for group in status.staged.values():
        paths.update(p for p in group if isinstance(p, bytes))
    paths.update(p for p in status.unstaged if isinstance(p, bytes))
    paths.update(p for p in status.untracked if isinstance(p, bytes))
    return {p.decode("utf-8", "replace").replace(os.sep, "/") for p in paths}


def changed_files(root: str) -> set[str]:
    """Son kayıttan beri değişen/eklenen/silinen DOSYALAR (boş küme = temiz).

    ``untracked_files="all"`` şart: dulwich'in öntanımlı "normal" kipi tümüyle
    izlenmeyen bir dizini tek girdi ('bolumler/') olarak döndürüyor, yani
    fonksiyon adının vaat ettiği dosya listesini vermiyordu. Bu kip yavaş
    (2000 izlenmeyen dosyada 6 ms yerine 1 sn, ölçüldü) ama burası yalnız
    listeyi gerçekten isteyenler için; 'değişiklik var mı' sorusu snapshot
    içinde ucuz kiple cevaplanıyor.
    """
    if not DULWICH_AVAILABLE or not is_repo(root):
        return set()
    return _status_paths(porcelain.status(Repo(root), untracked_files="all"))


def snapshot(root: str, message: str) -> VersionEntry | None:
    """Tüm değişiklikleri tek kayda al (değişiklik yoksa None; boş kayıt atma).

    Dosya ağacı taramaları .git ve nokta-klasörleri atladığı için depoya
    yalnız görünür proje dosyaları girer; .gitignore derleme artıklarını eler.
    """
    _require()
    repo = Repo(root)
    # Burada YALNIZCA "değişiklik var mı" sorusu soruluyor, liste değil; o
    # yüzden ucuz olan öntanımlı kip yeterli (dizinleri toplayan kip de boş
    # ile dolu arasını doğru ayırır). Dosya SAYISI kayıttan sonra kaydın
    # kendisinden okunuyor, bkz. _commit_nfiles.
    if not _status_paths(porcelain.status(repo)):
        return None
    porcelain.add(repo)
    sha = porcelain.commit(repo, message=message.encode("utf-8"),
                           author=_AUTHOR, committer=_AUTHOR, all=True)
    return VersionEntry(sha=sha.decode(), timestamp=int(time.time()),
                        message=message,
                        nfiles=_commit_nfiles(repo, repo[sha]))


def history(root: str, limit: int = 100) -> list[VersionEntry]:
    """Kayıtları yeniden eskiye doğru listeleye (yoksa boş liste)."""
    if not DULWICH_AVAILABLE or not is_repo(root):
        return []
    repo = Repo(root)
    entries = []
    for entry in repo.get_walker(max_entries=limit):
        c = entry.commit
        entries.append(VersionEntry(
            sha=c.id.decode(),
            timestamp=c.commit_time,
            message=c.message.decode("utf-8", "replace").strip(),
            nfiles=_commit_nfiles(repo, c),
        ))
    return entries


def drop_all(root: str) -> bool:
    """TÜM sürüm geçmişini sil (.git klasörünü geri dönüşüm kutusuna atar).

    Proje dosyalarına dokunmaz. Geri dönüşüm kutusu kullanıldığı için yanlış
    silmede klasör geri getirilebilir. Depo yoksa False.
    """
    git_dir = os.path.join(root, ".git")
    if not os.path.isdir(git_dir):
        return False
    import send2trash
    try:
        send2trash.send2trash(git_dir)
    except Exception:
        _logger.error("Geçmiş silinemedi: %s", root, exc_info=True)
        return False
    return True


def file_bytes(root: str, sha_hex: str, rel_path: str) -> bytes | None:
    """Kayıttaki bir dosyanın HAM baytları (yoksa None).

    Geri yükleme bunu kullanır: decode/encode döngüsü kodlama bozar (cp1254
    Türkçe dosyada her karakter değiştirme karakterine dönüşürdü). İkili
    dosyalar (resim vb.) da ancak bu yolla bozulmadan geri gelir.
    """
    from dulwich.objects import Tree

    _require()
    repo = Repo(root)
    commit = repo.object_store[sha_hex.encode()]
    obj = repo.object_store[commit.tree]
    for part in rel_path.replace(os.sep, "/").split("/"):
        if not part:
            continue
        if not isinstance(obj, Tree):
            return None
        try:
            mode, hexsha = obj[part.encode()]
        except KeyError:
            return None
        obj = repo.object_store[hexsha]
    return obj.data if hasattr(obj, "data") else None


def file_content(root: str, sha_hex: str, rel_path: str) -> str | None:
    """Kayıttaki dosyanın metin hâli (yalnız GÖSTERİM için: fark ekranı).

    Kodlama kabulü utf-8'dir; bozuk baytlar değiştirme karakteri olur.
    Diske yazım için file_bytes kullanın.
    """
    data = file_bytes(root, sha_hex, rel_path)
    return data.decode("utf-8", "replace") if data is not None else None


def drop_last(root: str) -> bool:
    """En yeni kaydı geçmişten düşür; dosyalara DOKUNMAZ. İlk kayıtta False.

    'Yanlışlıkla sürüm attım' düzeltmesi için: son kayıt geçmişten silinir,
    çalışma klasörü ve değişiklikler yerinde kalır (bir sonraki Sürümle yeniden
    kayda girer). Ara kayıtları silmek bilinçli olarak YOK: ara kaydı koparmak
    tüm sonraki kayıtların yeniden yazılmasını (rebase) gerektirir ve
    karışıklıktan başka şey katmaz.
    """
    _require()
    repo = Repo(root)
    symrefs = dict(repo.refs.get_symrefs())
    head_ref = symrefs.get(b"HEAD")
    if head_ref is None:
        return False
    commit = repo.object_store[repo.refs[head_ref]]
    if not commit.parents:
        return False  # ilk kayıt geçmişin köküdür; silinmez
    repo.refs[head_ref] = commit.parents[0]
    return True


def file_diff(root: str, sha_hex: str, rel_path: str) -> str:
    """Kayıttaki hâli ile diskteki hâlin birleşik farkı ('eski → yeni')."""
    _require()
    old = file_content(root, sha_hex, rel_path) or ""
    path = os.path.join(root, rel_path.replace("/", os.sep))
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            new = f.read()
    except OSError:
        new = ""
    diff = difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"{rel_path}@{sha_hex[:7]}", tofile=rel_path)
    return "".join(diff)
