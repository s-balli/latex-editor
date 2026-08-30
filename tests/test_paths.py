"""paths.py — Windows/WSL yol dönüşüm testleri."""

from core.paths import windows_to_wsl, wsl_to_windows


class TestWindowsToWsl:
    def test_c_drive(self):
        assert windows_to_wsl(r"C:\Users\test") == "/mnt/c/Users/test"

    def test_d_drive(self):
        assert windows_to_wsl(r"D:\Projects\file.tex") == "/mnt/d/Projects/file.tex"

    def test_lowercase_drive(self):
        assert windows_to_wsl(r"e:\data") == "/mnt/e/data"

    def test_no_drive(self):
        assert windows_to_wsl("relative/path.txt") == "relative/path.txt"

    def test_already_forward_slash(self):
        assert windows_to_wsl("C:/Users/test") == "/mnt/c/Users/test"

    def test_root_drive(self):
        assert windows_to_wsl("C:\\") == "/mnt/c/"

    def test_single_letter_no_colon(self):
        assert windows_to_wsl("C") == "C"

    def test_empty_string(self):
        assert windows_to_wsl("") == ""

    def test_ag_yolu_uydurulmuyor(self):
        r"""Ağ (UNC) paylaşımının WSL karşılığı yok — yol KORUNMALI.

        Bu test eskiden `//server/share/file` bekliyordu, yani hatayı
        sabitliyordu (2026-08-30 denetimi, E3): o yol WSL'de yoktur, üstelik
        hata da verilmediği için derleme "dosya bulunamadı" ile sessizce
        düşüyordu. Uydurulmuş bir yol yerine girdinin korunması, sorunun
        WSL tarafında açık bir hata olarak görünmesini sağlıyor; ayrıntı
        log'a yazılıyor.
        """
        assert windows_to_wsl(r"\\server\share\file") == r"\\server\share\file"

    def test_wsl_kendi_dosya_sistemi_cevriliyor(self):
        r"""\\wsl.localhost\<dagitim>\... ve \\wsl$\... gerçek karşılığı olan
        tek UNC biçimi: dağıtım adı yutulur, gerisi mutlak WSL yoludur."""
        assert windows_to_wsl(r"\\wsl.localhost\Ubuntu\home\s\a.tex") == "/home/s/a.tex"
        assert windows_to_wsl(r"\\wsl$\Ubuntu\home\s\a.tex") == "/home/s/a.tex"
        assert windows_to_wsl(r"\\WSL.LOCALHOST\Debian\tmp\x") == "/tmp/x"
        # Dağıtım kökü
        assert windows_to_wsl(r"\\wsl.localhost\Ubuntu") == "/"

    def test_spaces_in_path(self):
        assert windows_to_wsl(r"C:\My Files\doc.tex") == "/mnt/c/My Files/doc.tex"


class TestWslToWindows:
    def test_c_drive(self):
        assert wsl_to_windows("/mnt/c/Users/test") == r"C:\Users\test"

    def test_d_drive(self):
        assert wsl_to_windows("/mnt/d/data/file.tex") == r"D:\data\file.tex"

    def test_uppercase_drive(self):
        assert wsl_to_windows("/mnt/E/temp") == r"E:\temp"

    def test_root_path(self):
        assert wsl_to_windows("/mnt/c/") == "C:\\"

    def test_not_wsl_path(self):
        assert wsl_to_windows("/home/user/file") == "/home/user/file"

    def test_empty_string(self):
        assert wsl_to_windows("") == ""

    def test_spaces_in_path(self):
        assert wsl_to_windows("/mnt/c/My Files/doc.tex") == r"C:\My Files\doc.tex"

    def test_mnt_without_drive(self):
        assert wsl_to_windows("/mnt/") == "/mnt/"


class TestRoundTrip:
    def test_windows_roundtrip(self):
        original = r"C:\Users\test\document.tex"
        assert wsl_to_windows(windows_to_wsl(original)) == original

    def test_wsl_roundtrip(self):
        original = "/mnt/c/Users/test/document.tex"
        assert windows_to_wsl(wsl_to_windows(original)) == original


# --- clean_child_env: AppImage kütüphane sızıntısı temizliği ---

def test_clean_child_env_removes_library_paths(monkeypatch):
    from core.paths import clean_child_env
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/.mount_AppDir/usr/lib")
    monkeypatch.setenv("LD_PRELOAD", "birsey.so")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = clean_child_env()
    assert "LD_LIBRARY_PATH" not in env and "LD_PRELOAD" not in env
    assert env["PATH"] == "/usr/bin"


def test_clean_child_env_keeps_env_when_clean(monkeypatch):
    from core.paths import clean_child_env
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    monkeypatch.delenv("LD_PRELOAD", raising=False)
    assert clean_child_env() == dict(__import__("os").environ)
