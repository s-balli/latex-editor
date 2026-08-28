"""versioning.repo_status — 'bu, kullanıcının kendi git deposu mu?' teşhisi.

'Sürümle' mevcut .git'i olduğu gibi kullanır: kullanıcının gerçek deposunda
kayıt gerçek dala işlenir, 'Tüm Geçmişi Sil' gerçek .git'i çöpe atar. GUI bu
teşhise bakıp uyarır; teşhis yanılırsa ya sessiz veri kaybı (foreign=False
sanıldı) ya da her sürümlemede gereksiz uyarı (foreign=True sanıldı) olur.
"""

import pytest

dulwich = pytest.importorskip("dulwich")

from dulwich import porcelain  # noqa: E402
from dulwich.repo import Repo  # noqa: E402

from core import versioning as V  # noqa: E402


def _mk(root):
    (root / "ana.tex").write_text("merhaba\n", encoding="utf-8")


def _editor_repo(root):
    """Editörün yaratacağı depo: init + _AUTHOR imzalı bir kayıt."""
    _mk(root)
    V.init_repo(str(root))
    V.snapshot(str(root), "Başlangıç sürümü")
    return str(root)


def _foreign_commit(root, author=b"Ayse Yilmaz <ayse@example.com>"):
    """Kullanıcının kendi eliyle attığı kayıt (farklı imza)."""
    repo = Repo(str(root))
    porcelain.add(repo)
    porcelain.commit(repo, message=b"kendi kaydim", author=author, committer=author)


# --- depo yok ---


def test_depo_yoksa_uyari_gerekmez(tmp_path):
    st = V.repo_status(str(tmp_path))
    assert st.exists is False
    assert st.foreign is False
    assert st.parent_repo == ""
    assert st.nested is False


# --- editörün kendi deposu: uyarı ÇIKMAMALI ---


def test_editorun_kendi_deposu_yabanci_degil(tmp_path):
    root = _editor_repo(tmp_path)
    st = V.repo_status(root)
    assert st.exists is True
    assert st.remotes == []
    assert st.foreign is False, "kendi deposunda her Ctrl+K'da uyarı çıkardı"


def test_editorun_ard_arda_kayitlari_yabanci_degil(tmp_path):
    root = _editor_repo(tmp_path)
    (tmp_path / "ana.tex").write_text("degisti\n", encoding="utf-8")
    V.snapshot(root, "ikinci")
    assert V.repo_status(root).foreign is False


# --- kullanıcının kendi deposu: uyarı ÇIKMALI ---


def test_baska_imzali_kayit_yabanci_sayilir(tmp_path):
    """Remote'suz yerel depo da kullanıcının olabilir; imza ayırt eder."""
    _mk(tmp_path)
    porcelain.init(str(tmp_path))
    _foreign_commit(tmp_path)
    st = V.repo_status(str(tmp_path))
    assert st.exists is True
    assert st.foreign is True


def test_remote_varsa_yabanci_sayilir(tmp_path):
    """Editör hiç remote eklemez; remote = kullanıcının deposu."""
    root = _editor_repo(tmp_path)
    repo = Repo(root)
    cfg = repo.get_config()
    cfg.set((b"remote", b"origin"), b"url", b"git@github.com:kullanici/tez.git")
    cfg.write_to_path()
    st = V.repo_status(root)
    assert st.remotes == ["origin"]
    assert st.foreign is True, "editör imzası remote'u gölgelememeli"


def test_kayitsiz_bos_depo_yabanci_sayilmaz(tmp_path):
    """git init atılmış ama hiç commit yok: HEAD okunamaz, patlamamalı."""
    _mk(tmp_path)
    porcelain.init(str(tmp_path))
    st = V.repo_status(str(tmp_path))
    assert st.exists is True
    assert st.foreign is False


# --- iç içe depo ---


def test_ust_depo_altindaki_klasor_nested(tmp_path):
    """repo/makale/ açılırsa 'Sürümle' iç içe .git yaratır — uyarılmalı."""
    _mk(tmp_path)
    porcelain.init(str(tmp_path))
    alt = tmp_path / "makale"
    alt.mkdir()
    st = V.repo_status(str(alt))
    assert st.exists is False
    assert st.parent_repo == str(tmp_path)
    assert st.nested is True


def test_kendisi_depo_olan_klasor_nested_degil(tmp_path):
    """Zaten depo olan klasörde iç içe uyarısı anlamsız."""
    _mk(tmp_path)
    porcelain.init(str(tmp_path))
    alt = tmp_path / "makale"
    alt.mkdir()
    porcelain.init(str(alt))
    st = V.repo_status(str(alt))
    assert st.exists is True
    assert st.nested is False
    assert st.parent_repo == ""


def test_derin_alt_klasor_ust_depoyu_bulur(tmp_path):
    _mk(tmp_path)
    porcelain.init(str(tmp_path))
    derin = tmp_path / "a" / "b" / "c"
    derin.mkdir(parents=True)
    assert V.repo_status(str(derin)).parent_repo == str(tmp_path)


def test_depo_altinda_olmayan_derin_klasor(tmp_path):
    derin = tmp_path / "a" / "b"
    derin.mkdir(parents=True)
    st = V.repo_status(str(derin))
    assert st.parent_repo == ""
    assert st.nested is False


# --- dayanıklılık ---


def test_bozuk_depo_temkinli_davranir(tmp_path):
    """.git var ama okunamıyor: sessizce 'güvenli' demek yerine uyar."""
    _mk(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("bu gecerli bir git yapisi degil\n",
                                              encoding="utf-8")
    st = V.repo_status(str(tmp_path))
    assert st.exists is True
    assert st.foreign is True, "okunamayan depoda uyarı bastırılmamalı"


def test_dulwich_yoksa_patlamaz(tmp_path, monkeypatch):
    """repo_status _require() çağırmaz: dulwich'siz kurulumda da güvenli."""
    _mk(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(V, "DULWICH_AVAILABLE", False)
    st = V.repo_status(str(tmp_path))
    assert st.exists is True
    assert st.foreign is True
