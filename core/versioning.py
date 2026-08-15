"""Yerel sürümleme — dulwich (saf Python git) ile anlık görüntü ve geçmiş.

Qt bağımlılığı yok; GUI katmanı bunu sarmalar. Standart .git deposu üretir:
gerçek git (git log, git push...) ve dulwich aynı depoda karışık çalışabilir.
Kullanıcı hiçbir git kavramı görmez: "Sürümle" = tüm değişiklikleri tek
anlık görüntüye kaydet, "Geçmiş" = kayıt listesi.
"""

import difflib
import os
import time
from dataclasses import dataclass

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
IGNORE_TEMPLATE = """\
# LaTeX derleme artıkları (geri üretilebilir)
*.aux
*.log
*.out
*.toc
*.lof
*.lot
*.bbl
*.blg
*.bcf
*.run.xml
*.fls
*.fdb_latexmk
*.synctex.gz
*.idx
*.ilg
*.ind
*.nav
*.snm
*.vrb
*.dvi
*.xdv
# PDF yeniden derlenebilir; sürümlenmesini isterseniz son satırı silin
*.pdf
"""


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


def init_repo(root: str) -> Repo:
    """Depoyu kur (yoksa) ve .gitignore yaz (yoksa). Varsa olanı döndürür."""
    _require()
    repo = Repo(root) if is_repo(root) else porcelain.init(root)
    gi = os.path.join(root, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8") as f:
            f.write(IGNORE_TEMPLATE)
    return repo


def _status_paths(status) -> set[str]:
    """GitStatus'ten değişen/izlenmeyen göreli yolları (POSIX ayraçlı) topla."""
    paths: set[bytes] = set()
    for group in status.staged.values():
        paths.update(p for p in group if isinstance(p, bytes))
    paths.update(p for p in status.unstaged if isinstance(p, bytes))
    paths.update(p for p in status.untracked if isinstance(p, bytes))
    return {p.decode("utf-8", "replace").replace(os.sep, "/") for p in paths}


def changed_files(root: str) -> set[str]:
    """Son kayıttan beri değişen/eklenen/silinen dosyalar (boş küme = temiz)."""
    if not DULWICH_AVAILABLE or not is_repo(root):
        return set()
    return _status_paths(porcelain.status(Repo(root)))


def snapshot(root: str, message: str) -> VersionEntry | None:
    """Tüm değişiklikleri tek kayda al (değişiklik yoksa None; boş kayıt atma).

    Dosya ağacı taramaları .git ve nokta-klasörleri atladığı için depoya
    yalnız görünür proje dosyaları girer; .gitignore derleme artıklarını eler.
    """
    _require()
    repo = Repo(root)
    changed = _status_paths(porcelain.status(repo))
    if not changed:
        return None
    porcelain.add(repo)
    sha = porcelain.commit(repo, message=message.encode("utf-8"),
                           author=_AUTHOR, committer=_AUTHOR, all=True)
    return VersionEntry(sha=sha.decode(), timestamp=int(time.time()),
                        message=message, nfiles=len(changed))


def history(root: str, limit: int = 100) -> list[VersionEntry]:
    """Kayıtları yeniden eskiye doğru listeleye (yoksa boş liste)."""
    if not DULWICH_AVAILABLE or not is_repo(root):
        return []
    repo = Repo(root)
    entries = []
    for entry in repo.get_walker(max_entries=limit):
        c = entry.commit
        # Kayıttaki dosya sayısı: üst ağaçla fark (ilk kayıtta tüm dosyalar)
        parents = c.parents
        if parents:
            parent = repo.object_store[parents[0]]
            parent_tree = parent.tree
        else:
            parent_tree = None
        from dulwich.diff_tree import tree_changes
        nfiles = sum(1 for _ in tree_changes(repo.object_store, parent_tree, c.tree))
        entries.append(VersionEntry(
            sha=c.id.decode(),
            timestamp=c.commit_time,
            message=c.message.decode("utf-8", "replace").strip(),
            nfiles=nfiles,
        ))
    return entries


def file_content(root: str, sha_hex: str, rel_path: str) -> str | None:
    """Kayıttaki bir dosyanın içeriği (yoksa None; ikili dosya garanti edilmez)."""
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
    return obj.data.decode("utf-8", "replace") if hasattr(obj, "data") else None


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
